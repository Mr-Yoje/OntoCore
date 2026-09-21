from __future__ import annotations

import json
from dataclasses import asdict, fields

from ontocore.candidates.store import CandidateStore, StoredTypeCandidate
from ontocore.constants import NS
from ontocore.errors import ConflictError, GraphUnavailable, OntologyWriteError, StructuredOutputError
from ontocore.graph.ports import GraphRepository
from ontocore.graph.projector import Projector
from ontocore.jobs.store import JobStore
from ontocore.models import (
    InstanceRelDraft,
    InstanceSuggestionDraft,
    OntoAttribute,
    OntoObject,
    OntoRelation,
)
from ontocore.ontology.repository import OntologyRepository

_OBJECT_FIELDS = {f.name for f in fields(OntoObject)}
_ATTRIBUTE_FIELDS = {f.name for f in fields(OntoAttribute)}
_RELATION_FIELDS = {f.name for f in fields(OntoRelation)}
_INSTANCE_FIELDS = {f.name for f in fields(InstanceSuggestionDraft)}
_REL_FIELDS = {f.name for f in fields(InstanceRelDraft)}
_SKIP_UNCONFIRMED_OBJECT = "对象未确认："
_SKIP_UNCONFIRMED_REL = "关系未确认："
_SKIP_MISSING_ENDPOINT = "关系端点未投影："
_MERGE_OBJECT_SYSTEM = "合并为一条对象，必须保留新抽到的要点，编号保持已有编号。"
_MERGE_RELATION_SYSTEM = "合并为一条关系，必须保留新抽到的要点，编号保持已有编号。"
_MERGE_OBJECT_SCHEMA = {
    "type": "object",
    "properties": {
        "label": {"type": "string"},
        "definition": {"type": "string"},
        "parent_iri": {"type": ["string", "null"]},
        "attributes": {"type": "array"},
    },
    "required": ["label", "definition", "parent_iri", "attributes"],
}
_MERGE_RELATION_SCHEMA = {
    "type": "object",
    "properties": {
        "label": {"type": "string"},
        "definition": {"type": "string"},
        "source_iri": {"type": "string"},
        "target_iri": {"type": "string"},
    },
    "required": ["label", "definition", "source_iri", "target_iri"],
}


def _take(cls, payload: dict, allowed: set[str]):
    return cls(**{key: value for key, value in payload.items() if key in allowed})


def _similar_iris(payload: dict) -> list[str]:
    similar = payload.get("similar_to") or []
    iris: list[str] = []
    for item in similar:
        if isinstance(item, dict):
            iri = item.get("iri")
        else:
            iri = getattr(item, "iri", None)
        if iri:
            iris.append(iri)
    return iris


class ReviewService:
    def __init__(self, candidates, ontology, projector, jobs, graph, llm_factory) -> None:
        self._candidates: CandidateStore = candidates
        self._ontology: OntologyRepository = ontology
        self._projector: Projector = projector
        self._jobs: JobStore = jobs
        self._graph: GraphRepository = graph
        self._llm_factory = llm_factory

    def _call_factory(self, job):
        factory = self._llm_factory
        try:
            return factory(job.model, provider_id=job.provider_id, thinking=job.thinking)
        except TypeError:
            return factory(job.model)

    def _owned_attribute_candidates(self, job_id: str, owner_iri: str) -> list[OntoAttribute]:
        items: list[OntoAttribute] = []
        for row in self._candidates.list_type_candidates(job_id):
            if row.kind != "attribute":
                continue
            if row.payload.get("owner_iri") != owner_iri:
                continue
            items.append(_take(OntoAttribute, row.payload, _ATTRIBUTE_FIELDS))
        return items

    def _register(self, iri: str, label: str) -> None:
        self._projector.register_type(iri, label)

    def _accept_create(self, stored: StoredTypeCandidate) -> None:
        payload = stored.payload
        if stored.kind == "object":
            item = _take(OntoObject, payload, _OBJECT_FIELDS)
            self._ontology.create_object(item)
            self._register(item.iri, item.label)
        elif stored.kind == "relation":
            item = _take(OntoRelation, payload, _RELATION_FIELDS)
            self._ontology.create_relation(item)
            self._register(item.iri, item.label)
        else:
            raise ValueError(stored.kind)

    def _accept_overwrite(self, stored: StoredTypeCandidate, target_iri: str) -> None:
        payload = stored.payload
        if stored.kind == "object":
            attrs = self._owned_attribute_candidates(stored.job_id, payload["iri"])
            self._ontology.replace_object_bundle(
                target_iri,
                label=payload["label"],
                definition=payload["definition"],
                parent_iri=payload.get("parent_iri"),
                attributes=attrs,
            )
            self._register(target_iri, payload["label"])
            for attr in attrs:
                self._register(attr.iri, attr.label)
            return
        if stored.kind == "relation":
            self._ontology.replace_relation_payload(
                target_iri,
                label=payload["label"],
                definition=payload["definition"],
                source_iri=payload["source_iri"],
                target_object_iri=payload["target_iri"],
            )
            self._register(target_iri, payload["label"])
            return
        raise ValueError(stored.kind)

    def _existing_object_bundle(self, target_iri: str) -> dict:
        snap = self._ontology.snapshot()
        obj = next(item for item in snap.objects if item.iri == target_iri)
        owned = [attr for attr in snap.attributes if attr.owner_iri == target_iri]
        return {**asdict(obj), "attributes": [asdict(attr) for attr in owned]}

    def _incoming_object_bundle(self, stored: StoredTypeCandidate) -> dict:
        payload = stored.payload
        attrs = self._owned_attribute_candidates(stored.job_id, payload["iri"])
        return {
            "iri": payload.get("iri"),
            "label": payload.get("label"),
            "definition": payload.get("definition"),
            "parent_iri": payload.get("parent_iri"),
            "attributes": [asdict(attr) for attr in attrs],
        }

    def _accept_merge(self, stored: StoredTypeCandidate, target_iri: str) -> None:
        job = self._jobs.get(stored.job_id)
        llm = self._call_factory(job)
        try:
            if stored.kind == "object":
                raw = llm.complete_structured(
                    _MERGE_OBJECT_SCHEMA,
                    [
                        {"role": "system", "content": _MERGE_OBJECT_SYSTEM},
                        {
                            "role": "user",
                            "content": json.dumps(
                                {
                                    "existing": self._existing_object_bundle(target_iri),
                                    "incoming": self._incoming_object_bundle(stored),
                                },
                                ensure_ascii=False,
                            ),
                        },
                    ],
                )
                needed = ("label", "definition", "parent_iri", "attributes")
                if not isinstance(raw, dict) or any(key not in raw for key in needed):
                    raise OntologyWriteError("融合失败")
                if not isinstance(raw["attributes"], list):
                    raise OntologyWriteError("融合失败")
                attrs: list[OntoAttribute] = []
                for item in raw["attributes"]:
                    if not isinstance(item, dict) or any(
                        key not in item for key in ("iri", "label", "definition", "literal_kind")
                    ):
                        raise OntologyWriteError("融合失败")
                    attrs.append(
                        OntoAttribute(
                            iri=item["iri"],
                            label=item["label"],
                            definition=item["definition"],
                            owner_iri=target_iri,
                            literal_kind=item["literal_kind"],
                        )
                    )
                self._ontology.replace_object_bundle(
                    target_iri,
                    label=raw["label"],
                    definition=raw["definition"],
                    parent_iri=raw["parent_iri"],
                    attributes=attrs,
                )
                self._register(target_iri, raw["label"])
                for attr in attrs:
                    self._register(attr.iri, attr.label)
                return
            if stored.kind == "relation":
                snap = self._ontology.snapshot()
                existing = next(item for item in snap.relations if item.iri == target_iri)
                raw = llm.complete_structured(
                    _MERGE_RELATION_SCHEMA,
                    [
                        {"role": "system", "content": _MERGE_RELATION_SYSTEM},
                        {
                            "role": "user",
                            "content": json.dumps(
                                {
                                    "existing": asdict(existing),
                                    "incoming": {
                                        key: stored.payload.get(key)
                                        for key in ("iri", "label", "definition", "source_iri", "target_iri")
                                    },
                                },
                                ensure_ascii=False,
                            ),
                        },
                    ],
                )
                needed = ("label", "definition", "source_iri", "target_iri")
                if not isinstance(raw, dict) or any(key not in raw for key in needed):
                    raise OntologyWriteError("融合失败")
                self._ontology.replace_relation_payload(
                    target_iri,
                    label=raw["label"],
                    definition=raw["definition"],
                    source_iri=raw["source_iri"],
                    target_object_iri=raw["target_iri"],
                )
                self._register(target_iri, raw["label"])
                return
        except StructuredOutputError as exc:
            raise OntologyWriteError("融合失败") from exc
        raise ValueError(stored.kind)

    def accept_type(
        self,
        candidate_id: str,
        *,
        mode: str = "create",
        target_iri: str | None = None,
    ) -> StoredTypeCandidate:
        stored = self._candidates.get_type(candidate_id)
        payload = stored.payload
        if stored.kind == "attribute":
            item = _take(OntoAttribute, payload, _ATTRIBUTE_FIELDS)
            self._ontology.create_attribute(item)
            self._register(item.iri, item.label)
            return self._candidates.set_type_status(candidate_id, "accepted")
        similar = _similar_iris(payload)
        resolved = mode or "create"
        if not similar:
            if resolved not in ("create",):
                raise OntologyWriteError("无相似项时只能新增")
            self._accept_create(stored)
            return self._candidates.set_type_status(candidate_id, "accepted")
        if resolved == "create":
            self._accept_create(stored)
            return self._candidates.set_type_status(candidate_id, "accepted")
        if resolved in ("overwrite", "merge"):
            kind_word = "对象" if stored.kind == "object" else "关系"
            if target_iri not in similar:
                raise OntologyWriteError(f"请选择要对齐的已有{kind_word}")
            if resolved == "overwrite":
                self._accept_overwrite(stored, target_iri)
            else:
                self._accept_merge(stored, target_iri)
            return self._candidates.set_type_status(candidate_id, "accepted")
        raise OntologyWriteError("无相似项时只能新增")

    def reject_type(self, candidate_id: str) -> StoredTypeCandidate:
        return self._candidates.set_type_status(candidate_id, "rejected")

    def project_job(self, job_id: str) -> dict:
        stored = [
            item
            for item in self._candidates.list_instance_candidates(job_id)
            if item.status == "proposed"
        ]
        instances = [
            _take(InstanceSuggestionDraft, item.payload, _INSTANCE_FIELDS)
            for item in stored
            if item.kind == "instance"
        ]
        rels = [
            _take(InstanceRelDraft, item.payload, _REL_FIELDS)
            for item in stored
            if item.kind == "instance_rel"
        ]
        try:
            projected, skipped = self._projector.project_instances(
                self._ontology.snapshot(),
                instances,
                rels,
                iri_prefix=NS,
            )
        except GraphUnavailable:
            self._jobs.set_status(job_id, "types_accepted_graph_pending")
            raise
        projected_set = set(projected)
        skipped_set = set(skipped)
        for item in stored:
            if item.kind == "instance":
                onto_iri = f"{NS}{item.payload['local_id']}"
                type_iri = item.payload["type_iri"]
                status = (
                    "skipped"
                    if f"{_SKIP_UNCONFIRMED_OBJECT}{type_iri}" in skipped_set
                    or onto_iri not in projected_set
                    else "projected"
                )
            else:
                predicate = item.payload["predicate_iri"]
                status = (
                    "skipped"
                    if f"{_SKIP_UNCONFIRMED_REL}{predicate}" in skipped_set
                    or f"{_SKIP_MISSING_ENDPOINT}{predicate}" in skipped_set
                    else "projected"
                )
            self._candidates.set_instance_status(item.id, status)
        return {"projected": projected, "skipped": skipped}

    def delete_object(self, iri: str) -> None:
        if self._graph.count_nodes_of_type(iri) > 0:
            raise ConflictError("仍有实例占用该对象")
        self._ontology.delete_object(iri)

    def delete_attribute(self, iri: str) -> None:
        if self._graph.count_nodes_with_attribute(iri) > 0:
            raise ConflictError("仍有实例占用该属性")
        self._ontology.delete_attribute(iri)

    def delete_relation(self, iri: str) -> None:
        if self._graph.count_rels_of_predicate(iri) > 0:
            raise ConflictError("仍有实例占用该关系")
        self._ontology.delete_relation(iri)
