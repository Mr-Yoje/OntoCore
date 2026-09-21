from __future__ import annotations

import json

from ontocore.errors import StructuredOutputError
from ontocore.extract.chunking import SHORT_TEXT_LIMIT, extract_texts
from ontocore.extract.llm import LlmGateway
from ontocore.extract.llm_only import EXTRACTION_SCHEMA, result_from_dict
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
        for block_id, section_text in extract_texts(doc):
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
            except StructuredOutputError:
                merged.block_failures.append(BlockFailure(block_id=block_id, reason="抽取失败"))
                continue
            part = result_from_dict(payload)
            merged.object_candidates.extend(part.object_candidates)
            merged.attribute_candidates.extend(part.attribute_candidates)
            merged.relation_candidates.extend(part.relation_candidates)
            merged.instance_suggestions.extend(part.instance_suggestions)
            merged.instance_rel_suggestions.extend(part.instance_rel_suggestions)
            merged.block_failures.extend(part.block_failures)
        return merged


__all__ = ["LlmExtractor", "SHORT_TEXT_LIMIT"]
