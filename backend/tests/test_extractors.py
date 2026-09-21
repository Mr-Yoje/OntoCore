import inspect
from ontocore.constants import NS
from ontocore.extract.llm import FakeLlmGateway
from ontocore.extract.registry import get_extractor
from ontocore.models import OntoObject, ParsedDocument, TextBlock, TypeSnapshot


def test_extract_signature_has_no_domain_pack():
    sig = inspect.signature(get_extractor("hybrid").extract)
    assert "domain" not in sig.parameters
    assert "domain_pack" not in sig.parameters


def test_llm_only_with_fake():
    canned = {
        "object_candidates": [],
        "attribute_candidates": [],
        "relation_candidates": [],
        "instance_suggestions": [{
            "local_id": "i1", "type_iri": f"{NS}Product", "label": "尊享",
            "data": {}, "evidence": "尊享医疗保险", "block_id": "b0", "confidence": 0.8,
        }],
        "instance_rel_suggestions": [],
    }
    doc = ParsedDocument("a.txt", "尊享医疗保险", (TextBlock("b0", "paragraph", "尊享医疗保险"),))
    snap = TypeSnapshot(objects=(OntoObject(iri=f"{NS}Product", label="保险产品", definition="d"),), attributes=(), relations=())
    result = get_extractor("llm_only").extract(doc, snap, FakeLlmGateway(canned))
    assert result.instance_suggestions[0].label == "尊享"


def test_llm_only_invalid_draft_becomes_block_failure():
    canned = {
        "object_candidates": [{"label": "残缺", "block_id": "b0"}],
        "attribute_candidates": [],
        "relation_candidates": [],
        "instance_suggestions": [{
            "local_id": "i1", "type_iri": f"{NS}Product", "label": "尊享",
            "data": {}, "evidence": "尊享医疗保险", "block_id": "b0", "confidence": 0.8,
        }],
        "instance_rel_suggestions": [],
    }
    doc = ParsedDocument("a.txt", "尊享医疗保险", (TextBlock("b0", "paragraph", "尊享医疗保险"),))
    snap = TypeSnapshot(objects=(OntoObject(iri=f"{NS}Product", label="保险产品", definition="d"),), attributes=(), relations=())
    result = get_extractor("llm_only").extract(doc, snap, FakeLlmGateway(canned))
    assert result.instance_suggestions[0].label == "尊享"
    assert result.object_candidates == []
    assert result.block_failures
    assert result.block_failures[0].block_id == "b0"


def test_hybrid_invalid_draft_becomes_block_failure():
    canned = {
        "object_candidates": [],
        "attribute_candidates": [],
        "relation_candidates": [],
        "instance_suggestions": [{"block_id": "b1"}],
        "instance_rel_suggestions": [],
    }
    doc = ParsedDocument("a.txt", "保险产品\n\n尊享。", (
        TextBlock("b0", "heading", "保险产品"),
        TextBlock("b1", "paragraph", "尊享。"),
    ))
    snap = TypeSnapshot(objects=(OntoObject(iri=f"{NS}Product", label="保险产品", definition="d"),), attributes=(), relations=())
    result = get_extractor("hybrid").extract(doc, snap, FakeLlmGateway(canned))
    assert result.instance_suggestions == []
    assert result.block_failures


def test_fake_gateway_queues_and_logs_messages():
    from ontocore.extract.llm import FakeLlmGateway
    from ontocore.errors import StructuredOutputError

    gw = FakeLlmGateway([{"a": 1}, {"__error__": True}])
    assert gw.complete_structured({}, [{"role": "user", "content": "x"}]) == {"a": 1}
    assert gw.messages_log[0][0]["content"] == "x"
    try:
        gw.complete_structured({}, [])
        raise AssertionError("expected error")
    except StructuredOutputError:
        pass
    vec = FakeLlmGateway({}, embeddings={"保险产品": [1.0, 0.0]}).embed(["保险产品"])
    assert vec == [[1.0, 0.0]]


def test_result_from_dict_drops_llm_similar_to():
    from ontocore.extract.llm_only import result_from_dict
    from ontocore.constants import NS

    result = result_from_dict({
        "object_candidates": [{
            "iri": f"{NS}Wait", "label": "等待期", "definition": "d",
            "parent_iri": None, "evidence": "e", "block_id": "b0", "confidence": 0.5,
            "similar_to": [{"iri": f"{NS}Other", "label": "x"}],
        }],
        "attribute_candidates": [],
        "relation_candidates": [],
        "instance_suggestions": [],
        "instance_rel_suggestions": [],
    })
    assert result.object_candidates[0].similar_to == []


def test_rules_only_proposes_new_object_when_unaligned():
    doc = ParsedDocument("a.txt", "等待期\n\n30天。", (
        TextBlock("b0", "heading", "等待期"),
        TextBlock("b1", "paragraph", "30天。"),
    ))
    snap = TypeSnapshot(objects=(), attributes=(), relations=())
    result = get_extractor("rules_only").extract(doc, snap, FakeLlmGateway({}))
    assert result.object_candidates
    assert result.object_candidates[0].label == "等待期"
