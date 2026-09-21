from ontocore.constants import NS
from ontocore.extract.dedup import attach_similar
from ontocore.extract.llm import FakeLlmGateway
from ontocore.models import (
    ExtractionResult, ObjectCandidateDraft, OntoObject, OntoRelation,
    RelationCandidateDraft, TypeSnapshot,
)


def _obj(iri, label, definition="d"):
    return ObjectCandidateDraft(
        iri=iri, label=label, definition=definition, parent_iri=None,
        evidence="e", block_id="b0", confidence=0.5,
    )


def test_embed_keeps_top_five_then_one_judge_call():
    existing = [
        OntoObject(iri=f"{NS}E{i}", label=f"已有{i}", definition="d")
        for i in range(6)
    ]
    snap = TypeSnapshot(objects=tuple(existing), attributes=(), relations=())
    result = ExtractionResult(
        object_candidates=[_obj(f"{NS}New", "新品")],
        attribute_candidates=[], relation_candidates=[],
        instance_suggestions=[], instance_rel_suggestions=[],
    )
    embeddings = {f"已有{i} d": [1.0, float(i)] for i in range(6)}
    embeddings["新品 d"] = [1.0, 0.0]
    judge = {"object_similar": {f"{NS}New": [f"{NS}E0"]}, "relation_similar": {}}
    gw = FakeLlmGateway(judge, embeddings=embeddings)
    attach_similar(
        result, snap, gw,
        guide_object_iris=[], guide_relation_iris=[], use_embed=True,
    )
    assert len(gw.messages_log) == 1
    payload = __import__("json").loads(gw.messages_log[0][1]["content"])
    assert len(payload["new_objects"][0]["candidates"]) == 5
    assert result.object_candidates[0].similar_to[0].iri == f"{NS}E0"


def test_no_embed_sends_all_unselected_to_judge():
    snap = TypeSnapshot(
        objects=(
            OntoObject(iri=f"{NS}Keep", label="引导对象", definition="d"),
            OntoObject(iri=f"{NS}Other", label="其它", definition="d"),
        ),
        attributes=(), relations=(),
    )
    result = ExtractionResult(
        object_candidates=[_obj(f"{NS}New", "新品")],
        attribute_candidates=[], relation_candidates=[],
        instance_suggestions=[], instance_rel_suggestions=[],
    )
    gw = FakeLlmGateway({"object_similar": {f"{NS}New": [f"{NS}Other"]}, "relation_similar": {}})
    attach_similar(
        result, snap, gw,
        guide_object_iris=[f"{NS}Keep"], guide_relation_iris=[], use_embed=False,
    )
    payload = __import__("json").loads(gw.messages_log[0][1]["content"])
    iris = {c["iri"] for c in payload["new_objects"][0]["candidates"]}
    assert f"{NS}Other" in iris
    assert f"{NS}Keep" not in iris
