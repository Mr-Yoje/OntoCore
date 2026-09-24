from __future__ import annotations

import json
import math
from collections.abc import Callable

from ontocore.errors import StructuredOutputError
from ontocore.extract.llm import LlmGateway
from ontocore.models import (
    ExtractionResult,
    ObjectCandidateDraft,
    OntoObject,
    OntoRelation,
    RelationCandidateDraft,
    SimilarRef,
    TypeSnapshot,
)

_JUDGE_SYSTEM = "判断新建议与对照项是否同一含义。只输出确认为相似的已有编号。"

_JUDGE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "object_similar": {"type": "object"},
        "relation_similar": {"type": "object"},
    },
    "required": ["object_similar", "relation_similar"],
}


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / math.sqrt(na * nb)


def _embed_text(item: OntoObject | OntoRelation | ObjectCandidateDraft | RelationCandidateDraft) -> str:
    return f"{item.label} {item.definition}"


def _as_candidate(item: OntoObject | OntoRelation) -> dict:
    return {"iri": item.iri, "label": item.label, "definition": item.definition}


def _new_payload(item: ObjectCandidateDraft | RelationCandidateDraft, candidates: list) -> dict:
    return {
        "key": item.iri,
        "label": item.label,
        "definition": item.definition,
        "evidence": item.evidence,
        "candidates": [_as_candidate(c) for c in candidates],
    }


def _top5(
    query: ObjectCandidateDraft | RelationCandidateDraft,
    pool: list,
    vectors: dict[str, list[float]],
) -> list:
    qv = vectors[_embed_text(query)]
    ranked = sorted(
        pool,
        key=lambda item: cosine(qv, vectors[_embed_text(item)]),
        reverse=True,
    )
    return ranked[:5]


def attach_similar(
    result: ExtractionResult,
    snapshot: TypeSnapshot,
    llm: LlmGateway,
    *,
    guide_object_iris: list[str],
    guide_relation_iris: list[str],
    use_embed: bool,
    on_embed_finished: Callable[[], None] | None = None,
) -> None:
    if not result.object_candidates and not result.relation_candidates:
        return
    guide_objects = set(guide_object_iris)
    guide_relations = set(guide_relation_iris)
    unselected_objects = [o for o in snapshot.objects if o.iri not in guide_objects]
    unselected_relations = [r for r in snapshot.relations if r.iri not in guide_relations]
    if not unselected_objects and not unselected_relations:
        return

    embed_ok = use_embed
    vectors: dict[str, list[float]] = {}
    if use_embed:
        texts: list[str] = []
        for item in (
            *result.object_candidates,
            *unselected_objects,
            *result.relation_candidates,
            *unselected_relations,
        ):
            texts.append(_embed_text(item))
        try:
            embedded = llm.embed(texts)
        except Exception:
            embed_ok = False
        else:
            for text, vec in zip(texts, embedded):
                vectors[text] = vec
    if on_embed_finished is not None:
        on_embed_finished()

    new_objects = []
    object_candidate_sets: dict[str, set[str]] = {}
    for draft in result.object_candidates:
        pool = (
            _top5(draft, unselected_objects, vectors)
            if embed_ok
            else unselected_objects
        )
        object_candidate_sets[draft.iri] = {c.iri for c in pool}
        new_objects.append(_new_payload(draft, pool))

    new_relations = []
    relation_candidate_sets: dict[str, set[str]] = {}
    for draft in result.relation_candidates:
        pool = (
            _top5(draft, unselected_relations, vectors)
            if embed_ok
            else unselected_relations
        )
        relation_candidate_sets[draft.iri] = {c.iri for c in pool}
        new_relations.append(_new_payload(draft, pool))

    payload = {"new_objects": new_objects, "new_relations": new_relations}
    messages = [
        {"role": "system", "content": _JUDGE_SYSTEM},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    judged = llm.complete_structured(_JUDGE_SCHEMA, messages)
    if (
        not isinstance(judged, dict)
        or "object_similar" not in judged
        or "relation_similar" not in judged
        or not isinstance(judged.get("object_similar"), dict)
        or not isinstance(judged.get("relation_similar"), dict)
    ):
        raise StructuredOutputError(code="OC-3103")

    object_labels = {o.iri: o.label for o in snapshot.objects}
    relation_labels = {r.iri: r.label for r in snapshot.relations}
    object_similar = judged.get("object_similar") or {}
    relation_similar = judged.get("relation_similar") or {}

    for draft in result.object_candidates:
        allowed = object_candidate_sets.get(draft.iri, set())
        picked = [
            iri
            for iri in object_similar.get(draft.iri, [])
            if iri in allowed
        ]
        draft.similar_to = [SimilarRef(iri=iri, label=object_labels[iri]) for iri in picked]

    for draft in result.relation_candidates:
        allowed = relation_candidate_sets.get(draft.iri, set())
        picked = [
            iri
            for iri in relation_similar.get(draft.iri, [])
            if iri in allowed
        ]
        draft.similar_to = [SimilarRef(iri=iri, label=relation_labels[iri]) for iri in picked]
