from __future__ import annotations

import json

from ontocore.extract.llm import LlmGateway
from ontocore.extract.llm_only import EXTRACTION_SCHEMA, result_from_dict, serialize_snapshot
from ontocore.models import ExtractionResult, ParsedDocument, TextBlock, TypeSnapshot


def _sections(doc: ParsedDocument) -> list[dict]:
    sections: list[dict] = []
    current: dict | None = None
    for block in doc.blocks:
        if block.kind == "heading":
            if current is not None:
                sections.append(current)
            current = {
                "block_id": block.block_id,
                "heading": block.text,
                "blocks": [block],
            }
        elif current is not None:
            current["blocks"].append(block)
        else:
            current = {
                "block_id": block.block_id,
                "heading": "",
                "blocks": [block],
            }
    if current is not None:
        sections.append(current)
    return sections


def _align_type_iri(heading: str, snapshot: TypeSnapshot) -> str | None:
    for obj in snapshot.objects:
        if heading == obj.label:
            return obj.iri
    return None


def _section_text(blocks: list[TextBlock]) -> str:
    return "\n".join(block.text for block in blocks)


class HybridExtractor:
    name = "hybrid"

    def extract(self, doc: ParsedDocument, snapshot: TypeSnapshot, llm: LlmGateway) -> ExtractionResult:
        chunks = []
        for section in _sections(doc):
            heading = section["heading"]
            chunks.append(
                {
                    "block_id": section["block_id"],
                    "heading": heading,
                    "type_iri": _align_type_iri(heading, snapshot),
                    "text": _section_text(section["blocks"]),
                }
            )
        messages = [
            {
                "role": "system",
                "content": (
                    "Extract candidates from heading-aligned chunks. "
                    "When type_iri is set, bind instances in that chunk to it."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "existing": serialize_snapshot(snapshot),
                        "filename": doc.filename,
                        "chunks": chunks,
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        payload = llm.complete_structured(EXTRACTION_SCHEMA, messages)
        return result_from_dict(payload)
