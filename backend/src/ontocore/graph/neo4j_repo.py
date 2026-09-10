from __future__ import annotations

import json
from collections.abc import Callable
from typing import TypeVar

from neo4j import GraphDatabase
from neo4j.exceptions import AuthError, DriverError, ServiceUnavailable, TransientError

from ontocore.errors import GraphUnavailable
from ontocore.graph.ports import GraphNode, GraphRel, InstanceNetwork

T = TypeVar("T")

_CONNECT_ERRORS = (
    AuthError,
    DriverError,
    ServiceUnavailable,
    TransientError,
    OSError,
    TimeoutError,
    ConnectionError,
)


def _graph_node(n) -> GraphNode:
    raw = n.get("data_json") or "{}"
    data = json.loads(raw) if isinstance(raw, str) else dict(raw)
    return GraphNode(
        onto_iri=n["onto_iri"],
        type_iri=n["type_iri"],
        onto_label=n["onto_label"],
        evidence=n["evidence"],
        block_id=n["block_id"],
        data=data,
        native_label="OntoNode",
    )


def _graph_rel(r, source_iri: str, target_iri: str) -> GraphRel:
    return GraphRel(
        rel_id=r["rel_id"],
        source_iri=source_iri,
        target_iri=target_iri,
        predicate_iri=r["predicate_iri"],
        onto_label=r["onto_label"],
        evidence=r["evidence"],
        block_id=r["block_id"],
        native_label="ONTO_REL",
    )


class Neo4jGraphRepository:
    def __init__(self, uri: str, user: str, password: str) -> None:
        self._uri = uri
        self._user = user
        self._password = password

    def _with_session(self, work: Callable) -> T:
        try:
            driver = GraphDatabase.driver(
                self._uri,
                auth=(self._user, self._password),
                connection_timeout=2.0,
            )
        except _CONNECT_ERRORS as exc:
            raise GraphUnavailable from exc
        try:
            with driver.session() as session:
                return work(session)
        except _CONNECT_ERRORS as exc:
            raise GraphUnavailable from exc
        finally:
            driver.close()

    def upsert_node(self, node: GraphNode) -> None:
        def work(session) -> None:
            session.run(
                """
                MERGE (n:OntoNode {onto_iri: $onto_iri})
                SET n.type_iri = $type_iri,
                    n.onto_label = $onto_label,
                    n.evidence = $evidence,
                    n.block_id = $block_id,
                    n.data_json = $data_json
                """,
                onto_iri=node.onto_iri,
                type_iri=node.type_iri,
                onto_label=node.onto_label,
                evidence=node.evidence,
                block_id=node.block_id,
                data_json=json.dumps(node.data, ensure_ascii=False),
            ).consume()

        self._with_session(work)

    def upsert_rel(self, rel: GraphRel) -> None:
        def work(session) -> None:
            session.run(
                """
                MATCH (s:OntoNode {onto_iri: $source_iri})
                MATCH (t:OntoNode {onto_iri: $target_iri})
                MERGE (s)-[r:ONTO_REL {rel_id: $rel_id}]->(t)
                SET r.predicate_iri = $predicate_iri,
                    r.onto_label = $onto_label,
                    r.evidence = $evidence,
                    r.block_id = $block_id
                """,
                source_iri=rel.source_iri,
                target_iri=rel.target_iri,
                rel_id=rel.rel_id,
                predicate_iri=rel.predicate_iri,
                onto_label=rel.onto_label,
                evidence=rel.evidence,
                block_id=rel.block_id,
            ).consume()

        self._with_session(work)

    def get_node(self, onto_iri: str) -> GraphNode | None:
        def work(session) -> GraphNode | None:
            rec = session.run(
                "MATCH (n:OntoNode {onto_iri: $onto_iri}) RETURN n",
                onto_iri=onto_iri,
            ).single()
            if rec is None:
                return None
            return _graph_node(rec["n"])

        return self._with_session(work)

    def delete_node(self, onto_iri: str) -> None:
        def work(session) -> None:
            session.run(
                "MATCH (n:OntoNode {onto_iri: $onto_iri}) DETACH DELETE n",
                onto_iri=onto_iri,
            ).consume()

        self._with_session(work)

    def delete_rel(self, rel_id: str) -> None:
        def work(session) -> None:
            session.run(
                "MATCH ()-[r:ONTO_REL {rel_id: $rel_id}]->() DELETE r",
                rel_id=rel_id,
            ).consume()

        self._with_session(work)

    def instance_network(self, type_iri: str | None = None) -> InstanceNetwork:
        def work(session) -> InstanceNetwork:
            if type_iri is None:
                node_recs = list(session.run("MATCH (n:OntoNode) RETURN n"))
            else:
                node_recs = list(
                    session.run(
                        "MATCH (n:OntoNode {type_iri: $type_iri}) RETURN n",
                        type_iri=type_iri,
                    )
                )
            nodes = tuple(_graph_node(rec["n"]) for rec in node_recs)
            iris = {node.onto_iri for node in nodes}
            rel_recs = list(
                session.run(
                    """
                    MATCH (s:OntoNode)-[r:ONTO_REL]->(t:OntoNode)
                    RETURN s.onto_iri AS source_iri, t.onto_iri AS target_iri, r
                    """
                )
            )
            edges = tuple(
                _graph_rel(rec["r"], rec["source_iri"], rec["target_iri"])
                for rec in rel_recs
                if rec["source_iri"] in iris and rec["target_iri"] in iris
            )
            return InstanceNetwork(nodes=nodes, edges=edges)

        return self._with_session(work)

    def update_type_display(self, type_iri: str, onto_label: str) -> int:
        def work(session) -> int:
            rec = session.run(
                "MATCH (n:OntoNode {type_iri: $t}) SET n.onto_label = $l RETURN count(n) AS c",
                t=type_iri,
                l=onto_label,
            ).single()
            return int(rec["c"]) if rec is not None else 0

        return self._with_session(work)

    def count_nodes_of_type(self, type_iri: str) -> int:
        def work(session) -> int:
            rec = session.run(
                "MATCH (n:OntoNode {type_iri: $type_iri}) RETURN count(n) AS c",
                type_iri=type_iri,
            ).single()
            return int(rec["c"]) if rec is not None else 0

        return self._with_session(work)

    def count_rels_of_predicate(self, predicate_iri: str) -> int:
        def work(session) -> int:
            rec = session.run(
                "MATCH ()-[r:ONTO_REL {predicate_iri: $predicate_iri}]->() RETURN count(r) AS c",
                predicate_iri=predicate_iri,
            ).single()
            return int(rec["c"]) if rec is not None else 0

        return self._with_session(work)

    def count_nodes_with_attribute(self, attr_iri: str) -> int:
        def work(session) -> int:
            recs = list(session.run("MATCH (n:OntoNode) RETURN n.data_json AS data_json"))
            count = 0
            for rec in recs:
                raw = rec["data_json"] or "{}"
                data = json.loads(raw) if isinstance(raw, str) else dict(raw)
                if attr_iri in data:
                    count += 1
            return count

        return self._with_session(work)
