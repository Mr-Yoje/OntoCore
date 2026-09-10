from ontocore.constants import NS
from ontocore.graph.memory import MemoryGraphRepository
from ontocore.graph.projector import Projector
from ontocore.models import InstanceRelDraft, InstanceSuggestionDraft, OntoObject, OntoRelation, TypeSnapshot


def test_skip_unconfirmed_object():
    g = MemoryGraphRepository()
    p = Projector(g)
    snap = TypeSnapshot(
        objects=(OntoObject(iri=f"{NS}Product", label="产品", definition="d"),),
        attributes=(),
        relations=(),
    )
    inst = [InstanceSuggestionDraft(
        local_id="e1", type_iri=f"{NS}Unknown", label="x", data={}, evidence="e", block_id="b", confidence=1.0,
    )]
    ok, skipped = p.project_instances(snap, inst, [], iri_prefix=NS)
    assert ok == []
    assert skipped


def test_project_and_rename_keeps_iri():
    g = MemoryGraphRepository()
    p = Projector(g)
    iri = f"{NS}Product"
    snap = TypeSnapshot(objects=(OntoObject(iri=iri, label="产品", definition="d"),), attributes=(), relations=())
    p.register_type(iri, "产品")
    inst = [InstanceSuggestionDraft(
        local_id="p1", type_iri=iri, label="尊享", data={}, evidence="e", block_id="b", confidence=1.0,
    )]
    ok, skipped = p.project_instances(snap, inst, [], iri_prefix=NS)
    assert skipped == []
    node_iri = ok[0]
    p.sync_object_label(iri, "保险产品")
    node = g.get_node(node_iri)
    assert node is not None
    assert node.onto_iri == node_iri
    assert node.onto_label == "保险产品"
    assert node.native_label == "OntoNode"


def test_delete_instance():
    g = MemoryGraphRepository()
    p = Projector(g)
    iri = f"{NS}Product"
    snap = TypeSnapshot(objects=(OntoObject(iri=iri, label="产品", definition="d"),), attributes=(), relations=())
    inst = [InstanceSuggestionDraft(
        local_id="p1", type_iri=iri, label="尊享", data={}, evidence="e", block_id="b", confidence=1.0,
    )]
    ok, _ = p.project_instances(snap, inst, [], iri_prefix=NS)
    g.delete_node(ok[0])
    assert g.get_node(ok[0]) is None
    assert g.instance_network().nodes == ()


def test_rel_id_deterministic_on_reproject():
    g = MemoryGraphRepository()
    p = Projector(g)
    product = f"{NS}Product"
    coverage = f"{NS}Coverage"
    pred = f"{NS}contains"
    snap = TypeSnapshot(
        objects=(
            OntoObject(iri=product, label="产品", definition="d"),
            OntoObject(iri=coverage, label="责任", definition="d"),
        ),
        attributes=(),
        relations=(OntoRelation(
            iri=pred, label="包含", definition="d", source_iri=product, target_iri=coverage,
        ),),
    )
    inst = [
        InstanceSuggestionDraft(local_id="p1", type_iri=product, label="尊享", data={}, evidence="e", block_id="b", confidence=1.0),
        InstanceSuggestionDraft(local_id="c1", type_iri=coverage, label="住院", data={}, evidence="e", block_id="b", confidence=1.0),
    ]
    rels = [
        InstanceRelDraft(source_local_id="p1", target_local_id="c1", predicate_iri=pred, evidence="e", block_id="b", confidence=1.0),
    ]
    p.project_instances(snap, inst, rels, iri_prefix=NS)
    first = [e.rel_id for e in g.instance_network().edges]
    p.project_instances(snap, inst, rels, iri_prefix=NS)
    second = [e.rel_id for e in g.instance_network().edges]
    assert len(first) == 1
    assert first == second
