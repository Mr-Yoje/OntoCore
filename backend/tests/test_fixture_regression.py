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
    result = get_extractor("rules_only").extract(
        doc, TypeSnapshot(objects=(), attributes=(), relations=()), FakeLlmGateway({})
    )
    assert result.object_candidates
    with_product = get_extractor("rules_only").extract(
        doc,
        TypeSnapshot(
            objects=(OntoObject(iri=f"{NS}InsuranceProduct", label="保险产品", definition=""),),
            attributes=(),
            relations=(),
        ),
        FakeLlmGateway({}),
    )
    assert with_product.instance_suggestions
