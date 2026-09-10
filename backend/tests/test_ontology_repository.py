from ontocore.constants import NS
from ontocore.errors import OntologyWriteError, ProfileViolation
from ontocore.models import OntoAttribute, OntoObject, OntoRelation
from ontocore.ontology.repository import OntologyRepository


def test_empty_start():
    repo = OntologyRepository()
    assert repo.snapshot().objects == ()
    assert repo.type_network().nodes == ()


def test_create_object_and_network():
    repo = OntologyRepository()
    repo.create_object(OntoObject(iri=f"{NS}Product", label="保险产品", definition="一种产品"))
    repo.create_object(OntoObject(iri=f"{NS}Coverage", label="保险责任", definition="一条责任"))
    repo.create_relation(OntoRelation(
        iri=f"{NS}contains", label="包含", definition="产品包含责任",
        source_iri=f"{NS}Product", target_iri=f"{NS}Coverage",
    ))
    net = repo.type_network()
    assert {n.label for n in net.nodes} == {"保险产品", "保险责任"}
    assert net.edges[0].source_iri.endswith("Product")
    assert net.edges[0].target_iri.endswith("Coverage")


def test_parent_and_inherited_attribute():
    repo = OntologyRepository()
    repo.create_object(OntoObject(iri=f"{NS}Product", label="保险产品", definition="d"))
    repo.create_attribute(OntoAttribute(
        iri=f"{NS}name", label="名称", definition="显示名", owner_iri=f"{NS}Product", literal_kind="text",
    ))
    repo.create_object(OntoObject(iri=f"{NS}Critical", label="重疾险", definition="d", parent_iri=f"{NS}Product"))
    inherited = repo.inherited_attributes(f"{NS}Critical")
    assert any(a.label == "名称" for a in inherited)


def test_missing_parent_rejected():
    repo = OntologyRepository()
    try:
        repo.create_object(OntoObject(iri=f"{NS}A", label="A", definition="d", parent_iri=f"{NS}Missing"))
    except OntologyWriteError:
        return
    raise AssertionError("expected OntologyWriteError")


def test_relation_unknown_endpoint_rejected():
    repo = OntologyRepository()
    repo.create_object(OntoObject(iri=f"{NS}Product", label="产品", definition="d"))
    try:
        repo.create_relation(OntoRelation(
            iri=f"{NS}contains", label="包含", definition="d",
            source_iri=f"{NS}Product", target_iri=f"{NS}Coverage",
        ))
    except OntologyWriteError:
        return
    raise AssertionError("expected OntologyWriteError")


def test_import_same_iri_rejected_without_force():
    repo = OntologyRepository()
    repo.create_object(OntoObject(iri=f"{NS}Product", label="保险产品", definition="d"))
    ttl = repo.export_turtle()
    try:
        repo.import_turtle(ttl, force=False)
    except OntologyWriteError:
        return
    raise AssertionError("expected OntologyWriteError")


def test_import_force_overwrites_label():
    repo = OntologyRepository()
    repo.create_object(OntoObject(iri=f"{NS}Product", label="旧", definition="d"))
    ttl = (
        f"@prefix : <{NS}> . @prefix owl: <http://www.w3.org/2002/07/owl#> . "
        f"@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . "
        f':Product a owl:Class ; rdfs:label "新" ; rdfs:comment "d" .'
    )
    repo.import_turtle(ttl, force=True)
    labels = {c.iri: c.label for c in repo.snapshot().objects}
    assert labels[f"{NS}Product"] == "新"


def test_update_object_missing_parent_keeps_original():
    repo = OntologyRepository()
    repo.create_object(OntoObject(iri=f"{NS}Product", label="产品", definition="d"))
    repo.create_object(OntoObject(iri=f"{NS}Critical", label="重疾险", definition="d", parent_iri=f"{NS}Product"))
    try:
        repo.update_object(f"{NS}Critical", parent_iri=f"{NS}Missing")
    except OntologyWriteError:
        parents = {c.iri: c.parent_iri for c in repo.snapshot().objects}
        assert parents[f"{NS}Critical"] == f"{NS}Product"
        return
    raise AssertionError("expected OntologyWriteError")


def test_update_object_parent_rejects_duplicate_attribute_label():
    repo = OntologyRepository()
    repo.create_object(OntoObject(iri=f"{NS}Product", label="产品", definition="d"))
    repo.create_object(OntoObject(iri=f"{NS}Other", label="其他", definition="d"))
    repo.create_object(OntoObject(iri=f"{NS}Critical", label="重疾险", definition="d", parent_iri=f"{NS}Other"))
    repo.create_attribute(OntoAttribute(
        iri=f"{NS}childName", label="名称", definition="子名称", owner_iri=f"{NS}Critical", literal_kind="text",
    ))
    repo.create_attribute(OntoAttribute(
        iri=f"{NS}parentName", label="名称", definition="父名称", owner_iri=f"{NS}Product", literal_kind="text",
    ))
    try:
        repo.update_object(f"{NS}Critical", parent_iri=f"{NS}Product")
    except OntologyWriteError:
        parents = {c.iri: c.parent_iri for c in repo.snapshot().objects}
        assert parents[f"{NS}Critical"] == f"{NS}Other"
        return
    raise AssertionError("expected OntologyWriteError")


def test_update_object_parent_rejects_descendant_attribute_label():
    repo = OntologyRepository()
    repo.create_object(OntoObject(iri=f"{NS}P", label="P", definition="d"))
    repo.create_object(OntoObject(iri=f"{NS}Other", label="其他", definition="d"))
    repo.create_object(OntoObject(iri=f"{NS}Mid", label="中间", definition="d", parent_iri=f"{NS}Other"))
    repo.create_object(OntoObject(iri=f"{NS}Child", label="子", definition="d", parent_iri=f"{NS}Mid"))
    repo.create_attribute(OntoAttribute(
        iri=f"{NS}parentName", label="名称", definition="父名称", owner_iri=f"{NS}P", literal_kind="text",
    ))
    repo.create_attribute(OntoAttribute(
        iri=f"{NS}childName", label="名称", definition="子名称", owner_iri=f"{NS}Child", literal_kind="text",
    ))
    try:
        repo.update_object(f"{NS}Mid", parent_iri=f"{NS}P")
    except OntologyWriteError:
        parents = {c.iri: c.parent_iri for c in repo.snapshot().objects}
        assert parents[f"{NS}Mid"] == f"{NS}Other"
        return
    raise AssertionError("expected OntologyWriteError")


def test_update_object_rejects_parent_in_descendants():
    repo = OntologyRepository()
    repo.create_object(OntoObject(iri=f"{NS}A", label="A", definition="d"))
    repo.create_object(OntoObject(iri=f"{NS}B", label="B", definition="d", parent_iri=f"{NS}A"))
    try:
        repo.update_object(f"{NS}A", parent_iri=f"{NS}B")
    except OntologyWriteError:
        parents = {c.iri: c.parent_iri for c in repo.snapshot().objects}
        assert parents[f"{NS}A"] is None
        assert parents[f"{NS}B"] == f"{NS}A"
        return
    raise AssertionError("expected OntologyWriteError")


def test_import_invalid_turtle_does_not_mutate_store():
    repo = OntologyRepository()
    repo.create_object(OntoObject(iri=f"{NS}Product", label="保险产品", definition="d"))
    ttl = (
        f"@prefix : <{NS}> . @prefix owl: <http://www.w3.org/2002/07/owl#> . "
        f"@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . "
        f":A a owl:Class ; rdfs:subClassOf :B, :C . :B a owl:Class . :C a owl:Class ."
    )
    try:
        repo.import_turtle(ttl, force=True)
    except ProfileViolation:
        labels = {c.iri: c.label for c in repo.snapshot().objects}
        assert labels == {f"{NS}Product": "保险产品"}
        return
    raise AssertionError("expected ProfileViolation")


def test_attributes_for_includes_inherited():
    repo = OntologyRepository()
    repo.create_object(OntoObject(iri=f"{NS}Product", label="产品", definition="d"))
    repo.create_attribute(OntoAttribute(
        iri=f"{NS}name", label="名称", definition="显示名", owner_iri=f"{NS}Product", literal_kind="text",
    ))
    repo.create_object(OntoObject(iri=f"{NS}Critical", label="重疾险", definition="d", parent_iri=f"{NS}Product"))
    repo.create_attribute(OntoAttribute(
        iri=f"{NS}waiting", label="等待期", definition="天", owner_iri=f"{NS}Critical", literal_kind="number",
    ))
    attrs = repo.attributes_for(f"{NS}Critical")
    assert {a.label for a in attrs} == {"名称", "等待期"}
