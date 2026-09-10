from ontocore.graph.neo4j_repo import Neo4jGraphRepository
from ontocore.errors import GraphUnavailable


def test_unavailable_on_bad_uri():
    repo = Neo4jGraphRepository("bolt://127.0.0.1:1", "neo4j", "test")
    try:
        repo.instance_network()
    except GraphUnavailable:
        return
    raise AssertionError("expected GraphUnavailable")
