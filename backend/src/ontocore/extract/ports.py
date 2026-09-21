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
    ) -> ExtractionResult: ...
