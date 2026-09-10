from __future__ import annotations

import re

from ontocore.constants import NS
from ontocore.extract.llm import LlmGateway
from ontocore.models import (
    ExtractionResult,
    InstanceSuggestionDraft,
    ObjectCandidateDraft,
    ParsedDocument,
    TextBlock,
    TypeSnapshot,
)

_LOCAL_NAME_RE = re.compile(r"[^A-Za-z0-9_]")


def _sections(doc: ParsedDocument) -> list[tuple[TextBlock, list[TextBlock]]]:
    sections: list[tuple[TextBlock, list[TextBlock]]] = []
    heading: TextBlock | None = None
    body: list[TextBlock] = []
    for block in doc.blocks:
        if block.kind == "heading":
            if heading is not None:
                sections.append((heading, body))
            heading = block
            body = []
        elif heading is not None:
            body.append(block)
    if heading is not None:
        sections.append((heading, body))
    return sections


def _local_name(title: str, block_id: str) -> str:
    cleaned = _LOCAL_NAME_RE.sub("", title)
    if not cleaned or not cleaned[0].isalpha():
        return f"obj_{block_id}"
    return cleaned


def _first_line(heading: TextBlock, body: list[TextBlock]) -> str:
    if body:
        return body[0].text.splitlines()[0].strip()
    return heading.text.splitlines()[0].strip()


def _evidence(heading: TextBlock, body: list[TextBlock]) -> str:
    parts = [heading.text, *(block.text for block in body)]
    return "\n".join(parts)


class RulesOnlyExtractor:
    name = "rules_only"

    def extract(self, doc: ParsedDocument, snapshot: TypeSnapshot, llm: LlmGateway) -> ExtractionResult:
        del llm
        label_to_iri = {obj.label: obj.iri for obj in snapshot.objects}
        objects: list[ObjectCandidateDraft] = []
        instances: list[InstanceSuggestionDraft] = []
        for heading, body in _sections(doc):
            type_iri = label_to_iri.get(heading.text)
            evidence = _evidence(heading, body)
            if type_iri:
                instances.append(
                    InstanceSuggestionDraft(
                        local_id=heading.block_id,
                        type_iri=type_iri,
                        label=_first_line(heading, body),
                        data={},
                        evidence=evidence,
                        block_id=heading.block_id,
                        confidence=0.5,
                    )
                )
            else:
                local = _local_name(heading.text, heading.block_id)
                objects.append(
                    ObjectCandidateDraft(
                        iri=f"{NS}{local}",
                        label=heading.text,
                        definition="",
                        parent_iri=None,
                        evidence=evidence,
                        block_id=heading.block_id,
                        confidence=0.5,
                    )
                )
        return ExtractionResult(
            object_candidates=objects,
            attribute_candidates=[],
            relation_candidates=[],
            instance_suggestions=instances,
            instance_rel_suggestions=[],
        )
