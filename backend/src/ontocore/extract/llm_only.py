from __future__ import annotations

import json
from dataclasses import fields

from ontocore.error_catalog import fault_detail
from ontocore.extract.llm import LlmGateway
from ontocore.models import (
    AttributeCandidateDraft,
    BlockFailure,
    ExtractionResult,
    InstanceRelDraft,
    InstanceSuggestionDraft,
    ObjectCandidateDraft,
    ParsedDocument,
    RelationCandidateDraft,
    TypeSnapshot,
)

_STR = {"type": "string"}
_STR_NULL = {"type": ["string", "null"]}
_NUM = {"type": "number"}


def _object_item(properties: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": properties, "required": required}


EXTRACTION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "object_candidates": {
            "type": "array",
            "items": _object_item(
                {
                    "iri": _STR,
                    "label": _STR,
                    "definition": _STR,
                    "parent_iri": _STR_NULL,
                    "evidence": _STR,
                    "block_id": _STR,
                    "confidence": _NUM,
                },
                ["iri", "label", "definition", "parent_iri", "evidence", "block_id", "confidence"],
            ),
        },
        "attribute_candidates": {
            "type": "array",
            "items": _object_item(
                {
                    "iri": _STR,
                    "label": _STR,
                    "definition": _STR,
                    "owner_iri": _STR,
                    "literal_kind": {"type": "string", "enum": ["text", "number", "date"]},
                    "evidence": _STR,
                    "block_id": _STR,
                    "confidence": _NUM,
                },
                [
                    "iri",
                    "label",
                    "definition",
                    "owner_iri",
                    "literal_kind",
                    "evidence",
                    "block_id",
                    "confidence",
                ],
            ),
        },
        "relation_candidates": {
            "type": "array",
            "items": _object_item(
                {
                    "iri": _STR,
                    "label": _STR,
                    "definition": _STR,
                    "source_iri": _STR,
                    "target_iri": _STR,
                    "evidence": _STR,
                    "block_id": _STR,
                    "confidence": _NUM,
                },
                [
                    "iri",
                    "label",
                    "definition",
                    "source_iri",
                    "target_iri",
                    "evidence",
                    "block_id",
                    "confidence",
                ],
            ),
        },
        "instance_suggestions": {
            "type": "array",
            "items": _object_item(
                {
                    "local_id": _STR,
                    "type_iri": _STR,
                    "label": _STR,
                    "data": {"type": "object"},
                    "evidence": _STR,
                    "block_id": _STR,
                    "confidence": _NUM,
                },
                ["local_id", "type_iri", "label", "data", "evidence", "block_id", "confidence"],
            ),
        },
        "instance_rel_suggestions": {
            "type": "array",
            "items": _object_item(
                {
                    "source_local_id": _STR,
                    "target_local_id": _STR,
                    "predicate_iri": _STR,
                    "evidence": _STR,
                    "block_id": _STR,
                    "confidence": _NUM,
                },
                [
                    "source_local_id",
                    "target_local_id",
                    "predicate_iri",
                    "evidence",
                    "block_id",
                    "confidence",
                ],
            ),
        },
    },
    "required": [
        "object_candidates",
        "attribute_candidates",
        "relation_candidates",
        "instance_suggestions",
        "instance_rel_suggestions",
    ],
}

_DRAFT_TYPES = {
    "object_candidates": ObjectCandidateDraft,
    "attribute_candidates": AttributeCandidateDraft,
    "relation_candidates": RelationCandidateDraft,
    "instance_suggestions": InstanceSuggestionDraft,
    "instance_rel_suggestions": InstanceRelDraft,
}


def _take(cls, item: dict):
    allowed = {f.name for f in fields(cls)}
    return cls(**{key: value for key, value in item.items() if key in allowed})


def result_from_dict(payload: dict) -> ExtractionResult:
    empty_lists = {
        "object_candidates": [],
        "attribute_candidates": [],
        "relation_candidates": [],
        "instance_suggestions": [],
        "instance_rel_suggestions": [],
    }
    if not isinstance(payload, dict) or not any(key in payload for key in _DRAFT_TYPES):
        return ExtractionResult(
            **empty_lists,
            block_failures=[BlockFailure(block_id="", reason=fault_detail("OC-3101"))],
        )
    kwargs: dict = {}
    failures: list[BlockFailure] = []
    for key, cls in _DRAFT_TYPES.items():
        raw = payload.get(key, [])
        if raw is None:
            raw = []
        if not isinstance(raw, list):
            failures.append(BlockFailure(block_id="", reason=fault_detail("OC-3101")))
            kwargs[key] = []
            continue
        kept = []
        for item in raw:
            try:
                if not isinstance(item, dict):
                    raise TypeError("draft is not an object")
                cleaned = dict(item)
                cleaned.pop("similar_to", None)
                kept.append(_take(cls, cleaned))
            except (TypeError, ValueError, KeyError):
                block_id = ""
                if isinstance(item, dict):
                    block_id = str(item.get("block_id") or "")
                failures.append(
                    BlockFailure(block_id=block_id, reason=fault_detail("OC-3101"))
                )
        kwargs[key] = kept
    kwargs["block_failures"] = failures
    return ExtractionResult(**kwargs)


def serialize_snapshot(snapshot: TypeSnapshot) -> dict:
    return {
        "objects": [
            {
                "iri": obj.iri,
                "label": obj.label,
                "definition": obj.definition,
                "parent_iri": obj.parent_iri,
            }
            for obj in snapshot.objects
        ],
        "attributes": [
            {
                "iri": attr.iri,
                "label": attr.label,
                "definition": attr.definition,
                "owner_iri": attr.owner_iri,
                "literal_kind": attr.literal_kind,
            }
            for attr in snapshot.attributes
        ],
        "relations": [
            {
                "iri": rel.iri,
                "label": rel.label,
                "definition": rel.definition,
                "source_iri": rel.source_iri,
                "target_iri": rel.target_iri,
            }
            for rel in snapshot.relations
        ],
    }


class LlmOnlyExtractor:
    name = "llm_only"

    def extract(self, doc: ParsedDocument, snapshot: TypeSnapshot, llm: LlmGateway) -> ExtractionResult:
        messages = [
            {
                "role": "system",
                "content": (
                    "Extract object/attribute/relation candidates and instance suggestions "
                    "aligned to the current ontology snapshot."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "existing": serialize_snapshot(snapshot),
                        "filename": doc.filename,
                        "text": doc.full_text,
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        payload = llm.complete_structured(EXTRACTION_SCHEMA, messages)
        return result_from_dict(payload)
