from dataclasses import dataclass, field
from typing import Any, Literal

LiteralKind = Literal["text", "number", "date"]
TypeCandidateKind = Literal["object", "attribute", "relation"]
TypeCandidateStatus = Literal["proposed", "accepted", "rejected"]
InstanceCandidateStatus = Literal["proposed", "projected", "skipped"]
JobStatus = Literal[
    "queued", "running", "failed", "partial", "completed",
    "types_accepted_graph_pending",
]


@dataclass(frozen=True)
class OntoObject:
    iri: str
    label: str
    definition: str
    parent_iri: str | None = None


@dataclass(frozen=True)
class OntoAttribute:
    iri: str
    label: str
    definition: str
    owner_iri: str
    literal_kind: LiteralKind


@dataclass(frozen=True)
class OntoRelation:
    iri: str
    label: str
    definition: str
    source_iri: str
    target_iri: str


@dataclass(frozen=True)
class TypeSnapshot:
    objects: tuple[OntoObject, ...]
    attributes: tuple[OntoAttribute, ...]
    relations: tuple[OntoRelation, ...]


@dataclass(frozen=True)
class TypeNetworkNode:
    iri: str
    label: str
    definition: str
    parent_iri: str | None


@dataclass(frozen=True)
class TypeNetworkEdge:
    iri: str
    label: str
    source_iri: str
    target_iri: str


@dataclass(frozen=True)
class TypeNetwork:
    nodes: tuple[TypeNetworkNode, ...]
    edges: tuple[TypeNetworkEdge, ...]


@dataclass(frozen=True)
class TextBlock:
    block_id: str
    kind: Literal["heading", "paragraph", "list"]
    text: str


@dataclass(frozen=True)
class ParsedDocument:
    filename: str
    full_text: str
    blocks: tuple[TextBlock, ...]


@dataclass
class ObjectCandidateDraft:
    iri: str
    label: str
    definition: str
    parent_iri: str | None
    evidence: str
    block_id: str
    confidence: float


@dataclass
class AttributeCandidateDraft:
    iri: str
    label: str
    definition: str
    owner_iri: str
    literal_kind: LiteralKind
    evidence: str
    block_id: str
    confidence: float


@dataclass
class RelationCandidateDraft:
    iri: str
    label: str
    definition: str
    source_iri: str
    target_iri: str
    evidence: str
    block_id: str
    confidence: float


@dataclass
class InstanceSuggestionDraft:
    local_id: str
    type_iri: str
    label: str
    data: dict[str, Any]
    evidence: str
    block_id: str
    confidence: float


@dataclass
class InstanceRelDraft:
    source_local_id: str
    target_local_id: str
    predicate_iri: str
    evidence: str
    block_id: str
    confidence: float


@dataclass
class BlockFailure:
    block_id: str
    reason: str


@dataclass
class ExtractionResult:
    object_candidates: list[ObjectCandidateDraft]
    attribute_candidates: list[AttributeCandidateDraft]
    relation_candidates: list[RelationCandidateDraft]
    instance_suggestions: list[InstanceSuggestionDraft]
    instance_rel_suggestions: list[InstanceRelDraft]
    block_failures: list[BlockFailure] = field(default_factory=list)
