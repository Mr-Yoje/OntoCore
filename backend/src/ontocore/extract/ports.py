from collections.abc import Callable
from typing import Protocol

from ontocore.extract.llm import LlmGateway
from ontocore.models import ExtractionGuides, ExtractionResult, ParsedDocument, TypeSnapshot


class Extractor(Protocol):
    name: str

    def extract(
        self,
        doc: ParsedDocument,
        snapshot: TypeSnapshot,
        llm: LlmGateway,
        *,
        guides: ExtractionGuides | None = None,
        on_chunk_done: Callable[[int, int], None] | None = None,
    ) -> ExtractionResult: ...
