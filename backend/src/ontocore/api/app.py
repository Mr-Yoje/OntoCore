from __future__ import annotations

import os
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, Form, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from ontocore.candidates.store import CandidateStore
from ontocore.constants import NS
from ontocore.errors import (
    ConflictError,
    GraphUnavailable,
    IngressError,
    OntologyWriteError,
    ProfileViolation,
)
from ontocore.extract.llm import LiteLlmGateway
from ontocore.graph.memory import MemoryGraphRepository
from ontocore.graph.neo4j_repo import Neo4jGraphRepository
from ontocore.graph.projector import Projector
from ontocore.jobs.service import JobService
from ontocore.jobs.store import JobStore
from ontocore.models import OntoAttribute, OntoObject, OntoRelation
from ontocore.ontology.repository import OntologyRepository
from ontocore.review.service import ReviewService
from ontocore.settings import load_settings, save_settings

LiteralKind = Literal["text", "number", "date"]


class ObjectCreate(BaseModel):
    local_name: str
    label: str
    definition: str
    parent_local_name: str | None = None


class ObjectPatch(BaseModel):
    label: str | None = None
    definition: str | None = None
    parent_local_name: str | None = None


class AttributeCreate(BaseModel):
    local_name: str
    label: str
    definition: str
    literal_kind: LiteralKind


class AttributePatch(BaseModel):
    label: str | None = None
    definition: str | None = None
    literal_kind: LiteralKind | None = None


class RelationCreate(BaseModel):
    local_name: str
    label: str
    definition: str
    source_local_name: str
    target_local_name: str


class RelationPatch(BaseModel):
    label: str | None = None
    definition: str | None = None


class SettingsBody(BaseModel):
    extractor: str
    model: str


def _iri(local_name: str) -> str:
    return f"{NS}{local_name}"


def _dump(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, list | tuple):
        return [_dump(item) for item in value]
    return value


def _write_detail(exc: OntologyWriteError) -> str:
    raw = str(exc) or "写入失败"
    mapped = (
        raw.replace("attribute", "属性")
        .replace("relation", "关系")
        .replace("object", "对象")
        .replace("property", "属性")
    )
    if "对象" not in mapped and "属性" not in mapped and "关系" not in mapped:
        return f"无法写入对象：{mapped}"
    return mapped


def _graph_from_env():
    uri = os.environ.get("NEO4J_URI")
    if not uri:
        return MemoryGraphRepository()
    return Neo4jGraphRepository(
        uri,
        os.environ.get("NEO4J_USER", "neo4j"),
        os.environ.get("NEO4J_PASSWORD", "neo4j"),
    )


def create_app(
    *,
    data_dir: str | Path | None = None,
    graph=None,
    llm_factory=None,
) -> FastAPI:
    root = Path(data_dir) if data_dir is not None else Path(os.environ.get("ONTOCORE_DATA_DIR", "./data"))
    root.mkdir(parents=True, exist_ok=True)
    sqlite = str(root / "ontocore.db")
    ontology = OntologyRepository(str(root / "oxigraph"))
    graph_repo = graph if graph is not None else _graph_from_env()
    projector = Projector(graph_repo)
    candidates = CandidateStore(sqlite)
    jobs = JobStore(sqlite)
    factory = llm_factory or (lambda model: LiteLlmGateway(model))
    job_service = JobService(jobs, candidates, ontology, factory)
    review = ReviewService(candidates, ontology, projector, jobs, graph_repo)

    app = FastAPI(
        title="OntoCore",
        description="对象、属性、关系、定义与实例的 HTTP 接口",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8001",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.data_dir = root
    app.state.ontology = ontology
    app.state.graph = graph_repo
    app.state.projector = projector
    app.state.candidates = candidates
    app.state.jobs = jobs
    app.state.review = review

    @app.exception_handler(OntologyWriteError)
    async def ontology_write_handler(_request: Request, exc: OntologyWriteError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": _write_detail(exc)})

    @app.exception_handler(ConflictError)
    async def conflict_handler(_request: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": exc.message})

    @app.exception_handler(IngressError)
    async def ingress_handler(_request: Request, exc: IngressError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc) or "无法提取文本"})

    @app.exception_handler(GraphUnavailable)
    async def graph_handler(_request: Request, exc: GraphUnavailable) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": "图不可用"})

    @app.exception_handler(ProfileViolation)
    async def profile_handler(_request: Request, exc: ProfileViolation) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(KeyError)
    async def missing_handler(_request: Request, exc: KeyError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "未找到"})

    @app.get("/api/objects", summary="列出对象")
    def list_objects():
        return _dump(list(ontology.snapshot().objects))

    @app.post("/api/objects", summary="新建对象")
    def create_object(body: ObjectCreate):
        item_iri = _iri(body.local_name)
        parent_iri = None if body.parent_local_name is None else _iri(body.parent_local_name)
        ontology.create_object(
            OntoObject(
                iri=item_iri,
                label=body.label,
                definition=body.definition,
                parent_iri=parent_iri,
            )
        )
        projector.register_type(item_iri, body.label)
        return {"iri": item_iri, "label": body.label, "definition": body.definition}

    @app.patch("/api/objects/{local_name}", summary="更新对象")
    def patch_object(local_name: str, body: ObjectPatch):
        kwargs: dict[str, Any] = {}
        if "label" in body.model_fields_set:
            kwargs["label"] = body.label
        if "definition" in body.model_fields_set:
            kwargs["definition"] = body.definition
        if "parent_local_name" in body.model_fields_set:
            kwargs["parent_iri"] = (
                None if body.parent_local_name is None else _iri(body.parent_local_name)
            )
        iri = _iri(local_name)
        ontology.update_object(iri, **kwargs)
        if body.label is not None:
            projector.register_type(iri, body.label)
            graph_repo.update_type_display(iri, body.label)
        return {"iri": iri}

    @app.delete("/api/objects/{local_name}", summary="删除对象")
    def delete_object(local_name: str):
        review.delete_object(_iri(local_name))
        return {"ok": True}

    @app.post("/api/objects/{local_name}/attributes", summary="新建属性")
    def create_attribute(local_name: str, body: AttributeCreate):
        iri = _iri(body.local_name)
        ontology.create_attribute(
            OntoAttribute(
                iri=iri,
                label=body.label,
                definition=body.definition,
                owner_iri=_iri(local_name),
                literal_kind=body.literal_kind,
            )
        )
        projector.register_type(iri, body.label)
        return {"iri": iri, "label": body.label, "definition": body.definition}

    @app.get("/api/objects/{local_name}/attributes", summary="列出对象属性（含继承）")
    def list_object_attributes(local_name: str):
        return _dump(ontology.attributes_for(_iri(local_name)))

    @app.patch("/api/attributes/{local_name}", summary="更新属性")
    def patch_attribute(local_name: str, body: AttributePatch):
        kwargs: dict[str, Any] = {}
        if "label" in body.model_fields_set:
            kwargs["label"] = body.label
        if "definition" in body.model_fields_set:
            kwargs["definition"] = body.definition
        if "literal_kind" in body.model_fields_set:
            kwargs["literal_kind"] = body.literal_kind
        ontology.update_attribute(_iri(local_name), **kwargs)
        return {"iri": _iri(local_name)}

    @app.delete("/api/attributes/{local_name}", summary="删除属性")
    def delete_attribute(local_name: str):
        review.delete_attribute(_iri(local_name))
        return {"ok": True}

    @app.get("/api/relations", summary="列出关系")
    def list_relations():
        return _dump(list(ontology.snapshot().relations))

    @app.post("/api/relations", summary="新建关系")
    def create_relation(body: RelationCreate):
        iri = _iri(body.local_name)
        ontology.create_relation(
            OntoRelation(
                iri=iri,
                label=body.label,
                definition=body.definition,
                source_iri=_iri(body.source_local_name),
                target_iri=_iri(body.target_local_name),
            )
        )
        projector.register_type(iri, body.label)
        return {"iri": iri, "label": body.label, "definition": body.definition}

    @app.patch("/api/relations/{local_name}", summary="更新关系")
    def patch_relation(local_name: str, body: RelationPatch):
        kwargs: dict[str, Any] = {}
        if "label" in body.model_fields_set:
            kwargs["label"] = body.label
        if "definition" in body.model_fields_set:
            kwargs["definition"] = body.definition
        ontology.update_relation(_iri(local_name), **kwargs)
        return {"iri": _iri(local_name)}

    @app.delete("/api/relations/{local_name}", summary="删除关系")
    def delete_relation(local_name: str):
        review.delete_relation(_iri(local_name))
        return {"ok": True}

    @app.get("/api/ontology/network", summary="对象关系网")
    def ontology_network():
        return _dump(ontology.type_network())

    @app.get("/api/ontology/export", summary="导出本体")
    def export_ontology(format: str = Query("turtle")):
        if format == "jsonld":
            return Response(ontology.export_jsonld(), media_type="application/ld+json")
        return Response(ontology.export_turtle(), media_type="text/turtle")

    @app.post("/api/ontology/import", summary="导入本体")
    async def import_ontology(request: Request, force: bool = False):
        ttl = (await request.body()).decode("utf-8")
        ontology.import_turtle(ttl, force=force)
        return {"ok": True}

    @app.post("/api/jobs", summary="上传并抽取")
    async def create_job(
        file: UploadFile = File(...),
        extractor: str | None = Form(None),
        model: str | None = Form(None),
    ):
        current = load_settings(root)
        chosen_extractor = extractor or current["extractor"]
        chosen_model = model or current["model"]
        data = await file.read()
        filename = file.filename or "upload.bin"
        job = jobs.create(filename, chosen_extractor, chosen_model)
        job = job_service.run(job.id, filename, data)
        return _dump(job)

    @app.get("/api/jobs/{job_id}", summary="作业状态")
    def get_job(job_id: str):
        return _dump(jobs.get(job_id))

    @app.get("/api/jobs/{job_id}/type-candidates", summary="对象候选")
    def list_type_candidates(job_id: str):
        return _dump(candidates.list_type_candidates(job_id))

    @app.post("/api/type-candidates/{candidate_id}/accept", summary="接受对象候选")
    def accept_type_candidate(candidate_id: str):
        return _dump(review.accept_type(candidate_id))

    @app.post("/api/type-candidates/{candidate_id}/reject", summary="拒绝对象候选")
    def reject_type_candidate(candidate_id: str):
        return _dump(review.reject_type(candidate_id))

    @app.post("/api/jobs/{job_id}/project", summary="投影实例到图")
    def project_job(job_id: str):
        return review.project_job(job_id)

    @app.get("/api/graph/network", summary="实例网")
    def graph_network(type_iri: str | None = None):
        return _dump(graph_repo.instance_network(type_iri))

    @app.delete("/api/graph/nodes/{iri:path}", summary="删除实例节点")
    def delete_graph_node(iri: str):
        graph_repo.delete_node(iri)
        return {"ok": True}

    @app.delete("/api/graph/rels/{rel_id}", summary="删除实例关系")
    def delete_graph_rel(rel_id: str):
        graph_repo.delete_rel(rel_id)
        return {"ok": True}

    @app.get("/api/settings", summary="读取抽取设置")
    def get_settings():
        return load_settings(root)

    @app.put("/api/settings", summary="保存抽取设置")
    def put_settings(body: SettingsBody):
        return save_settings(root, body.extractor, body.model)

    return app
