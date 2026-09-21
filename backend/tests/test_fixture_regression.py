from pathlib import Path

from ontocore.api.app import create_app
from ontocore.constants import NS
from ontocore.extract.ingress import parse_upload
from ontocore.extract.llm import FakeLlmGateway
from ontocore.extract.registry import get_extractor
from ontocore.models import OntoObject, TypeSnapshot


def test_empty_app_and_fixture_extract():
    app = create_app()
    assert not any("domain" in getattr(r, "path", "") for r in app.routes)
    network = app.state.ontology.type_network()
    assert network.nodes == ()
    assert network.edges == ()
    text = Path(__file__).parent.joinpath("fixtures/sample.txt").read_bytes()
    doc = parse_upload("sample.txt", text)
    canned_objects = {
        "object_candidates": [{
            "iri": f"{NS}Wait", "label": "等待期", "definition": "d",
            "parent_iri": None, "evidence": "等待期", "block_id": "b0", "confidence": 0.5,
        }],
        "attribute_candidates": [],
        "relation_candidates": [],
        "instance_suggestions": [],
        "instance_rel_suggestions": [],
    }
    result = get_extractor("llm").extract(
        doc, TypeSnapshot(objects=(), attributes=(), relations=()), FakeLlmGateway(canned_objects)
    )
    assert result.object_candidates
    canned_instances = {
        "object_candidates": [],
        "attribute_candidates": [],
        "relation_candidates": [],
        "instance_suggestions": [{
            "local_id": "i1", "type_iri": f"{NS}InsuranceProduct", "label": "尊享医疗保险",
            "data": {}, "evidence": "尊享医疗保险", "block_id": "b0", "confidence": 0.8,
        }],
        "instance_rel_suggestions": [],
    }
    with_product = get_extractor("llm").extract(
        doc,
        TypeSnapshot(
            objects=(OntoObject(iri=f"{NS}InsuranceProduct", label="保险产品", definition=""),),
            attributes=(),
            relations=(),
        ),
        FakeLlmGateway(canned_instances),
    )
    assert with_product.instance_suggestions
