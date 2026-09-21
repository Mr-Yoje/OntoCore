from ontocore.candidates.store import CandidateStore
from ontocore.constants import NS
from ontocore.errors import ConflictError, GraphUnavailable
from ontocore.extract.llm import FakeLlmGateway
from ontocore.graph.memory import MemoryGraphRepository
from ontocore.graph.ports import GraphNode
from ontocore.graph.projector import Projector
from ontocore.jobs.service import JobService
from ontocore.jobs.store import JobStore
from ontocore.models import BlockFailure, ExtractionResult
from ontocore.ontology.repository import OntologyRepository
from ontocore.review.service import ReviewService


def test_job_store_persists_guides_and_embed(tmp_path):
    store = JobStore(str(tmp_path / "j.db"))
    job = store.create(
        "a.txt",
        "llm",
        "deepseek-chat",
        provider_id="p1",
        thinking=False,
        embed_model="embed-x",
        guide_object_iris=[f"{NS}Product"],
        guide_relation_iris=[],
        guide_instance_iris=[f"{NS}i1"],
    )
    loaded = store.get(job.id)
    assert loaded.extractor == "llm"
    assert loaded.embed_model == "embed-x"
    assert loaded.guide_object_iris == [f"{NS}Product"]
    assert loaded.guide_instance_iris == [f"{NS}i1"]
    assert loaded.guide_relation_iris == []


def _canned():
    return {
        "object_candidates": [{
            "iri": f"{NS}Product", "label": "保险产品", "definition": "d",
            "parent_iri": None, "evidence": "产品", "block_id": "b0", "confidence": 1.0,
        }],
        "attribute_candidates": [],
        "relation_candidates": [],
        "instance_suggestions": [{
            "local_id": "p1", "type_iri": f"{NS}Product", "label": "尊享",
            "data": {}, "evidence": "尊享", "block_id": "b0", "confidence": 1.0,
        }],
        "instance_rel_suggestions": [],
    }


def test_accept_object_then_project(tmp_path):
    sqlite = str(tmp_path / "j.db")
    ontology = OntologyRepository()
    graph = MemoryGraphRepository()
    projector = Projector(graph)
    candidates = CandidateStore(sqlite)
    jobs = JobStore(sqlite)
    def llm_factory(model):
        return FakeLlmGateway(_canned())
    js = JobService(jobs, candidates, ontology, llm_factory)
    job = jobs.create("a.txt", "llm_only", "fake")
    js.run(job.id, "a.txt", "尊享医疗保险".encode("utf-8"))
    review = ReviewService(candidates, ontology, projector, jobs, graph)
    types = candidates.list_type_candidates(job.id)
    review.accept_type(types[0].id)
    assert any(o.label == "保险产品" for o in ontology.snapshot().objects)
    out = review.project_job(job.id)
    assert out["projected"]
    assert graph.instance_network().nodes
    assert not hasattr(review, "accept_instance")


class _BoomGraph(MemoryGraphRepository):
    def upsert_node(self, node: GraphNode) -> None:
        raise GraphUnavailable("graph down")


def test_graph_unavailable_keeps_accepted_types(tmp_path):
    sqlite = str(tmp_path / "j.db")
    ontology = OntologyRepository()
    graph = _BoomGraph()
    projector = Projector(graph)
    candidates = CandidateStore(sqlite)
    jobs = JobStore(sqlite)
    js = JobService(jobs, candidates, ontology, lambda model: FakeLlmGateway(_canned()))
    job = jobs.create("a.txt", "llm_only", "fake")
    js.run(job.id, "a.txt", "尊享医疗保险".encode("utf-8"))
    review = ReviewService(candidates, ontology, projector, jobs, graph)
    types = candidates.list_type_candidates(job.id)
    review.accept_type(types[0].id)
    try:
        review.project_job(job.id)
    except GraphUnavailable:
        pass
    else:
        raise AssertionError("expected GraphUnavailable")
    assert jobs.get(job.id).status == "types_accepted_graph_pending"
    assert any(o.label == "保险产品" for o in ontology.snapshot().objects)


def test_delete_object_conflicts_when_instances_exist(tmp_path):
    sqlite = str(tmp_path / "j.db")
    ontology = OntologyRepository()
    graph = MemoryGraphRepository()
    projector = Projector(graph)
    candidates = CandidateStore(sqlite)
    jobs = JobStore(sqlite)
    js = JobService(jobs, candidates, ontology, lambda model: FakeLlmGateway(_canned()))
    job = jobs.create("a.txt", "llm_only", "fake")
    js.run(job.id, "a.txt", "尊享医疗保险".encode("utf-8"))
    review = ReviewService(candidates, ontology, projector, jobs, graph)
    types = candidates.list_type_candidates(job.id)
    review.accept_type(types[0].id)
    review.project_job(job.id)
    try:
        review.delete_object(f"{NS}Product")
    except ConflictError as exc:
        assert exc.message == "仍有实例占用该对象"
    else:
        raise AssertionError("expected ConflictError")


class _AllBlocksFailExtractor:
    def extract(self, doc, snapshot, llm):
        return ExtractionResult(
            object_candidates=[],
            attribute_candidates=[],
            relation_candidates=[],
            instance_suggestions=[],
            instance_rel_suggestions=[],
            block_failures=[BlockFailure(block_id="b0", reason="extract failed")],
        )


def test_all_block_failures_without_candidates_is_failed(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "ontocore.jobs.service.get_extractor",
        lambda name: _AllBlocksFailExtractor(),
    )
    sqlite = str(tmp_path / "j.db")
    jobs = JobStore(sqlite)
    js = JobService(
        jobs,
        CandidateStore(sqlite),
        OntologyRepository(),
        lambda model: FakeLlmGateway({}),
    )
    job = jobs.create("a.txt", "llm_only", "fake")
    finished = js.run(job.id, "a.txt", "尊享医疗保险".encode("utf-8"))
    assert finished.status == "failed"


class _BoomExtractor:
    def extract(self, doc, snapshot, llm):
        raise RuntimeError("llm down")


def test_extractor_exception_marks_job_failed(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "ontocore.jobs.service.get_extractor",
        lambda name: _BoomExtractor(),
    )
    sqlite = str(tmp_path / "j.db")
    jobs = JobStore(sqlite)
    js = JobService(
        jobs,
        CandidateStore(sqlite),
        OntologyRepository(),
        lambda model: FakeLlmGateway({}),
    )
    job = jobs.create("a.txt", "llm_only", "fake")
    finished = js.run(job.id, "a.txt", "尊享医疗保险".encode("utf-8"))
    assert finished.status == "failed"
    assert "llm down" in (finished.error or "")
    assert jobs.get(job.id).status == "failed"


def test_invalid_drafts_can_leave_job_partial(tmp_path):
    sqlite = str(tmp_path / "j.db")
    jobs = JobStore(sqlite)
    canned = {
        "object_candidates": [{"label": "残缺", "block_id": "b0"}],
        "attribute_candidates": [],
        "relation_candidates": [],
        "instance_suggestions": [{
            "local_id": "p1", "type_iri": f"{NS}Product", "label": "尊享",
            "data": {}, "evidence": "尊享", "block_id": "b0", "confidence": 1.0,
        }],
        "instance_rel_suggestions": [],
    }
    js = JobService(
        jobs,
        CandidateStore(sqlite),
        OntologyRepository(),
        lambda model: FakeLlmGateway(canned),
    )
    job = jobs.create("a.txt", "llm_only", "fake")
    finished = js.run(job.id, "a.txt", "尊享医疗保险".encode("utf-8"))
    assert finished.status == "partial"


def test_successful_rel_not_skipped_when_longer_predicate_skipped(tmp_path):
    sqlite = str(tmp_path / "j.db")
    ontology = OntologyRepository()
    graph = MemoryGraphRepository()
    projector = Projector(graph)
    candidates = CandidateStore(sqlite)
    jobs = JobStore(sqlite)
    ok_pred = f"{NS}HasCoverage"
    skip_pred = f"{NS}HasCoverageExtra"
    canned = {
        "object_candidates": [
            {
                "iri": f"{NS}Product", "label": "保险产品", "definition": "d",
                "parent_iri": None, "evidence": "产品", "block_id": "b0", "confidence": 1.0,
            },
            {
                "iri": f"{NS}Coverage", "label": "保障责任", "definition": "d",
                "parent_iri": None, "evidence": "责任", "block_id": "b0", "confidence": 1.0,
            },
        ],
        "attribute_candidates": [],
        "relation_candidates": [{
            "iri": ok_pred, "label": "包含责任", "definition": "d",
            "source_iri": f"{NS}Product", "target_iri": f"{NS}Coverage",
            "evidence": "含", "block_id": "b0", "confidence": 1.0,
        }],
        "instance_suggestions": [
            {
                "local_id": "p1", "type_iri": f"{NS}Product", "label": "尊享",
                "data": {}, "evidence": "尊享", "block_id": "b0", "confidence": 1.0,
            },
            {
                "local_id": "c1", "type_iri": f"{NS}Coverage", "label": "住院",
                "data": {}, "evidence": "住院", "block_id": "b0", "confidence": 1.0,
            },
        ],
        "instance_rel_suggestions": [
            {
                "source_local_id": "p1", "target_local_id": "c1",
                "predicate_iri": ok_pred, "evidence": "含",
                "block_id": "b0", "confidence": 1.0,
            },
            {
                "source_local_id": "p1", "target_local_id": "c1",
                "predicate_iri": skip_pred, "evidence": "额外",
                "block_id": "b0", "confidence": 1.0,
            },
        ],
    }
    js = JobService(jobs, candidates, ontology, lambda model: FakeLlmGateway(canned))
    job = jobs.create("a.txt", "llm_only", "fake")
    js.run(job.id, "a.txt", "尊享医疗保险".encode("utf-8"))
    review = ReviewService(candidates, ontology, projector, jobs, graph)
    for item in candidates.list_type_candidates(job.id):
        review.accept_type(item.id)
    review.project_job(job.id)
    by_pred = {
        item.payload["predicate_iri"]: item.status
        for item in candidates.list_instance_candidates(job.id)
        if item.kind == "instance_rel"
    }
    assert by_pred[ok_pred] == "projected"
    assert by_pred[skip_pred] == "skipped"
