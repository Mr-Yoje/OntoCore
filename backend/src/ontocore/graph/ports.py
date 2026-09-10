from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class GraphNode:
    onto_iri: str
    type_iri: str
    onto_label: str
    evidence: str
    block_id: str
    data: dict
    native_label: str = "OntoNode"


@dataclass
class GraphRel:
    rel_id: str
    source_iri: str
    target_iri: str
    predicate_iri: str
    onto_label: str
    evidence: str
    block_id: str
    native_label: str = "ONTO_REL"


@dataclass
class InstanceNetwork:
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphRel, ...]


class GraphRepository(Protocol):
    def upsert_node(self, node: GraphNode) -> None: ...
    def upsert_rel(self, rel: GraphRel) -> None: ...
    def get_node(self, onto_iri: str) -> GraphNode | None: ...
    def delete_node(self, onto_iri: str) -> None: ...
    def delete_rel(self, rel_id: str) -> None: ...
    def instance_network(self, type_iri: str | None = None) -> InstanceNetwork: ...
    def update_type_display(self, type_iri: str, onto_label: str) -> int: ...
    def count_nodes_of_type(self, type_iri: str) -> int: ...
    def count_rels_of_predicate(self, predicate_iri: str) -> int: ...
    def count_nodes_with_attribute(self, attr_iri: str) -> int: ...
