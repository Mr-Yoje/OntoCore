from ontocore.candidates.store import CandidateStore
from ontocore.constants import NS
from ontocore.errors import ConflictError, GraphUnavailable, OntologyWriteError
from ontocore.extract.llm import FakeLlmGateway
from ontocore.graph.memory import MemoryGraphRepository
from ontocore.graph.memory import MemoryGraphRepository as MemoryGraph
from ontocore.graph.ports import GraphNode
from ontocore.graph.projector import Projector
from ontocore.jobs.service import JobService
from ontocore.jobs.store import JobStore
from ontocore.models import (
    AttributeCandidateDraft,
    BlockFailure,
    ExtractionResult,
    ObjectCandidateDraft,
    OntoAttribute,
    OntoObject,
    SimilarRef,
)
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
    assert loaded.embed_provider_id is None
    assert loaded.guide_object_iris == [f"{NS}Product"]
    assert loaded.guide_instance_iris == [f"{NS}i1"]
    assert loaded.guide_relation_iris == []


def test_job_store_persists_embed_provider(tmp_path):
    store = JobStore(str(tmp_path / "j.db"))
    job = store.create(
        "a.txt",
        "llm",
        "deepseek-chat",
        provider_id="p1",
        embed_model="embed-x",
        embed_provider_id="p2",
    )
    loaded = store.get(job.id)
    assert loaded.provider_id == "p1"
    assert loaded.embed_provider_id == "p2"
    assert loaded.embed_model == "embed-x"


def test_job_embed_uses_separate_provider(tmp_path):
    calls: list[dict] = []

    def factory(model, provider_id=None, thinking=False):
        calls.append({"model": model, "provider_id": provider_id, "thinking": thinking})
        return FakeLlmGateway(_canned())

    sqlite = str(tmp_path / "j.db")
    jobs = JobStore(sqlite)
    js = JobService(jobs, CandidateStore(sqlite), OntologyRepository(), factory, MemoryGraph())
    job = jobs.create(
        "a.txt",
        "llm",
        "chat-model",
        provider_id="chat-p",
        embed_model="embed-m",
        embed_provider_id="embed-p",
    )
    js.run(job.id, "a.txt", "尊享医疗保险".encode("utf-8"))
    chat = [c for c in calls if c["model"] == "chat-model"]
    embed = [c for c in calls if c["model"] == "embed-m"]
    assert chat and chat[0]["provider_id"] == "chat-p"
    assert embed and embed[0]["provider_id"] == "embed-p"
    assert embed[0]["thinking"] is False


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
    js = JobService(jobs, candidates, ontology, llm_factory, MemoryGraph())
    job = jobs.create("a.txt", "llm", "fake")
    js.run(job.id, "a.txt", "尊享医疗保险".encode("utf-8"))
    review = ReviewService(candidates, ontology, projector, jobs, graph, llm_factory)
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
    js = JobService(jobs, candidates, ontology, lambda model: FakeLlmGateway(_canned()), MemoryGraph())
    job = jobs.create("a.txt", "llm", "fake")
    js.run(job.id, "a.txt", "尊享医疗保险".encode("utf-8"))
    review = ReviewService(
        candidates, ontology, projector, jobs, graph, lambda model: FakeLlmGateway(_canned()),
    )
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
    js = JobService(jobs, candidates, ontology, lambda model: FakeLlmGateway(_canned()), MemoryGraph())
    job = jobs.create("a.txt", "llm", "fake")
    js.run(job.id, "a.txt", "尊享医疗保险".encode("utf-8"))
    review = ReviewService(
        candidates, ontology, projector, jobs, graph, lambda model: FakeLlmGateway(_canned()),
    )
    types = candidates.list_type_candidates(job.id)
    review.accept_type(types[0].id)
    review.project_job(job.id)
    try:
        review.delete_object(f"{NS}Product")
    except ConflictError as exc:
        assert exc.code == "OC-2004"
        assert exc.message == "仍有实例占用该对象"
    else:
        raise AssertionError("expected ConflictError")


class _AllBlocksFailExtractor:
    def extract(self, doc, snapshot, llm, **kwargs):
        return ExtractionResult(
            object_candidates=[],
            attribute_candidates=[],
            relation_candidates=[],
            instance_suggestions=[],
            instance_rel_suggestions=[],
            block_failures=[BlockFailure(block_id="b0", reason="")],
        )


def test_job_run_sets_progress_across_chunks(tmp_path, monkeypatch):
    chunks = [("b0", "甲"), ("b1", "乙"), ("b2", "丙")]
    monkeypatch.setattr(
        "ontocore.jobs.service.extract_texts",
        lambda doc: list(chunks),
    )
    monkeypatch.setattr(
        "ontocore.extract.engine.extract_texts",
        lambda doc: list(chunks),
    )
    empty = {
        "object_candidates": [],
        "attribute_candidates": [],
        "relation_candidates": [],
        "instance_suggestions": [],
        "instance_rel_suggestions": [],
    }
    sqlite = str(tmp_path / "j.db")
    jobs = JobStore(sqlite)
    progress_log: list[tuple[int, int]] = []
    orig_progress = jobs.set_progress

    def track_progress(job_id, done, total):
        progress_log.append((done, total))
        return orig_progress(job_id, done, total)

    jobs.set_progress = track_progress  # type: ignore[method-assign]
    js = JobService(
        jobs,
        CandidateStore(sqlite),
        OntologyRepository(),
        lambda *a, **k: FakeLlmGateway([dict(empty), dict(empty), dict(empty)]),
        MemoryGraph(),
    )
    job = jobs.create("a.txt", "llm", "fake")
    finished = js.run(job.id, "a.txt", "甲乙丙".encode("utf-8"))
    assert finished.status == "reviewable"
    assert (3, 3) in progress_log
    assert finished.progress_done == 2
    assert finished.progress_total == 2


def test_job_run_merges_same_name_across_slices_to_reviewable(tmp_path, monkeypatch):
    class _DupNameExtractor:
        def extract(self, doc, snapshot, llm, **kwargs):
            on_chunk_done = kwargs.get("on_chunk_done")
            if on_chunk_done is not None:
                on_chunk_done(1, 2)
                on_chunk_done(2, 2)
            return ExtractionResult(
                object_candidates=[
                    ObjectCandidateDraft(
                        iri=f"{NS}Pump1",
                        label="泵",
                        definition="d1",
                        parent_iri=None,
                        evidence="e1",
                        block_id="b0",
                        confidence=0.9,
                    ),
                    ObjectCandidateDraft(
                        iri=f"{NS}Pump2",
                        label="泵",
                        definition="d2",
                        parent_iri=None,
                        evidence="e2",
                        block_id="b1",
                        confidence=0.8,
                    ),
                ],
                attribute_candidates=[],
                relation_candidates=[],
                instance_suggestions=[],
                instance_rel_suggestions=[],
            )

    monkeypatch.setattr(
        "ontocore.jobs.service.get_extractor",
        lambda name: _DupNameExtractor(),
    )
    merge_payload = {
        "label": "泵",
        "definition": "merged",
        "parent_iri": None,
        "evidence": "e1; e2",
        "attributes": [],
    }
    sqlite = str(tmp_path / "j.db")
    jobs = JobStore(sqlite)
    cands = CandidateStore(sqlite)
    statuses: list[str] = []
    orig_status = jobs.set_status

    def track_status(job_id, status, **kwargs):
        statuses.append(status)
        return orig_status(job_id, status, **kwargs)

    jobs.set_status = track_status  # type: ignore[method-assign]
    js = JobService(
        jobs,
        cands,
        OntologyRepository(),
        lambda *a, **k: FakeLlmGateway(merge_payload),
        MemoryGraph(),
    )
    job = jobs.create("a.txt", "llm", "fake")
    finished = js.run(job.id, "a.txt", "标题\n\n正文。".encode("utf-8"))
    assert finished.status == "reviewable"
    assert statuses[:3] == ["extracting", "merging", "aligning"]
    assert statuses[-1] == "reviewable"
    objects = [r for r in cands.list_type_candidates(job.id) if r.kind == "object"]
    assert len(objects) == 1
    assert objects[0].payload["label"] == "泵"


def test_job_fails_when_llm_json_missing_extraction_keys(tmp_path):
    from ontocore.error_catalog import fault_detail

    sqlite = str(tmp_path / "j.db")
    jobs = JobStore(sqlite)
    cands = CandidateStore(sqlite)
    js = JobService(
        jobs,
        cands,
        OntologyRepository(),
        lambda model: FakeLlmGateway({"ok": True, "对象": []}),
        MemoryGraph(),
    )
    job = jobs.create("a.txt", "llm", "fake")
    finished = js.run(job.id, "a.txt", "尊享医疗保险".encode("utf-8"))
    assert finished.status == "failed"
    assert finished.error == fault_detail("OC-3101")
    assert cands.list_type_candidates(job.id) == []


def test_all_block_failures_without_candidates_is_failed(tmp_path, monkeypatch):
    from ontocore.error_catalog import fault_detail

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
        MemoryGraph(),
    )
    job = jobs.create("a.txt", "llm", "fake")
    finished = js.run(job.id, "a.txt", "尊享医疗保险".encode("utf-8"))
    assert finished.status == "failed"
    assert finished.error == fault_detail("OC-3101")
    assert finished.error_kind == "business"


class _BoomExtractor:
    def extract(self, doc, snapshot, llm, **kwargs):
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
        MemoryGraph(),
    )
    job = jobs.create("a.txt", "llm", "fake")
    finished = js.run(job.id, "a.txt", "尊享医疗保险".encode("utf-8"))
    assert finished.status == "failed"
    assert finished.error == "服务出错，请查看日志"
    assert finished.error_kind == "system"
    assert jobs.get(job.id).status == "failed"


def test_invalid_drafts_can_leave_job_partial(tmp_path):
    from ontocore.error_catalog import fault_detail

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
        MemoryGraph(),
    )
    job = jobs.create("a.txt", "llm", "fake")
    finished = js.run(job.id, "a.txt", "尊享医疗保险".encode("utf-8"))
    assert finished.status == "reviewable_partial"
    assert finished.error == fault_detail("OC-3101")


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
    js = JobService(jobs, candidates, ontology, lambda model: FakeLlmGateway(canned), MemoryGraph())
    job = jobs.create("a.txt", "llm", "fake")
    js.run(job.id, "a.txt", "尊享医疗保险".encode("utf-8"))
    review = ReviewService(
        candidates, ontology, projector, jobs, graph, lambda model: FakeLlmGateway(canned),
    )
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


def test_job_extract_then_partial_on_judge_failure(tmp_path, monkeypatch):
    from ontocore.candidates.store import CandidateStore
    from ontocore.extract.llm import FakeLlmGateway
    from ontocore.jobs.service import JobService
    from ontocore.jobs.store import JobStore
    from ontocore.ontology.repository import OntologyRepository
    from ontocore.graph.memory import MemoryGraphRepository as MemoryGraph
    from ontocore.constants import NS
    from ontocore.models import OntoObject

    ontology = OntologyRepository(str(tmp_path / "onto"))
    ontology.create_object(OntoObject(iri=f"{NS}Other", label="其它", definition="d"))
    extract_payload = {
        "object_candidates": [{
            "iri": f"{NS}New", "label": "新品", "definition": "d",
            "parent_iri": None, "evidence": "e", "block_id": "b0", "confidence": 0.5,
        }],
        "attribute_candidates": [], "relation_candidates": [],
        "instance_suggestions": [], "instance_rel_suggestions": [],
    }
    gw = FakeLlmGateway([extract_payload, {"__error__": True}])
    jobs = JobStore(str(tmp_path / "j.db"))
    cands = CandidateStore(str(tmp_path / "j.db"))
    service = JobService(jobs, cands, ontology, lambda *a, **k: gw, MemoryGraph())
    job = jobs.create("a.txt", "llm", "fake", guide_object_iris=[])
    done = service.run(job.id, "a.txt", "标题\n\n正文。".encode("utf-8"))
    assert done.status == "reviewable_partial"
    assert "判重" in (done.error or "")
    rows = cands.list_type_candidates(job.id)
    assert rows[0].payload["label"] == "新品"
    assert rows[0].payload.get("similar_to") in ([], None)


def test_accept_overwrite_replaces_object_attributes(tmp_path):
    onto = OntologyRepository(str(tmp_path / "o"))
    onto.create_object(OntoObject(iri=f"{NS}Product", label="旧名", definition="旧定义"))
    onto.create_attribute(OntoAttribute(
        iri=f"{NS}oldAttr", label="旧属性", definition="x",
        owner_iri=f"{NS}Product", literal_kind="text",
    ))
    jobs = JobStore(str(tmp_path / "j.db"))
    cands = CandidateStore(str(tmp_path / "j.db"))
    job = jobs.create("a.txt", "llm", "fake")
    cands.replace_job_results(job.id, ExtractionResult(
        object_candidates=[ObjectCandidateDraft(
            iri=f"{NS}New", label="新名", definition="新定义", parent_iri=None,
            evidence="e", block_id="b0", confidence=0.9,
            similar_to=[SimilarRef(iri=f"{NS}Product", label="旧名")],
        )],
        attribute_candidates=[AttributeCandidateDraft(
            iri=f"{NS}newAttr", label="新属性", definition="y",
            owner_iri=f"{NS}New", literal_kind="text",
            evidence="e", block_id="b0", confidence=0.9,
        )],
        relation_candidates=[], instance_suggestions=[], instance_rel_suggestions=[],
    ))
    review = ReviewService(cands, onto, Projector(MemoryGraph()), jobs, MemoryGraph(), lambda *a, **k: None)
    oid = [r for r in cands.list_type_candidates(job.id) if r.kind == "object"][0].id
    review.accept_type(oid, mode="overwrite", target_iri=f"{NS}Product")
    snap = onto.snapshot()
    product = [o for o in snap.objects if o.iri == f"{NS}Product"][0]
    assert product.label == "新名"
    owned = [a for a in snap.attributes if a.owner_iri == f"{NS}Product"]
    assert {a.label for a in owned} == {"新属性"}


def test_overwrite_then_accept_attribute_does_not_create_orphan(tmp_path):
    onto = OntologyRepository(str(tmp_path / "o"))
    onto.create_object(OntoObject(iri=f"{NS}Product", label="旧名", definition="旧定义"))
    jobs = JobStore(str(tmp_path / "j.db"))
    cands = CandidateStore(str(tmp_path / "j.db"))
    job = jobs.create("a.txt", "llm", "fake")
    cands.replace_job_results(job.id, ExtractionResult(
        object_candidates=[ObjectCandidateDraft(
            iri=f"{NS}New", label="新名", definition="新定义", parent_iri=None,
            evidence="e", block_id="b0", confidence=0.9,
            similar_to=[SimilarRef(iri=f"{NS}Product", label="旧名")],
        )],
        attribute_candidates=[AttributeCandidateDraft(
            iri=f"{NS}newAttr", label="新属性", definition="y",
            owner_iri=f"{NS}New", literal_kind="text",
            evidence="e", block_id="b0", confidence=0.9,
        )],
        relation_candidates=[], instance_suggestions=[], instance_rel_suggestions=[],
    ))
    review = ReviewService(cands, onto, Projector(MemoryGraph()), jobs, MemoryGraph(), lambda *a, **k: None)
    oid = [r for r in cands.list_type_candidates(job.id) if r.kind == "object"][0].id
    review.accept_type(oid, mode="overwrite", target_iri=f"{NS}Product")
    attr = [r for r in cands.list_type_candidates(job.id) if r.kind == "attribute"][0]
    assert attr.status == "accepted"
    review.accept_type(attr.id)
    owned = [a for a in onto.snapshot().attributes if a.owner_iri == f"{NS}Product"]
    assert len(owned) == 1
    assert owned[0].label == "新属性"
    assert not any(a.owner_iri == f"{NS}New" for a in onto.snapshot().attributes)


def test_unknown_accept_mode_uses_distinct_message(tmp_path):
    onto = OntologyRepository(str(tmp_path / "o"))
    onto.create_object(OntoObject(iri=f"{NS}Product", label="旧名", definition="旧定义"))
    jobs = JobStore(str(tmp_path / "j.db"))
    cands = CandidateStore(str(tmp_path / "j.db"))
    job = jobs.create("a.txt", "llm", "fake")
    cands.replace_job_results(job.id, ExtractionResult(
        object_candidates=[ObjectCandidateDraft(
            iri=f"{NS}New", label="新名", definition="新定义", parent_iri=None,
            evidence="e", block_id="b0", confidence=0.9,
            similar_to=[SimilarRef(iri=f"{NS}Product", label="旧名")],
        )],
        attribute_candidates=[], relation_candidates=[],
        instance_suggestions=[], instance_rel_suggestions=[],
    ))
    review = ReviewService(cands, onto, Projector(MemoryGraph()), jobs, MemoryGraph(), lambda *a, **k: None)
    oid = [r for r in cands.list_type_candidates(job.id) if r.kind == "object"][0].id
    try:
        review.accept_type(oid, mode="zap", target_iri=f"{NS}Product")
    except OntologyWriteError as exc:
        assert exc.code == "OC-2002"
        assert str(exc) == "无法写入对象、属性或关系"
    else:
        raise AssertionError("expected OntologyWriteError")


def test_accept_align_miss_uses_oc_2007(tmp_path):
    onto = OntologyRepository(str(tmp_path / "o"))
    onto.create_object(OntoObject(iri=f"{NS}Product", label="旧名", definition="旧定义"))
    jobs = JobStore(str(tmp_path / "j.db"))
    cands = CandidateStore(str(tmp_path / "j.db"))
    job = jobs.create("a.txt", "llm", "fake")
    cands.replace_job_results(job.id, ExtractionResult(
        object_candidates=[ObjectCandidateDraft(
            iri=f"{NS}New", label="新名", definition="新定义", parent_iri=None,
            evidence="e", block_id="b0", confidence=0.9,
            similar_to=[SimilarRef(iri=f"{NS}Product", label="旧名")],
        )],
        attribute_candidates=[], relation_candidates=[],
        instance_suggestions=[], instance_rel_suggestions=[],
    ))
    review = ReviewService(cands, onto, Projector(MemoryGraph()), jobs, MemoryGraph(), lambda *a, **k: None)
    oid = [r for r in cands.list_type_candidates(job.id) if r.kind == "object"][0].id
    try:
        review.accept_type(oid, mode="overwrite", target_iri=f"{NS}Other")
    except OntologyWriteError as exc:
        assert exc.code == "OC-2007"
        assert str(exc) == "请选择要对齐的已有对象或关系"
    else:
        raise AssertionError("expected OntologyWriteError")


def test_job_partial_when_judge_json_malformed(tmp_path):
    from ontocore.faults import configure_logging

    configure_logging(tmp_path)
    ontology = OntologyRepository(str(tmp_path / "onto"))
    ontology.create_object(OntoObject(iri=f"{NS}Other", label="其它", definition="d"))
    extract_payload = {
        "object_candidates": [{
            "iri": f"{NS}New", "label": "新品", "definition": "d",
            "parent_iri": None, "evidence": "e", "block_id": "b0", "confidence": 0.5,
        }],
        "attribute_candidates": [], "relation_candidates": [],
        "instance_suggestions": [], "instance_rel_suggestions": [],
    }
    gw = FakeLlmGateway([extract_payload, {"object_similar": {f"{NS}New": None}}])
    jobs = JobStore(str(tmp_path / "j.db"))
    cands = CandidateStore(str(tmp_path / "j.db"))
    service = JobService(jobs, cands, ontology, lambda *a, **k: gw, MemoryGraph())
    job = jobs.create("a.txt", "llm", "fake", guide_object_iris=[])
    done = service.run(job.id, "a.txt", "标题\n\n正文。".encode("utf-8"))
    assert done.status == "reviewable_partial"
    assert "判重失败" in (done.error or "")
    assert done.error_kind == "business"
    rows = cands.list_type_candidates(job.id)
    assert rows
    assert rows[0].payload["label"] == "新品"
    from pathlib import Path

    logs = list((Path(tmp_path) / "logs").glob("ontocore_*.log"))
    if logs:
        text = logs[0].read_text(encoding="utf-8")
        assert "OC-3103" in text
        assert "Traceback" in text


def test_accept_merge_writes_llm_result(tmp_path):
    onto = OntologyRepository(str(tmp_path / "o"))
    onto.create_object(OntoObject(iri=f"{NS}Product", label="旧名", definition="旧定义"))
    jobs = JobStore(str(tmp_path / "j.db"))
    cands = CandidateStore(str(tmp_path / "j.db"))
    job = jobs.create("a.txt", "llm", "fake")
    cands.replace_job_results(job.id, ExtractionResult(
        object_candidates=[ObjectCandidateDraft(
            iri=f"{NS}New", label="新名", definition="新定义", parent_iri=None,
            evidence="e", block_id="b0", confidence=0.9,
            similar_to=[SimilarRef(iri=f"{NS}Product", label="旧名")],
        )],
        attribute_candidates=[], relation_candidates=[],
        instance_suggestions=[], instance_rel_suggestions=[],
    ))
    gw = FakeLlmGateway({
        "label": "融合名", "definition": "融合定义", "parent_iri": None,
        "attributes": [],
    })
    graph = MemoryGraph()
    review = ReviewService(cands, onto, Projector(graph), jobs, graph, lambda *a, **k: gw)
    oid = [r for r in cands.list_type_candidates(job.id) if r.kind == "object"][0].id
    review.accept_type(oid, mode="merge", target_iri=f"{NS}Product")
    assert [o.label for o in onto.snapshot().objects if o.iri == f"{NS}Product"] == ["融合名"]


def _track_status_progress(jobs: JobStore) -> list[tuple[str, int, int]]:
    """Record (status, done, total) on each set_status / set_progress."""
    events: list[tuple[str, int, int]] = []
    current = {"status": "queued"}
    orig_status = jobs.set_status
    orig_progress = jobs.set_progress

    def track_status(job_id, status, **kwargs):
        current["status"] = status
        result = orig_status(job_id, status, **kwargs)
        job = jobs.get(job_id)
        events.append((status, job.progress_done, job.progress_total))
        return result

    def track_progress(job_id, done, total):
        result = orig_progress(job_id, done, total)
        events.append((current["status"], done, total))
        return result

    jobs.set_status = track_status  # type: ignore[method-assign]
    jobs.set_progress = track_progress  # type: ignore[method-assign]
    return events


def test_acceptance_extracting_progress_increments_per_slice(tmp_path, monkeypatch):
    """§4.1: extracting total == n_slices; done increments after each chunk."""
    n_slices = 3
    chunks = [("b0", "甲"), ("b1", "乙"), ("b2", "丙")]
    monkeypatch.setattr(
        "ontocore.jobs.service.extract_texts",
        lambda doc: list(chunks),
    )
    monkeypatch.setattr(
        "ontocore.extract.engine.extract_texts",
        lambda doc: list(chunks),
    )
    empty = {
        "object_candidates": [],
        "attribute_candidates": [],
        "relation_candidates": [],
        "instance_suggestions": [],
        "instance_rel_suggestions": [],
    }
    sqlite = str(tmp_path / "j.db")
    jobs = JobStore(sqlite)
    events = _track_status_progress(jobs)
    js = JobService(
        jobs,
        CandidateStore(sqlite),
        OntologyRepository(),
        lambda *a, **k: FakeLlmGateway([dict(empty)] * n_slices),
        MemoryGraph(),
    )
    job = jobs.create("a.txt", "llm", "fake")
    finished = js.run(job.id, "a.txt", "甲乙丙".encode("utf-8"))
    extracting = [(d, t) for s, d, t in events if s == "extracting"]
    assert (0, n_slices) in extracting
    assert (1, n_slices) in extracting
    assert (2, n_slices) in extracting
    assert (3, n_slices) in extracting
    assert finished.status == "reviewable"


def test_acceptance_merging_progress_for_same_name_cluster(tmp_path, monkeypatch):
    """§4.2: two same-name drafts → merging total==1; after merge done==1."""

    class _DupNameExtractor:
        def extract(self, doc, snapshot, llm, **kwargs):
            on_chunk_done = kwargs.get("on_chunk_done")
            if on_chunk_done is not None:
                on_chunk_done(1, 1)
            return ExtractionResult(
                object_candidates=[
                    ObjectCandidateDraft(
                        iri=f"{NS}Pump1",
                        label="泵",
                        definition="d1",
                        parent_iri=None,
                        evidence="e1",
                        block_id="b0",
                        confidence=0.9,
                    ),
                    ObjectCandidateDraft(
                        iri=f"{NS}Pump2",
                        label="泵",
                        definition="d2",
                        parent_iri=None,
                        evidence="e2",
                        block_id="b1",
                        confidence=0.8,
                    ),
                ],
                attribute_candidates=[],
                relation_candidates=[],
                instance_suggestions=[],
                instance_rel_suggestions=[],
            )

    monkeypatch.setattr(
        "ontocore.jobs.service.get_extractor",
        lambda name: _DupNameExtractor(),
    )
    merge_payload = {
        "label": "泵",
        "definition": "merged",
        "parent_iri": None,
        "evidence": "e1; e2",
        "attributes": [],
    }
    sqlite = str(tmp_path / "j.db")
    jobs = JobStore(sqlite)
    events = _track_status_progress(jobs)
    js = JobService(
        jobs,
        CandidateStore(sqlite),
        OntologyRepository(),
        lambda *a, **k: FakeLlmGateway(merge_payload),
        MemoryGraph(),
    )
    job = jobs.create("a.txt", "llm", "fake")
    finished = js.run(job.id, "a.txt", "标题\n\n正文。".encode("utf-8"))
    merging = [(d, t) for s, d, t in events if s == "merging"]
    assert any(t == 1 for _, t in merging)
    assert (1, 1) in merging
    assert finished.status == "reviewable"


def test_acceptance_aligning_progress_embed_then_judge(tmp_path, monkeypatch):
    """§4.3: after embed done==1,total==2; after judge done==2."""

    class _OneObjExtractor:
        def extract(self, doc, snapshot, llm, **kwargs):
            on_chunk_done = kwargs.get("on_chunk_done")
            if on_chunk_done is not None:
                on_chunk_done(1, 1)
            return ExtractionResult(
                object_candidates=[
                    ObjectCandidateDraft(
                        iri=f"{NS}New",
                        label="新品",
                        definition="d",
                        parent_iri=None,
                        evidence="e",
                        block_id="b0",
                        confidence=0.9,
                    ),
                ],
                attribute_candidates=[],
                relation_candidates=[],
                instance_suggestions=[],
                instance_rel_suggestions=[],
            )

    monkeypatch.setattr(
        "ontocore.jobs.service.get_extractor",
        lambda name: _OneObjExtractor(),
    )
    ontology = OntologyRepository(str(tmp_path / "onto"))
    ontology.create_object(OntoObject(iri=f"{NS}Other", label="其它", definition="d"))
    judge = {"object_similar": {}, "relation_similar": {}}
    sqlite = str(tmp_path / "j.db")
    jobs = JobStore(sqlite)
    events = _track_status_progress(jobs)
    gw = FakeLlmGateway(judge)
    js = JobService(
        jobs,
        CandidateStore(sqlite),
        ontology,
        lambda *a, **k: gw,
        MemoryGraph(),
    )
    job = jobs.create(
        "a.txt",
        "llm",
        "fake",
        embed_model="fake-embed",
        embed_provider_id="p1",
    )
    finished = js.run(job.id, "a.txt", "标题\n\n正文。".encode("utf-8"))
    aligning = [(d, t) for s, d, t in events if s == "aligning"]
    assert (0, 2) in aligning
    assert (1, 2) in aligning
    assert (2, 2) in aligning
    assert finished.status == "reviewable"
    assert finished.progress_done == 2
    assert finished.progress_total == 2


def test_acceptance_no_merge_clusters_still_reviewable(tmp_path, monkeypatch):
    """§4.2: no multi-member clusters → merging need not be non-zero; still reviewable."""

    class _UniqueExtractor:
        def extract(self, doc, snapshot, llm, **kwargs):
            on_chunk_done = kwargs.get("on_chunk_done")
            if on_chunk_done is not None:
                on_chunk_done(1, 1)
            return ExtractionResult(
                object_candidates=[
                    ObjectCandidateDraft(
                        iri=f"{NS}Only",
                        label="唯一泵",
                        definition="d",
                        parent_iri=None,
                        evidence="e",
                        block_id="b0",
                        confidence=0.9,
                    ),
                ],
                attribute_candidates=[],
                relation_candidates=[],
                instance_suggestions=[],
                instance_rel_suggestions=[],
            )

    monkeypatch.setattr(
        "ontocore.jobs.service.get_extractor",
        lambda name: _UniqueExtractor(),
    )
    sqlite = str(tmp_path / "j.db")
    jobs = JobStore(sqlite)
    events = _track_status_progress(jobs)
    js = JobService(
        jobs,
        CandidateStore(sqlite),
        OntologyRepository(),
        lambda *a, **k: FakeLlmGateway({"object_similar": {}, "relation_similar": {}}),
        MemoryGraph(),
    )
    job = jobs.create("a.txt", "llm", "fake")
    finished = js.run(job.id, "a.txt", "标题\n\n正文。".encode("utf-8"))
    assert "merging" in {s for s, _, _ in events}
    # After phase reset to (0,0), no cluster progress (total>0) is required.
    after_reset: list[tuple[int, int]] = []
    seen_reset = False
    for status, done, total in events:
        if status != "merging":
            continue
        if (done, total) == (0, 0):
            seen_reset = True
            after_reset.append((done, total))
            continue
        if seen_reset:
            after_reset.append((done, total))
    assert seen_reset
    assert not any(t > 0 for _, t in after_reset)
    assert finished.status == "reviewable"
