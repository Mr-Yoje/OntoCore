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


def test_rules_only_proposes_new_object_when_unaligned():
    doc = ParsedDocument("a.txt", "等待期\n\n30天。", (
        TextBlock("b0", "heading", "等待期"),
        TextBlock("b1", "paragraph", "30天。"),
    ))
    snap = TypeSnapshot(objects=(), attributes=(), relations=())
    result = get_extractor("rules_only").extract(doc, snap, FakeLlmGateway({}))
    assert result.object_candidates
    assert result.object_candidates[0].label == "等待期"
