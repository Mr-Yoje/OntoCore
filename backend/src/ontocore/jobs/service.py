from __future__ import annotations

from ontocore.candidates.store import CandidateStore
from ontocore.errors import AppError, IngressError
from ontocore.extract.dedup import attach_similar
from ontocore.extract.guides import build_guides
from ontocore.extract.ingress import parse_upload
from ontocore.extract.registry import get_extractor
from ontocore.faults import KIND_BUSINESS, KIND_SYSTEM, log_fault
from ontocore.jobs.store import Job, JobStore
from ontocore.models import ExtractionResult
from ontocore.ontology.repository import OntologyRepository


def _has_candidates(result: ExtractionResult) -> bool:
    return bool(
        result.object_candidates
        or result.attribute_candidates
        or result.relation_candidates
        or result.instance_suggestions
        or result.instance_rel_suggestions
    )


class _ChatAndEmbed:
    def __init__(self, chat, embed) -> None:
        self._chat = chat
        self._embed = embed

    def complete_structured(self, schema: dict, messages: list[dict]) -> dict:
        return self._chat.complete_structured(schema, messages)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._embed.embed(texts)


class JobService:
    def __init__(self, jobs: JobStore, candidates: CandidateStore, ontology: OntologyRepository, llm_factory, graph) -> None:
        self._jobs = jobs
        self._candidates = candidates
        self._ontology = ontology
        self._llm_factory = llm_factory
        self._graph = graph

    def _call_factory(self, model: str, *, provider_id, thinking: bool):
        factory = self._llm_factory
        try:
            return factory(model, provider_id=provider_id, thinking=thinking)
        except TypeError:
            return factory(model)

    def _make_llm(self, job: Job):
        return self._call_factory(job.model, provider_id=job.provider_id, thinking=job.thinking)

    def _judge_llm(self, job: Job, chat):
        if not job.embed_model:
            return chat
        embed = self._call_factory(
            job.embed_model,
            provider_id=job.embed_provider_id or job.provider_id,
            thinking=False,
        )
        if embed is chat:
            return chat
        return _ChatAndEmbed(chat, embed)

    def _guide_instances(self, job: Job) -> list[dict]:
        wanted = set(job.guide_instance_iris)
        if not wanted:
            return []
        return [
            {
                "iri": node.onto_iri,
                "label": node.onto_label,
                "type_iri": node.type_iri,
                "data": node.data,
            }
            for node in self._graph.instance_network().nodes
            if node.onto_iri in wanted
        ]

    def run(self, job_id: str, filename: str, data: bytes) -> Job:
        job = self._jobs.set_status(job_id, "running")
        try:
            doc = parse_upload(filename, data)
        except IngressError as exc:
            log_fault(code=exc.code, kind=exc.kind, detail=str(exc) or "无法提取文本", exc=exc)
            self._jobs.set_status(job_id, "failed", error=str(exc) or "无法提取文本", error_kind=exc.kind)
            raise
        try:
            extractor = get_extractor(job.extractor)
            llm = self._make_llm(job)
            snapshot = self._ontology.snapshot()
            guides = build_guides(
                snapshot,
                object_iris=job.guide_object_iris,
                relation_iris=job.guide_relation_iris,
                instances=self._guide_instances(job),
            )
            result = extractor.extract(doc, snapshot, llm, guides=guides)
            if result.object_candidates or result.relation_candidates:
                try:
                    attach_similar(
                        result,
                        snapshot,
                        self._judge_llm(job, llm),
                        guide_object_iris=job.guide_object_iris,
                        guide_relation_iris=job.guide_relation_iris,
                        use_embed=bool(job.embed_model),
                    )
                except Exception as exc:
                    log_fault(
                        code="OC-3103",
                        kind=KIND_BUSINESS,
                        detail="判重失败",
                        exc=exc,
                    )
                    self._candidates.replace_job_results(job_id, result)
                    return self._jobs.set_status(
                        job_id, "partial", error="判重失败", error_kind=KIND_BUSINESS,
                    )
            self._candidates.replace_job_results(job_id, result)
        except AppError as exc:
            log_fault(code=exc.code, kind=exc.kind, detail=str(exc) or exc.message, exc=exc)
            return self._jobs.set_status(
                job_id, "failed", error=str(exc) or exc.message, error_kind=exc.kind,
            )
        except Exception as exc:
            log_fault(code="OC-9001", kind=KIND_SYSTEM, detail=str(exc) or "抽取失败", exc=exc)
            return self._jobs.set_status(
                job_id, "failed", error="抽取失败", error_kind=KIND_SYSTEM,
            )
        if result.block_failures:
            msg = result.block_failures[0].reason or "抽取失败"
            if _has_candidates(result):
                return self._jobs.set_status(
                    job_id, "partial", error=msg, error_kind=KIND_BUSINESS,
                )
            return self._jobs.set_status(
                job_id, "failed", error=msg, error_kind=KIND_BUSINESS,
            )
        return self._jobs.set_status(job_id, "completed")
