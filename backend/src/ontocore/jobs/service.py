from __future__ import annotations

from ontocore.candidates.store import CandidateStore
from ontocore.error_catalog import fault_detail
from ontocore.errors import AppError, IngressError
from ontocore.extract.chunking import extract_texts
from ontocore.extract.dedup import attach_similar
from ontocore.extract.guides import build_guides
from ontocore.extract.ingress import parse_upload
from ontocore.extract.merge import merge_extraction_result
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


def _partial_reason(result: ExtractionResult, *, merge_failed: bool) -> str:
    if result.block_failures:
        return result.block_failures[0].reason or fault_detail("OC-3101")
    if merge_failed:
        return fault_detail("OC-3101")
    return fault_detail("OC-3101")


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
        self._jobs.set_status(job_id, "extracting")
        self._jobs.set_progress(job_id, 0, 0)
        job = self._jobs.get(job_id)
        try:
            doc = parse_upload(filename, data)
        except IngressError as exc:
            detail = fault_detail(exc.code)
            log_fault(code=exc.code, kind=exc.kind, detail=detail, exc=exc)
            self._jobs.set_status(job_id, "failed", error=detail, error_kind=exc.kind)
            raise
        try:
            n = len(extract_texts(doc))
            self._jobs.set_progress(job_id, 0, n)
            extractor = get_extractor(job.extractor)
            llm = self._make_llm(job)
            judge = self._judge_llm(job, llm)
            snapshot = self._ontology.snapshot()
            guides = build_guides(
                snapshot,
                object_iris=job.guide_object_iris,
                relation_iris=job.guide_relation_iris,
                instances=self._guide_instances(job),
            )

            def on_chunk_done(done: int, total: int) -> None:
                self._jobs.set_progress(job_id, done, total)

            result = extractor.extract(
                doc, snapshot, llm, guides=guides, on_chunk_done=on_chunk_done,
            )
            extract_partial = bool(result.block_failures)

            self._jobs.set_status(job_id, "merging")
            self._jobs.set_progress(job_id, 0, 0)
            embed_fn = judge.embed if job.embed_model and hasattr(judge, "embed") else None

            def on_cluster_done(done: int, total: int) -> None:
                self._jobs.set_progress(job_id, done, total)

            result, merge_failed = merge_extraction_result(
                result,
                llm,
                embed=embed_fn,
                on_cluster_done=on_cluster_done,
            )

            self._jobs.set_status(job_id, "aligning")
            self._jobs.set_progress(job_id, 0, 2)
            if result.object_candidates or result.relation_candidates:
                try:
                    attach_similar(
                        result,
                        snapshot,
                        judge,
                        guide_object_iris=job.guide_object_iris,
                        guide_relation_iris=job.guide_relation_iris,
                        use_embed=bool(job.embed_model),
                        on_embed_finished=lambda: self._jobs.set_progress(job_id, 1, 2),
                    )
                    self._jobs.set_progress(job_id, 2, 2)
                except Exception as exc:
                    detail = fault_detail("OC-3103")
                    log_fault(
                        code="OC-3103",
                        kind=KIND_BUSINESS,
                        detail=detail,
                        exc=exc,
                    )
                    self._candidates.replace_job_results(job_id, result)
                    return self._jobs.set_status(
                        job_id,
                        "reviewable_partial",
                        error=detail,
                        error_kind=KIND_BUSINESS,
                    )
            else:
                self._jobs.set_progress(job_id, 2, 2)

            self._candidates.replace_job_results(job_id, result)
        except AppError as exc:
            detail = exc.message
            log_fault(code=exc.code, kind=exc.kind, detail=detail, exc=exc)
            return self._jobs.set_status(
                job_id, "failed", error=detail, error_kind=exc.kind,
            )
        except Exception as exc:
            detail = fault_detail("OC-9001")
            log_fault(code="OC-9001", kind=KIND_SYSTEM, detail=detail, exc=exc)
            return self._jobs.set_status(
                job_id, "failed", error=detail, error_kind=KIND_SYSTEM,
            )

        has_partial = extract_partial or merge_failed or bool(result.block_failures)
        if has_partial:
            msg = _partial_reason(result, merge_failed=merge_failed)
            if _has_candidates(result):
                return self._jobs.set_status(
                    job_id, "reviewable_partial", error=msg, error_kind=KIND_BUSINESS,
                )
            return self._jobs.set_status(
                job_id, "failed", error=msg, error_kind=KIND_BUSINESS,
            )
        return self._jobs.set_status(job_id, "reviewable")
