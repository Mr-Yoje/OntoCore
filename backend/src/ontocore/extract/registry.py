from ontocore.extract.engine import LlmExtractor
from ontocore.extract.ports import Extractor

_EXTRACTORS: dict[str, Extractor] = {
    "llm": LlmExtractor(),
}


def get_extractor(name: str) -> Extractor:
    return _EXTRACTORS[name]
