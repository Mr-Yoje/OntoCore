from __future__ import annotations

import json
from collections.abc import Callable

from ontocore.error_catalog import fault_detail
from ontocore.errors import AppError
from ontocore.extract.chunking import SHORT_TEXT_LIMIT, extract_texts
from ontocore.extract.llm import LlmGateway
from ontocore.extract.llm_only import EXTRACTION_SCHEMA, result_from_dict
from ontocore.faults import KIND_BUSINESS, log_fault, map_provider_fault
from ontocore.models import (
    BlockFailure,
    ExtractionGuides,
    ExtractionResult,
    ParsedDocument,
    TypeSnapshot,
)

SYSTEM_CONTENT = (
    "根据文档抽取对象（含属性）、关系和实例。guides 是软约束：实例含义接近引导中的对象或关系时对齐到其编号；确实无法对齐可以提议新对象、新属性、新关系。"
)


class LlmExtractor:
    name = "llm"

    def extract(
        self,
        doc: ParsedDocument,
        snapshot: TypeSnapshot,
        llm: LlmGateway,
        *,
        guides: ExtractionGuides | None = None,
        on_chunk_done: Callable[[int, int], None] | None = None,
    ) -> ExtractionResult:
        del snapshot
        guides_payload = (
            guides.as_prompt_dict()
            if guides
            else {"objects": [], "attributes": [], "relations": [], "instances": []}
        )
        merged = ExtractionResult(
            object_candidates=[],
            attribute_candidates=[],
            relation_candidates=[],
            instance_suggestions=[],
            instance_rel_suggestions=[],
            block_failures=[],
        )
        texts = extract_texts(doc)
        total = len(texts)
        if on_chunk_done is not None:
            on_chunk_done(0, total)
        for done, (block_id, section_text) in enumerate(texts, start=1):
            messages = [
                {"role": "system", "content": SYSTEM_CONTENT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "guides": guides_payload,
                            "filename": doc.filename,
                            "text": section_text,
                        },
                        ensure_ascii=False,
                    ),
                },
            ]
            try:
                payload = llm.complete_structured(EXTRACTION_SCHEMA, messages)
            except Exception as exc:
                if isinstance(exc, AppError):
                    code = exc.code
                    detail = exc.message
                else:
                    code = map_provider_fault(str(exc), domain="job")
                    detail = fault_detail(code)
                log_fault(code=code, kind=KIND_BUSINESS, detail=detail, exc=exc)
                merged.block_failures.append(BlockFailure(block_id=block_id, reason=detail))
                if on_chunk_done is not None:
                    on_chunk_done(done, total)
                continue
            part = result_from_dict(payload)
            merged.object_candidates.extend(part.object_candidates)
            merged.attribute_candidates.extend(part.attribute_candidates)
            merged.relation_candidates.extend(part.relation_candidates)
            merged.instance_suggestions.extend(part.instance_suggestions)
            merged.instance_rel_suggestions.extend(part.instance_rel_suggestions)
            merged.block_failures.extend(part.block_failures)
            if on_chunk_done is not None:
                on_chunk_done(done, total)
        return merged


__all__ = ["LlmExtractor", "SHORT_TEXT_LIMIT"]
