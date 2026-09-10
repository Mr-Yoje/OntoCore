from __future__ import annotations

from ontocore.candidates.store import CandidateStore
from ontocore.errors import IngressError
from ontocore.extract.ingress import parse_upload
from ontocore.extract.registry import get_extractor
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


class JobService:
    def __init__(self, jobs: JobStore, candidates: CandidateStore, ontology: OntologyRepository, llm_factory) -> None:
        self._jobs = jobs
        self._candidates = candidates
        self._ontology = ontology
        self._llm_factory = llm_factory

    def run(self, job_id: str, filename: str, data: bytes) -> Job:
        job = self._jobs.set_status(job_id, "running")
        try:
            doc = parse_upload(filename, data)
        except IngressError as exc:
            self._jobs.set_status(job_id, "failed", error=str(exc))
            raise
        try:
            extractor = get_extractor(job.extractor)
            llm = self._llm_factory(job.model)
            result = extractor.extract(doc, self._ontology.snapshot(), llm)
            self._candidates.replace_job_results(job_id, result)
        except Exception as exc:
            return self._jobs.set_status(job_id, "failed", error=str(exc))
        if result.block_failures:
            if _has_candidates(result):
                return self._jobs.set_status(job_id, "partial")
            return self._jobs.set_status(job_id, "failed")
        return self._jobs.set_status(job_id, "completed")
