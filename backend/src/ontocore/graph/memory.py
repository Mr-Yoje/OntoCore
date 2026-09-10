from __future__ import annotations

from ontocore.graph.ports import GraphNode, GraphRel, InstanceNetwork


class MemoryGraphRepository:
    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._rels: dict[str, GraphRel] = {}

    def upsert_node(self, node: GraphNode) -> None:
        self._nodes[node.onto_iri] = node

    def upsert_rel(self, rel: GraphRel) -> None:
        self._rels[rel.rel_id] = rel

    def get_node(self, onto_iri: str) -> GraphNode | None:
        return self._nodes.get(onto_iri)

    def delete_node(self, onto_iri: str) -> None:
        self._nodes.pop(onto_iri, None)
        stale = [
            rel_id
            for rel_id, rel in self._rels.items()
            if rel.source_iri == onto_iri or rel.target_iri == onto_iri
        ]
        for rel_id in stale:
            del self._rels[rel_id]

    def delete_rel(self, rel_id: str) -> None:
        self._rels.pop(rel_id, None)

    def instance_network(self, type_iri: str | None = None) -> InstanceNetwork:
        nodes = tuple(
            node
            for node in self._nodes.values()
            if type_iri is None or node.type_iri == type_iri
        )
        iris = {node.onto_iri for node in nodes}
        edges = tuple(
            rel
            for rel in self._rels.values()
            if rel.source_iri in iris and rel.target_iri in iris
        )
        return InstanceNetwork(nodes=nodes, edges=edges)

    def update_type_display(self, type_iri: str, onto_label: str) -> int:
        updated = 0
        for node in self._nodes.values():
            if node.type_iri == type_iri:
                node.onto_label = onto_label
                updated += 1
        return updated

    def count_nodes_of_type(self, type_iri: str) -> int:
        return sum(1 for node in self._nodes.values() if node.type_iri == type_iri)

    def count_rels_of_predicate(self, predicate_iri: str) -> int:
        return sum(1 for rel in self._rels.values() if rel.predicate_iri == predicate_iri)

    def count_nodes_with_attribute(self, attr_iri: str) -> int:
        return sum(1 for node in self._nodes.values() if attr_iri in node.data)
