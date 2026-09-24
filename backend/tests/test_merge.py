from ontocore.extract.llm import FakeLlmGateway
from ontocore.extract.merge import (
    EMBED_MERGE_THRESHOLD,
    cluster_objects,
    cluster_relations,
    merge_extraction_result,
    normalize_label,
)
from ontocore.models import (
    AttributeCandidateDraft,
    ExtractionResult,
    ObjectCandidateDraft,
    RelationCandidateDraft,
)


def _empty_result(**kwargs) -> ExtractionResult:
    base = dict(
        object_candidates=[],
        attribute_candidates=[],
        relation_candidates=[],
        instance_suggestions=[],
        instance_rel_suggestions=[],
    )
    base.update(kwargs)
    return ExtractionResult(**base)


def test_normalize_label_collapses_space_and_case():
    assert normalize_label("  Foo   BAR ") == "foo bar"


def test_cluster_objects_by_same_normalized_name():
    a = ObjectCandidateDraft(
        iri="n1",
        label="泵",
        definition="d1",
        parent_iri=None,
        evidence="e1",
        block_id="b0",
        confidence=0.9,
    )
    b = ObjectCandidateDraft(
        iri="n2",
        label="泵",
        definition="d2",
        parent_iri=None,
        evidence="e2",
        block_id="b1",
        confidence=0.8,
    )
    clusters = cluster_objects([a, b], None)
    assert len(clusters) == 1 and {x.iri for x in clusters[0]} == {"n1", "n2"}


def test_cluster_objects_by_normalized_case():
    a = ObjectCandidateDraft(
        iri="n1",
        label="Foo Bar",
        definition="d1",
        parent_iri=None,
        evidence="e1",
        block_id="b0",
        confidence=0.9,
    )
    b = ObjectCandidateDraft(
        iri="n2",
        label="  foo   bar  ",
        definition="d2",
        parent_iri=None,
        evidence="e2",
        block_id="b1",
        confidence=0.8,
    )
    clusters = cluster_objects([a, b], None)
    assert len(clusters) == 1 and {x.iri for x in clusters[0]} == {"n1", "n2"}


def test_cluster_objects_by_embed_threshold():
    a = ObjectCandidateDraft(
        iri="n1",
        label="Alpha",
        definition="d1",
        parent_iri=None,
        evidence="e1",
        block_id="b0",
        confidence=0.9,
    )
    b = ObjectCandidateDraft(
        iri="n2",
        label="Beta",
        definition="d2",
        parent_iri=None,
        evidence="e2",
        block_id="b1",
        confidence=0.8,
    )
    vec = [1.0, 0.0, 0.0]
    clusters = cluster_objects([a, b], {"n1": vec, "n2": vec})
    assert len(clusters) == 1 and {x.iri for x in clusters[0]} == {"n1", "n2"}


def test_cluster_objects_embed_below_threshold_stays_separate():
    a = ObjectCandidateDraft(
        iri="n1",
        label="Alpha",
        definition="d1",
        parent_iri=None,
        evidence="e1",
        block_id="b0",
        confidence=0.9,
    )
    b = ObjectCandidateDraft(
        iri="n2",
        label="Beta",
        definition="d2",
        parent_iri=None,
        evidence="e2",
        block_id="b1",
        confidence=0.8,
    )
    clusters = cluster_objects([a, b], {"n1": [1.0, 0.0], "n2": [0.0, 1.0]})
    assert len(clusters) == 2


def test_cluster_relations_by_remapped_endpoints():
    a = RelationCandidateDraft(
        iri="r1",
        label="连接",
        definition="d1",
        source_iri="o1",
        target_iri="o3",
        evidence="e1",
        block_id="b0",
        confidence=0.9,
    )
    b = RelationCandidateDraft(
        iri="r2",
        label="连接",
        definition="d2",
        source_iri="o2",
        target_iri="o4",
        evidence="e2",
        block_id="b1",
        confidence=0.8,
    )
    object_iri_map = {"o1": "o_rep", "o2": "o_rep", "o3": "o_rep", "o4": "o_rep"}
    clusters = cluster_relations([a, b], object_iri_map, None)
    assert len(clusters) == 1 and {x.iri for x in clusters[0]} == {"r1", "r2"}


def test_cluster_relations_by_embed_threshold():
    a = RelationCandidateDraft(
        iri="r1",
        label="AlphaRel",
        definition="d1",
        source_iri="o1",
        target_iri="o2",
        evidence="e1",
        block_id="b0",
        confidence=0.9,
    )
    b = RelationCandidateDraft(
        iri="r2",
        label="BetaRel",
        definition="d2",
        source_iri="o3",
        target_iri="o4",
        evidence="e2",
        block_id="b1",
        confidence=0.8,
    )
    vec = [0.5, 0.5, 0.5]
    clusters = cluster_relations([a, b], {}, {"r1": vec, "r2": vec})
    assert len(clusters) == 1 and {x.iri for x in clusters[0]} == {"r1", "r2"}


def test_embed_merge_threshold_constant():
    assert EMBED_MERGE_THRESHOLD == 0.85


def test_merge_same_name_objects_one_llm_call_and_rewrite_attr():
    o1 = ObjectCandidateDraft(
        iri="n1",
        label="泵",
        definition="d1",
        parent_iri=None,
        evidence="e1",
        block_id="b0",
        confidence=0.9,
    )
    o2 = ObjectCandidateDraft(
        iri="n2",
        label="泵",
        definition="d2",
        parent_iri=None,
        evidence="e2",
        block_id="b1",
        confidence=0.8,
    )
    attr = AttributeCandidateDraft(
        iri="a1",
        label="功率",
        definition="ad",
        owner_iri="n2",
        literal_kind="number",
        evidence="ae",
        block_id="b1",
        confidence=0.7,
    )
    result = _empty_result(object_candidates=[o1, o2], attribute_candidates=[attr])
    gw = FakeLlmGateway(
        {
            "label": "泵",
            "definition": "merged",
            "parent_iri": None,
            "evidence": "e1; e2",
            "attributes": [{"label": "功率", "definition": "ad", "literal_kind": "number"}],
        }
    )

    merged, failed = merge_extraction_result(result, gw, embed=None)

    assert failed is False
    assert len(gw.messages_log) == 1
    assert len(merged.object_candidates) == 1
    assert merged.object_candidates[0].iri == "n1"
    assert merged.object_candidates[0].definition == "merged"
    assert len(merged.attribute_candidates) == 1
    assert merged.attribute_candidates[0].owner_iri == "n1"


def test_merge_by_embed_one_llm_call():
    o1 = ObjectCandidateDraft(
        iri="n1",
        label="Alpha",
        definition="d1",
        parent_iri=None,
        evidence="e1",
        block_id="b0",
        confidence=0.9,
    )
    o2 = ObjectCandidateDraft(
        iri="n2",
        label="Beta",
        definition="d2",
        parent_iri=None,
        evidence="e2",
        block_id="b1",
        confidence=0.8,
    )
    result = _empty_result(object_candidates=[o1, o2])
    vec = [1.0, 0.0, 0.0]

    def embed(texts: list[str]) -> list[list[float]]:
        return [vec for _ in texts]

    gw = FakeLlmGateway(
        {
            "label": "Alpha",
            "definition": "merged",
            "parent_iri": None,
            "evidence": "e1; e2",
            "attributes": [],
        }
    )

    merged, failed = merge_extraction_result(result, gw, embed=embed)

    assert failed is False
    assert len(gw.messages_log) == 1
    assert len(merged.object_candidates) == 1
    assert merged.object_candidates[0].iri == "n1"


def test_merge_llm_failure_keeps_max_confidence_and_progress():
    o1 = ObjectCandidateDraft(
        iri="n1",
        label="泵",
        definition="d1",
        parent_iri=None,
        evidence="e1",
        block_id="b0",
        confidence=0.9,
    )
    o2 = ObjectCandidateDraft(
        iri="n2",
        label="泵",
        definition="d2",
        parent_iri=None,
        evidence="e2",
        block_id="b1",
        confidence=0.8,
    )
    result = _empty_result(object_candidates=[o1, o2])
    gw = FakeLlmGateway([{"__error__": True}])
    progress: list[tuple[int, int]] = []

    merged, failed = merge_extraction_result(
        result,
        gw,
        embed=None,
        on_cluster_done=lambda done, total: progress.append((done, total)),
    )

    assert failed is True
    assert len(merged.object_candidates) == 1
    assert merged.object_candidates[0].iri == "n1"
    assert merged.object_candidates[0].definition == "d1"
    assert progress == [(1, 1)]
