from ontocore.extract.hybrid import HybridExtractor
from ontocore.extract.llm_only import LlmOnlyExtractor
from ontocore.extract.ports import Extractor
from ontocore.extract.rules_only import RulesOnlyExtractor

_EXTRACTORS: dict[str, Extractor] = {
    "hybrid": HybridExtractor(),
    "llm_only": LlmOnlyExtractor(),
    "rules_only": RulesOnlyExtractor(),
}


def get_extractor(name: str) -> Extractor:
    return _EXTRACTORS[name]
