from __future__ import annotations

import json
from dataclasses import fields

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

EXTRACTION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "object_candidates": {"type": "array", "items": {"type": "object"}},
        "attribute_candidates": {"type": "array", "items": {"type": "object"}},
        "relation_candidates": {"type": "array", "items": {"type": "object"}},
        "instance_suggestions": {"type": "array", "items": {"type": "object"}},
        "instance_rel_suggestions": {"type": "array", "items": {"type": "object"}},
    },
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
    kwargs: dict = {}
    failures: list[BlockFailure] = []
    for key, cls in _DRAFT_TYPES.items():
        items = payload.get(key) or []
        kept = []
        for item in items:
            try:
                cleaned = dict(item)
                cleaned.pop("similar_to", None)
                kept.append(_take(cls, cleaned))
            except (TypeError, ValueError, KeyError):
                block_id = ""
                if isinstance(item, dict):
                    block_id = str(item.get("block_id") or "")
                failures.append(BlockFailure(block_id=block_id, reason="invalid draft"))
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
