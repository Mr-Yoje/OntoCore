from pyoxigraph import BlankNode, NamedNode, RdfFormat, Store

from ontocore.constants import LITERAL_RANGE
from ontocore.errors import ProfileViolation

OWL = "http://www.w3.org/2002/07/owl#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"

RDF_TYPE = NamedNode(f"{RDF}type")
RDFS_LABEL = NamedNode(f"{RDFS}label")
RDFS_COMMENT = NamedNode(f"{RDFS}comment")
RDFS_SUBCLASS_OF = NamedNode(f"{RDFS}subClassOf")
RDFS_DOMAIN = NamedNode(f"{RDFS}domain")
RDFS_RANGE = NamedNode(f"{RDFS}range")
OWL_CLASS = NamedNode(f"{OWL}Class")
OWL_DATATYPE_PROPERTY = NamedNode(f"{OWL}DatatypeProperty")
OWL_OBJECT_PROPERTY = NamedNode(f"{OWL}ObjectProperty")
OWL_RESTRICTION = NamedNode(f"{OWL}Restriction")
OWL_EQUIVALENT_CLASS = NamedNode(f"{OWL}equivalentClass")
OWL_INTERSECTION_OF = NamedNode(f"{OWL}intersectionOf")
OWL_UNION_OF = NamedNode(f"{OWL}unionOf")

ALLOWED_PREDICATES = frozenset(
    {
        RDF_TYPE,
        RDFS_LABEL,
        RDFS_COMMENT,
        RDFS_SUBCLASS_OF,
        RDFS_DOMAIN,
        RDFS_RANGE,
    }
)
ALLOWED_TYPES = frozenset({OWL_CLASS, OWL_DATATYPE_PROPERTY, OWL_OBJECT_PROPERTY})
LITERAL_RANGE_NODES = frozenset(NamedNode(iri) for iri in LITERAL_RANGE.values())


def _named_values(store: Store, subject: NamedNode, predicate: NamedNode) -> list[str]:
    values: list[str] = []
    for quad in store.quads_for_pattern(subject, predicate, None):
        obj = quad.object
        if isinstance(obj, NamedNode):
            values.append(obj.value)
        else:
            raise ProfileViolation(f"{predicate.value} must reference a named IRI")
    return values


def _classes(store: Store) -> set[str]:
    found: set[str] = set()
    for quad in store.quads_for_pattern(None, RDF_TYPE, OWL_CLASS):
        subject = quad.subject
        if isinstance(subject, NamedNode):
            found.add(subject.value)
    return found


def assert_profile_store(store: Store, *, extra_classes: set[str] | None = None) -> None:
    classes = _classes(store)
    if extra_classes:
        classes = classes | extra_classes

    subclass_of: dict[str, list[str]] = {}
    obj_domains: dict[str, list[str]] = {}
    obj_ranges: dict[str, list[str]] = {}
    data_domains: dict[str, list[str]] = {}
    data_ranges: dict[str, list[str]] = {}
    types: dict[str, set[NamedNode]] = {}

    for quad in store:
        predicate = quad.predicate
        obj = quad.object
        subject = quad.subject

        if obj == OWL_RESTRICTION or (
            predicate == RDF_TYPE and obj == OWL_RESTRICTION
        ):
            raise ProfileViolation("owl:Restriction is not allowed")

        if predicate in {OWL_EQUIVALENT_CLASS, OWL_INTERSECTION_OF, OWL_UNION_OF}:
            if isinstance(obj, BlankNode) or isinstance(subject, BlankNode):
                raise ProfileViolation("blank equivalentClass/intersectionOf/unionOf is not allowed")
            raise ProfileViolation(f"predicate not allowed: {predicate.value}")

        if predicate not in ALLOWED_PREDICATES:
            raise ProfileViolation(f"predicate not allowed: {predicate.value}")

        if predicate == RDF_TYPE:
            if obj not in ALLOWED_TYPES:
                raise ProfileViolation("rdf:type must be Class, DatatypeProperty, or ObjectProperty")
            if not isinstance(subject, NamedNode):
                raise ProfileViolation("typed terms must be named IRIs")
            types.setdefault(subject.value, set()).add(obj)

        if predicate == RDFS_SUBCLASS_OF:
            if not isinstance(subject, NamedNode) or not isinstance(obj, NamedNode):
                raise ProfileViolation("rdfs:subClassOf must reference a named IRI")
            subclass_of.setdefault(subject.value, []).append(obj.value)

        if predicate in {RDFS_DOMAIN, RDFS_RANGE} and not isinstance(obj, NamedNode):
            raise ProfileViolation(f"{predicate.value} must reference a named IRI")

        if isinstance(subject, NamedNode) and predicate == RDFS_DOMAIN and isinstance(obj, NamedNode):
            if OWL_OBJECT_PROPERTY in types.get(subject.value, set()) or any(
                store.quads_for_pattern(subject, RDF_TYPE, OWL_OBJECT_PROPERTY)
            ):
                obj_domains.setdefault(subject.value, []).append(obj.value)
            if OWL_DATATYPE_PROPERTY in types.get(subject.value, set()) or any(
                store.quads_for_pattern(subject, RDF_TYPE, OWL_DATATYPE_PROPERTY)
            ):
                data_domains.setdefault(subject.value, []).append(obj.value)

        if isinstance(subject, NamedNode) and predicate == RDFS_RANGE and isinstance(obj, NamedNode):
            if OWL_OBJECT_PROPERTY in types.get(subject.value, set()) or any(
                store.quads_for_pattern(subject, RDF_TYPE, OWL_OBJECT_PROPERTY)
            ):
                obj_ranges.setdefault(subject.value, []).append(obj.value)
            if OWL_DATATYPE_PROPERTY in types.get(subject.value, set()) or any(
                store.quads_for_pattern(subject, RDF_TYPE, OWL_DATATYPE_PROPERTY)
            ):
                data_ranges.setdefault(subject.value, []).append(obj.value)

    for iri, parents in subclass_of.items():
        if len(parents) > 1:
            raise ProfileViolation(f"more than one rdfs:subClassOf: {iri}")
        parent = parents[0]
        if parent not in classes:
            raise ProfileViolation(f"rdfs:subClassOf must reference a class: {parent}")

    for iri in {q.subject.value for q in store.quads_for_pattern(None, RDF_TYPE, OWL_OBJECT_PROPERTY) if isinstance(q.subject, NamedNode)}:
        domains = obj_domains.get(iri) or _named_values(store, NamedNode(iri), RDFS_DOMAIN)
        ranges = obj_ranges.get(iri) or _named_values(store, NamedNode(iri), RDFS_RANGE)
        if len(domains) > 1:
            raise ProfileViolation(f"ObjectProperty has more than one domain: {iri}")
        if len(ranges) > 1:
            raise ProfileViolation(f"ObjectProperty has more than one range: {iri}")
        for target in domains + ranges:
            if target not in classes:
                raise ProfileViolation(f"domain/range must reference a class: {target}")

    for iri in {q.subject.value for q in store.quads_for_pattern(None, RDF_TYPE, OWL_DATATYPE_PROPERTY) if isinstance(q.subject, NamedNode)}:
        domains = data_domains.get(iri) or _named_values(store, NamedNode(iri), RDFS_DOMAIN)
        ranges = data_ranges.get(iri) or _named_values(store, NamedNode(iri), RDFS_RANGE)
        if len(domains) > 1:
            raise ProfileViolation(f"DatatypeProperty has more than one domain: {iri}")
        if len(ranges) > 1:
            raise ProfileViolation(f"DatatypeProperty has more than one range: {iri}")
        for target in domains:
            if target not in classes:
                raise ProfileViolation(f"domain/range must reference a class: {target}")
        for target in ranges:
            if NamedNode(target) not in LITERAL_RANGE_NODES:
                raise ProfileViolation(f"DatatypeProperty range is not a literal: {target}")


def load_turtle(ttl: str) -> Store:
    store = Store()
    try:
        payload: str | bytes = ttl
        store.load(payload, format=RdfFormat.TURTLE)
    except Exception as exc:
        raise ProfileViolation(f"invalid turtle: {exc}") from exc
    return store


def assert_profile_turtle(ttl: str, *, extra_classes: set[str] | None = None) -> Store:
    store = load_turtle(ttl)
    assert_profile_store(store, extra_classes=extra_classes)
    return store
