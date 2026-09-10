from __future__ import annotations

from dataclasses import fields

from ontocore.candidates.store import CandidateStore, StoredTypeCandidate
from ontocore.constants import NS
from ontocore.errors import ConflictError, GraphUnavailable
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


def _take(cls, payload: dict, allowed: set[str]):
    return cls(**{key: value for key, value in payload.items() if key in allowed})


class ReviewService:
    def __init__(self, candidates, ontology, projector, jobs, graph) -> None:
        self._candidates: CandidateStore = candidates
        self._ontology: OntologyRepository = ontology
        self._projector: Projector = projector
        self._jobs: JobStore = jobs
        self._graph: GraphRepository = graph

    def accept_type(self, candidate_id: str) -> StoredTypeCandidate:
        stored = self._candidates.get_type(candidate_id)
        payload = stored.payload
        if stored.kind == "object":
            item = _take(OntoObject, payload, _OBJECT_FIELDS)
            self._ontology.create_object(item)
            self._projector.register_type(item.iri, item.label)
        elif stored.kind == "attribute":
            item = _take(OntoAttribute, payload, _ATTRIBUTE_FIELDS)
            self._ontology.create_attribute(item)
            self._projector.register_type(item.iri, item.label)
        elif stored.kind == "relation":
            item = _take(OntoRelation, payload, _RELATION_FIELDS)
            self._ontology.create_relation(item)
            self._projector.register_type(item.iri, item.label)
        else:
            raise ValueError(stored.kind)
        return self._candidates.set_type_status(candidate_id, "accepted")

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
