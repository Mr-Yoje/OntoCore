from __future__ import annotations

import hashlib

from ontocore.graph.ports import GraphNode, GraphRel, GraphRepository
from ontocore.models import InstanceRelDraft, InstanceSuggestionDraft, TypeSnapshot


class Projector:
    def __init__(self, graph: GraphRepository) -> None:
        self._graph = graph
        self._labels: dict[str, str] = {}

    def register_type(self, type_iri: str, display_label: str) -> None:
        self._labels[type_iri] = display_label

    def display_label(self, type_iri: str) -> str:
        return self._labels[type_iri]

    def project_instances(
        self,
        snapshot: TypeSnapshot,
        instances: list[InstanceSuggestionDraft],
        rels: list[InstanceRelDraft],
        *,
        iri_prefix: str,
    ) -> tuple[list[str], list[str]]:
        confirmed_objects = {obj.iri: obj for obj in snapshot.objects}
        confirmed_relations = {rel.iri: rel for rel in snapshot.relations}
        projected: list[str] = []
        skipped: list[str] = []
        projected_set: set[str] = set()

        for inst in instances:
            if inst.type_iri not in confirmed_objects:
                skipped.append(f"对象未确认：{inst.type_iri}")
                continue
            onto_iri = f"{iri_prefix}{inst.local_id}"
            onto_label = self._labels.get(
                inst.type_iri, confirmed_objects[inst.type_iri].label
            )
            self._graph.upsert_node(
                GraphNode(
                    onto_iri=onto_iri,
                    type_iri=inst.type_iri,
                    onto_label=onto_label,
                    evidence=inst.evidence,
                    block_id=inst.block_id,
                    data=inst.data,
                )
            )
            projected.append(onto_iri)
            projected_set.add(onto_iri)

        for rel in rels:
            if rel.predicate_iri not in confirmed_relations:
                skipped.append(f"关系未确认：{rel.predicate_iri}")
                continue
            source_iri = f"{iri_prefix}{rel.source_local_id}"
            target_iri = f"{iri_prefix}{rel.target_local_id}"
            if (
                source_iri not in projected_set
                and self._graph.get_node(source_iri) is None
            ) or (
                target_iri not in projected_set
                and self._graph.get_node(target_iri) is None
            ):
                skipped.append(f"关系端点未投影：{rel.predicate_iri}")
                continue
            onto_rel = confirmed_relations[rel.predicate_iri]
            key = f"{source_iri}\0{target_iri}\0{rel.predicate_iri}"
            rel_id = hashlib.sha256(key.encode("utf-8")).hexdigest()
            self._graph.upsert_rel(
                GraphRel(
                    rel_id=rel_id,
                    source_iri=source_iri,
                    target_iri=target_iri,
                    predicate_iri=rel.predicate_iri,
                    onto_label=onto_rel.label,
                    evidence=rel.evidence,
                    block_id=rel.block_id,
                )
            )

        return projected, skipped

    def sync_object_label(self, type_iri: str, label: str) -> None:
        self.register_type(type_iri, label)
        self._graph.update_type_display(type_iri, label)
