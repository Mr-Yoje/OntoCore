from ontocore.constants import NS
from ontocore.errors import ProfileViolation
from ontocore.ontology.profile import assert_profile_turtle


PREFIX = f"""
@prefix : <{NS}> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
"""


def test_named_object_hierarchy_ok():
    ttl = f"""
    @prefix : <{NS}> .
    @prefix owl: <http://www.w3.org/2002/07/owl#> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    :Product a owl:Class ; rdfs:label "保险产品" ; rdfs:comment "一种保险产品" .
    :Critical a owl:Class ; rdfs:subClassOf :Product ; rdfs:label "重疾险" .
    """
    assert_profile_turtle(ttl)


def test_blank_restriction_rejected():
    ttl = f"""
    @prefix : <{NS}> .
    @prefix owl: <http://www.w3.org/2002/07/owl#> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    :Product a owl:Class .
    :Product rdfs:subClassOf [ a owl:Restriction ; owl:onProperty :p ; owl:someValuesFrom :Coverage ] .
    """
    try:
        assert_profile_turtle(ttl)
    except ProfileViolation:
        return
    raise AssertionError("expected ProfileViolation")


def _reject(ttl: str) -> None:
    try:
        assert_profile_turtle(ttl)
    except ProfileViolation:
        return
    raise AssertionError("expected ProfileViolation")


def test_two_subclassof_rejected():
    _reject(
        PREFIX
        + """
        :A a owl:Class .
        :B a owl:Class .
        :C a owl:Class ; rdfs:subClassOf :A, :B .
        """
    )


def test_blank_equivalentclass_rejected():
    _reject(
        PREFIX
        + """
        :A a owl:Class .
        :B a owl:Class .
        :A owl:equivalentClass [ owl:intersectionOf ( :B ) ] .
        """
    )


def test_object_property_two_domains_rejected():
    _reject(
        PREFIX
        + """
        :A a owl:Class .
        :B a owl:Class .
        :p a owl:ObjectProperty ; rdfs:domain :A ; rdfs:domain :B ; rdfs:range :A .
        """
    )


def test_object_property_two_ranges_rejected():
    _reject(
        PREFIX
        + """
        :A a owl:Class .
        :B a owl:Class .
        :p a owl:ObjectProperty ; rdfs:domain :A ; rdfs:range :A ; rdfs:range :B .
        """
    )


def test_datatype_property_range_not_literal_rejected():
    _reject(
        PREFIX
        + """
        :A a owl:Class .
        :name a owl:DatatypeProperty ; rdfs:domain :A ; rdfs:range xsd:boolean .
        """
    )


def test_domain_pointing_at_non_class_rejected():
    _reject(
        PREFIX
        + """
        :A a owl:Class .
        :q a owl:ObjectProperty .
        :p a owl:ObjectProperty ; rdfs:domain :q ; rdfs:range :A .
        """
    )


def test_unknown_predicate_rejected():
    _reject(
        PREFIX
        + """
        :A a owl:Class ; owl:versionInfo "1" .
        """
    )
