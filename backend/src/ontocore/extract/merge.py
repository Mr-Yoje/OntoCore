from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import replace

from ontocore.errors import StructuredOutputError
from ontocore.extract.dedup import cosine
from ontocore.extract.llm import LlmGateway
from ontocore.models import (
    AttributeCandidateDraft,
    ExtractionResult,
    ObjectCandidateDraft,
    RelationCandidateDraft,
)

EMBED_MERGE_THRESHOLD = 0.85

_WHITESPACE = re.compile(r"\s+")

_STR = {"type": "string"}
_STR_NULL = {"type": ["string", "null"]}

OBJECT_MERGE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "label": _STR,
        "definition": _STR,
        "parent_iri": _STR_NULL,
        "evidence": _STR,
        "attributes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": _STR,
                    "definition": _STR,
                    "literal_kind": {"type": "string", "enum": ["text", "number", "date"]},
                },
                "required": ["label", "definition", "literal_kind"],
            },
        },
    },
    "required": ["label", "definition", "parent_iri", "evidence", "attributes"],
}

RELATION_MERGE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "label": _STR,
        "definition": _STR,
        "source_iri": _STR,
        "target_iri": _STR,
        "evidence": _STR,
    },
    "required": ["label", "definition", "source_iri", "target_iri", "evidence"],
}

_OBJECT_MERGE_SYSTEM = (
    "合并同义对象草稿为一条。保留各成员定义与证据要点；输出含属性列表。"
    "不得只复述其中一条。"
)
_RELATION_MERGE_SYSTEM = (
    "合并同义关系草稿为一条。保留各成员定义与证据要点；不得只复述其中一条。"
)


def normalize_label(label: str) -> str:
    """strip; collapse whitespace; ASCII casefold."""
    return _WHITESPACE.sub(" ", label.strip()).casefold()


def _embed_text(item: ObjectCandidateDraft | RelationCandidateDraft) -> str:
    return f"{item.label} {item.definition}"


def _vector_for(
    draft: ObjectCandidateDraft | RelationCandidateDraft,
    vectors: dict[str, list[float]],
) -> list[float] | None:
    return vectors.get(draft.iri) or vectors.get(_embed_text(draft))


class _UnionFind:
    def __init__(self, keys: list[str]) -> None:
        self._parent = {key: key for key in keys}

    def find(self, key: str) -> str:
        while self._parent[key] != key:
            self._parent[key] = self._parent[self._parent[key]]
            key = self._parent[key]
        return key

    def union(self, a: str, b: str) -> None:
        root_a = self.find(a)
        root_b = self.find(b)
        if root_a != root_b:
            self._parent[root_b] = root_a


def _pick_representative(
    drafts: list[ObjectCandidateDraft] | list[RelationCandidateDraft],
) -> ObjectCandidateDraft | RelationCandidateDraft:
    return max(drafts, key=lambda d: (d.confidence, d.iri))


def _merge_by_embed(
    cluster_ids: list[str],
    clusters: dict[str, list[ObjectCandidateDraft] | list[RelationCandidateDraft]],
    vectors: dict[str, list[float]],
) -> list[list[ObjectCandidateDraft] | list[RelationCandidateDraft]]:
    reps = {cid: _pick_representative(clusters[cid]) for cid in cluster_ids}
    uf = _UnionFind(cluster_ids)
    for i, cid_a in enumerate(cluster_ids):
        vec_a = _vector_for(reps[cid_a], vectors)
        if vec_a is None:
            continue
        for cid_b in cluster_ids[i + 1 :]:
            vec_b = _vector_for(reps[cid_b], vectors)
            if vec_b is None:
                continue
            if cosine(vec_a, vec_b) >= EMBED_MERGE_THRESHOLD:
                uf.union(cid_a, cid_b)

    merged: dict[str, list] = {}
    for cid in cluster_ids:
        root = uf.find(cid)
        merged.setdefault(root, []).extend(clusters[cid])
    return list(merged.values())


def cluster_objects(
    drafts: list[ObjectCandidateDraft],
    vectors: dict[str, list[float]] | None,
) -> list[list[ObjectCandidateDraft]]:
    """Same normalize_label -> one cluster; else cosine >= 0.85 merges (union-find)."""
    buckets: dict[str, list[ObjectCandidateDraft]] = {}
    for draft in drafts:
        key = normalize_label(draft.label)
        buckets.setdefault(key, []).append(draft)

    if not buckets:
        return []

    if vectors is None:
        return list(buckets.values())

    return _merge_by_embed(list(buckets.keys()), buckets, vectors)


def _remap_iri(iri: str, mapping: dict[str, str]) -> str:
    return mapping.get(iri, iri)


def cluster_relations(
    drafts: list[RelationCandidateDraft],
    object_iri_map: dict[str, str],
    vectors: dict[str, list[float]] | None,
) -> list[list[RelationCandidateDraft]]:
    """Remap endpoints via object_iri_map; cluster by (norm label, src, tgt) or embed."""
    buckets: dict[tuple[str, str, str], list[RelationCandidateDraft]] = {}
    for draft in drafts:
        src = _remap_iri(draft.source_iri, object_iri_map)
        tgt = _remap_iri(draft.target_iri, object_iri_map)
        key = (normalize_label(draft.label), src, tgt)
        buckets.setdefault(key, []).append(draft)

    if not buckets:
        return []

    if vectors is None:
        return list(buckets.values())

    return _merge_by_embed(list(buckets.keys()), buckets, vectors)


def _build_vectors(
    objects: list[ObjectCandidateDraft],
    relations: list[RelationCandidateDraft],
    embed: Callable[[list[str]], list[list[float]]],
) -> dict[str, list[float]]:
    drafts: list[ObjectCandidateDraft | RelationCandidateDraft] = [*objects, *relations]
    if not drafts:
        return {}
    texts = [_embed_text(d) for d in drafts]
    vecs = embed(texts)
    return {d.iri: vec for d, vec in zip(drafts, vecs)}


def _object_member_payload(
    draft: ObjectCandidateDraft,
    attributes: list[AttributeCandidateDraft],
) -> dict:
    owned = [a for a in attributes if a.owner_iri == draft.iri]
    return {
        "iri": draft.iri,
        "label": draft.label,
        "definition": draft.definition,
        "parent_iri": draft.parent_iri,
        "evidence": draft.evidence,
        "confidence": draft.confidence,
        "attributes": [
            {
                "label": a.label,
                "definition": a.definition,
                "literal_kind": a.literal_kind,
                "evidence": a.evidence,
            }
            for a in owned
        ],
    }


def _relation_member_payload(
    draft: RelationCandidateDraft,
    object_iri_map: dict[str, str],
) -> dict:
    return {
        "iri": draft.iri,
        "label": draft.label,
        "definition": draft.definition,
        "source_iri": _remap_iri(draft.source_iri, object_iri_map),
        "target_iri": _remap_iri(draft.target_iri, object_iri_map),
        "evidence": draft.evidence,
        "confidence": draft.confidence,
    }


def _merge_object_cluster(
    cluster: list[ObjectCandidateDraft],
    attributes: list[AttributeCandidateDraft],
    llm: LlmGateway,
) -> tuple[ObjectCandidateDraft, bool]:
    rep = _pick_representative(cluster)
    assert isinstance(rep, ObjectCandidateDraft)
    members = [_object_member_payload(d, attributes) for d in cluster]
    messages = [
        {"role": "system", "content": _OBJECT_MERGE_SYSTEM},
        {"role": "user", "content": json.dumps({"members": members}, ensure_ascii=False)},
    ]
    try:
        payload = llm.complete_structured(OBJECT_MERGE_SCHEMA, messages)
        if not isinstance(payload, dict):
            raise StructuredOutputError("object merge payload is not an object")
        return (
            ObjectCandidateDraft(
                iri=rep.iri,
                label=str(payload.get("label") or rep.label),
                definition=str(payload.get("definition") or rep.definition),
                parent_iri=payload.get("parent_iri", rep.parent_iri),
                evidence=str(payload.get("evidence") or rep.evidence),
                block_id=rep.block_id,
                confidence=rep.confidence,
                similar_to=list(rep.similar_to),
            ),
            False,
        )
    except StructuredOutputError:
        return rep, True


def _merge_relation_cluster(
    cluster: list[RelationCandidateDraft],
    object_iri_map: dict[str, str],
    llm: LlmGateway,
) -> tuple[RelationCandidateDraft, bool]:
    rep = _pick_representative(cluster)
    assert isinstance(rep, RelationCandidateDraft)
    members = [_relation_member_payload(d, object_iri_map) for d in cluster]
    messages = [
        {"role": "system", "content": _RELATION_MERGE_SYSTEM},
        {"role": "user", "content": json.dumps({"members": members}, ensure_ascii=False)},
    ]
    src = _remap_iri(rep.source_iri, object_iri_map)
    tgt = _remap_iri(rep.target_iri, object_iri_map)
    try:
        payload = llm.complete_structured(RELATION_MERGE_SCHEMA, messages)
        if not isinstance(payload, dict):
            raise StructuredOutputError("relation merge payload is not an object")
        return (
            RelationCandidateDraft(
                iri=rep.iri,
                label=str(payload.get("label") or rep.label),
                definition=str(payload.get("definition") or rep.definition),
                source_iri=_remap_iri(str(payload.get("source_iri") or src), object_iri_map),
                target_iri=_remap_iri(str(payload.get("target_iri") or tgt), object_iri_map),
                evidence=str(payload.get("evidence") or rep.evidence),
                block_id=rep.block_id,
                confidence=rep.confidence,
                similar_to=list(rep.similar_to),
            ),
            False,
        )
    except StructuredOutputError:
        return (
            replace(rep, source_iri=src, target_iri=tgt),
            True,
        )


def merge_extraction_result(
    result: ExtractionResult,
    llm: LlmGateway,
    *,
    embed: Callable[[list[str]], list[list[float]]] | None,
    on_cluster_done: Callable[[int, int], None] | None = None,
) -> tuple[ExtractionResult, bool]:
    """
    Returns (merged_result, had_merge_failures).
    - Build vectors if embed provided (label+definition texts).
    - Cluster objects; for len>=2 call llm once; pick representative iri (max confidence).
    - Build object_iri_map old->rep; rewrite attribute owner_iri, instance type_iri, instance_rel endpoints.
    - Cluster relations with map; merge len>=2.
    - on_cluster_done(done, total) where total = number of clusters with len>=2
      (object multi-clusters + relation multi-clusters).
    - Merge failure: keep highest-confidence member of cluster; had_merge_failures=True.
    """
    objects = list(result.object_candidates)
    relations = list(result.relation_candidates)
    attributes = list(result.attribute_candidates)

    vectors: dict[str, list[float]] | None = None
    if embed is not None:
        vectors = _build_vectors(objects, relations, embed)

    object_clusters = cluster_objects(objects, vectors)
    object_iri_map: dict[str, str] = {}
    for cluster in object_clusters:
        rep = _pick_representative(cluster)
        for draft in cluster:
            object_iri_map[draft.iri] = rep.iri

    relation_clusters = cluster_relations(relations, object_iri_map, vectors)
    total = sum(1 for c in object_clusters if len(c) >= 2) + sum(
        1 for c in relation_clusters if len(c) >= 2
    )
    done = 0
    had_merge_failures = False

    def _with_remapped_parent(obj: ObjectCandidateDraft) -> ObjectCandidateDraft:
        if obj.parent_iri is None:
            return obj
        return replace(obj, parent_iri=_remap_iri(obj.parent_iri, object_iri_map))

    merged_objects: list[ObjectCandidateDraft] = []
    for cluster in object_clusters:
        if len(cluster) == 1:
            merged_objects.append(_with_remapped_parent(cluster[0]))
            continue
        merged_obj, failed = _merge_object_cluster(cluster, attributes, llm)
        had_merge_failures = had_merge_failures or failed
        merged_objects.append(_with_remapped_parent(merged_obj))
        done += 1
        if on_cluster_done is not None:
            on_cluster_done(done, total)

    merged_relations: list[RelationCandidateDraft] = []
    for cluster in relation_clusters:
        if len(cluster) == 1:
            only = cluster[0]
            merged_relations.append(
                replace(
                    only,
                    source_iri=_remap_iri(only.source_iri, object_iri_map),
                    target_iri=_remap_iri(only.target_iri, object_iri_map),
                )
            )
            continue
        merged_rel, failed = _merge_relation_cluster(cluster, object_iri_map, llm)
        had_merge_failures = had_merge_failures or failed
        merged_relations.append(merged_rel)
        done += 1
        if on_cluster_done is not None:
            on_cluster_done(done, total)

    merged_attributes = [
        replace(attr, owner_iri=_remap_iri(attr.owner_iri, object_iri_map))
        for attr in attributes
    ]
    merged_instances = [
        replace(inst, type_iri=_remap_iri(inst.type_iri, object_iri_map))
        for inst in result.instance_suggestions
    ]
    # InstanceRelDraft endpoints are instance local_ids; predicate_iri may point at
    # a relation type — no object_iri_map rewrite applies this round.
    merged_instance_rels = list(result.instance_rel_suggestions)

    return (
        ExtractionResult(
            object_candidates=merged_objects,
            attribute_candidates=merged_attributes,
            relation_candidates=merged_relations,
            instance_suggestions=merged_instances,
            instance_rel_suggestions=merged_instance_rels,
            block_failures=list(result.block_failures),
        ),
        had_merge_failures,
    )
