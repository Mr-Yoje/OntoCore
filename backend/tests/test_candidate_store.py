from ontocore.candidates.store import CandidateStore
from ontocore.models import ExtractionResult, ObjectCandidateDraft


def test_type_accept_and_instance_not_accepted(tmp_path):
    store = CandidateStore(str(tmp_path / "c.db"))
    result = ExtractionResult(
        object_candidates=[ObjectCandidateDraft(
            iri="https://ontocore.local/ns/working#Foo", label="Foo", definition="",
            parent_iri=None, evidence="原文", block_id="b1", confidence=0.9,
        )],
        attribute_candidates=[],
        relation_candidates=[],
        instance_suggestions=[],
        instance_rel_suggestions=[],
    )
    store.replace_job_results("job1", result)
    rows = store.list_type_candidates("job1")
    assert rows[0].status == "proposed"
    updated = store.set_type_status(rows[0].id, "accepted")
    assert updated.status == "accepted"
    assert store.list_instance_candidates("job1") == []
