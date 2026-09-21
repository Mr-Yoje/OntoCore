from ontocore.models import ExtractionGuides, TypeSnapshot


def build_guides(
    snapshot: TypeSnapshot,
    *,
    object_iris: list[str],
    relation_iris: list[str],
    instances: list[dict],
) -> ExtractionGuides:
    object_set = set(object_iris)
    relation_set = set(relation_iris)
    objects = [
        {
            "iri": obj.iri,
            "label": obj.label,
            "definition": obj.definition,
            "parent_iri": obj.parent_iri,
        }
        for obj in snapshot.objects
        if obj.iri in object_set
    ]
    attributes = [
        {
            "iri": attr.iri,
            "label": attr.label,
            "definition": attr.definition,
            "owner_iri": attr.owner_iri,
            "literal_kind": attr.literal_kind,
        }
        for attr in snapshot.attributes
        if attr.owner_iri in object_set
    ]
    relations = [
        {
            "iri": rel.iri,
            "label": rel.label,
            "definition": rel.definition,
            "source_iri": rel.source_iri,
            "target_iri": rel.target_iri,
        }
        for rel in snapshot.relations
        if rel.iri in relation_set
    ]
    return ExtractionGuides(
        objects=objects,
        attributes=attributes,
        relations=relations,
        instances=list(instances),
    )
