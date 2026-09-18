from __future__ import annotations

import os
import threading
from pathlib import Path

from pyoxigraph import DefaultGraph, Literal, NamedNode, Quad, RdfFormat, Store

from ontocore.constants import LITERAL_RANGE, NS, RANGE_LITERAL
from ontocore.errors import OntologyWriteError
from ontocore.models import (
    LiteralKind,
    OntoAttribute,
    OntoObject,
    OntoRelation,
    TypeNetwork,
    TypeNetworkEdge,
    TypeNetworkNode,
    TypeSnapshot,
)
from ontocore.ontology.profile import assert_profile_store, load_turtle

OWL = "http://www.w3.org/2002/07/owl#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
XSD = "http://www.w3.org/2001/XMLSchema#"

RDF_TYPE = NamedNode(f"{RDF}type")
RDFS_LABEL = NamedNode(f"{RDFS}label")
RDFS_COMMENT = NamedNode(f"{RDFS}comment")
RDFS_SUBCLASS_OF = NamedNode(f"{RDFS}subClassOf")
RDFS_DOMAIN = NamedNode(f"{RDFS}domain")
RDFS_RANGE = NamedNode(f"{RDFS}range")
OWL_CLASS = NamedNode(f"{OWL}Class")
OWL_DATATYPE_PROPERTY = NamedNode(f"{OWL}DatatypeProperty")
OWL_OBJECT_PROPERTY = NamedNode(f"{OWL}ObjectProperty")

_UNSET = ...


def _node(iri: str) -> NamedNode:
    return NamedNode(iri)


def _literal(value: str) -> Literal:
    return Literal(value)


def _declared_iris(store: Store) -> set[str]:
    iris: set[str] = set()
    for kind in (OWL_CLASS, OWL_DATATYPE_PROPERTY, OWL_OBJECT_PROPERTY):
        for quad in store.quads_for_pattern(None, RDF_TYPE, kind):
            subject = quad.subject
            if isinstance(subject, NamedNode):
                iris.add(subject.value)
    return iris


_SNAPSHOT_NAME = "ontology.nq"


class OntologyRepository:
    def __init__(self, path: str | None = None) -> None:
        self._lock = threading.RLock()
        self._store = Store()
        self._snapshot_path: Path | None = None
        self._lock_file = None
        if path is not None:
            root = Path(path)
            data_dir = root.parent if root.name == "oxigraph" else root
            data_dir.mkdir(parents=True, exist_ok=True)
            self._snapshot_path = data_dir / _SNAPSHOT_NAME
            self._acquire_lock(data_dir)
            self._load_durable(data_dir)

    def _acquire_lock(self, data_dir: Path) -> None:
        lock_path = data_dir / "ontology.lock"
        handle = open(lock_path, "a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise OntologyWriteError("本体库已被其他进程打开") from exc
        self._lock_file = handle

    def _load_durable(self, data_dir: Path) -> None:
        snapshot = data_dir / _SNAPSHOT_NAME
        if snapshot.exists() and snapshot.stat().st_size > 0:
            self._store.bulk_load(snapshot.read_bytes(), format=RdfFormat.N_QUADS)
            return
        rocks = data_dir / "oxigraph" if data_dir.name != "oxigraph" else data_dir
        if not rocks.exists():
            return
        try:
            legacy = Store(str(rocks))
            payload = legacy.dump(format=RdfFormat.N_QUADS)
        except (OSError, RuntimeError):
            return
        if payload:
            self._store.bulk_load(payload, format=RdfFormat.N_QUADS)
            self._persist()

    def _persist(self) -> None:
        if self._snapshot_path is None:
            return
        payload = self._store.dump(format=RdfFormat.N_QUADS)
        tmp = self._snapshot_path.with_name(self._snapshot_path.name + ".tmp")
        tmp.write_bytes(payload)
        os.replace(tmp, self._snapshot_path)

    def close(self) -> None:
        with self._lock:
            try:
                self._persist()
            finally:
                handle = self._lock_file
                self._lock_file = None
                if handle is not None:
                    try:
                        handle.seek(0)
                        if os.name == "nt":
                            import msvcrt

                            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                        else:
                            import fcntl

                            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                    except OSError:
                        pass
                    handle.close()

    def snapshot(self) -> TypeSnapshot:
        with self._lock:
            return TypeSnapshot(
                objects=tuple(self._objects()),
                attributes=tuple(self._attributes()),
                relations=tuple(self._relations()),
            )

    def type_network(self) -> TypeNetwork:
        with self._lock:
            nodes = tuple(
                TypeNetworkNode(
                    iri=obj.iri,
                    label=obj.label,
                    definition=obj.definition,
                    parent_iri=obj.parent_iri,
                )
                for obj in self._objects()
            )
            edges = tuple(
                TypeNetworkEdge(
                    iri=rel.iri,
                    label=rel.label,
                    source_iri=rel.source_iri,
                    target_iri=rel.target_iri,
                )
                for rel in self._relations()
            )
            return TypeNetwork(nodes=nodes, edges=edges)

    def create_object(self, item: OntoObject) -> None:
        with self._lock:
            if self.has_iri(item.iri):
                raise OntologyWriteError(f"IRI already exists: {item.iri}")
            if item.parent_iri is not None and not self._is_class(item.parent_iri):
                raise OntologyWriteError(f"parent object does not exist: {item.parent_iri}")
            subject = _node(item.iri)
            self._add(subject, RDF_TYPE, OWL_CLASS)
            self._add(subject, RDFS_LABEL, _literal(item.label))
            self._add(subject, RDFS_COMMENT, _literal(item.definition))
            if item.parent_iri is not None:
                if self._parents(item.iri):
                    raise OntologyWriteError(f"object already has a parent: {item.iri}")
                self._add(subject, RDFS_SUBCLASS_OF, _node(item.parent_iri))
            self._persist()

    def update_object(
        self,
        iri: str,
        *,
        label: str | None = None,
        definition: str | None = None,
        parent_iri: str | None | object = _UNSET,
    ) -> None:
        with self._lock:
            if not self._is_class(iri):
                raise OntologyWriteError(f"object does not exist: {iri}")
            subject = _node(iri)
            if label is not None:
                self._replace(subject, RDFS_LABEL, _literal(label))
            if definition is not None:
                self._replace(subject, RDFS_COMMENT, _literal(definition))
            if parent_iri is not _UNSET:
                if parent_iri is not None:
                    parent = str(parent_iri)
                    if parent == iri:
                        raise OntologyWriteError(f"object cannot be its own parent: {iri}")
                    if not self._is_class(parent):
                        raise OntologyWriteError(f"parent object does not exist: {parent}")
                    if parent in self._descendants(iri):
                        raise OntologyWriteError(f"parent cannot be a descendant: {parent}")
                    self._assert_reparent_attribute_labels(iri, parent)
                self._clear_predicate(subject, RDFS_SUBCLASS_OF)
                if parent_iri is not None:
                    self._add(subject, RDFS_SUBCLASS_OF, _node(parent))
            self._persist()

    def delete_object(self, iri: str) -> None:
        with self._lock:
            if not self._is_class(iri):
                raise OntologyWriteError(f"object does not exist: {iri}")
            node = _node(iri)
            if any(self._store.quads_for_pattern(None, RDFS_SUBCLASS_OF, node)):
                raise OntologyWriteError(f"object has child objects: {iri}")
            if any(self._store.quads_for_pattern(None, RDFS_DOMAIN, node)):
                raise OntologyWriteError(f"object is referenced by a property domain: {iri}")
            if any(self._store.quads_for_pattern(None, RDFS_RANGE, node)):
                raise OntologyWriteError(f"object is referenced by a property range: {iri}")
            self._remove_subject(iri)
            self._persist()

    def create_attribute(self, item: OntoAttribute) -> None:
        with self._lock:
            if self.has_iri(item.iri):
                raise OntologyWriteError(f"IRI already exists: {item.iri}")
            if not self._is_class(item.owner_iri):
                raise OntologyWriteError(f"owner object does not exist: {item.owner_iri}")
            self._assert_attribute_label_available(item.owner_iri, item.label, exclude_iri=None)
            subject = _node(item.iri)
            self._add(subject, RDF_TYPE, OWL_DATATYPE_PROPERTY)
            self._add(subject, RDFS_LABEL, _literal(item.label))
            self._add(subject, RDFS_COMMENT, _literal(item.definition))
            self._add(subject, RDFS_DOMAIN, _node(item.owner_iri))
            self._add(subject, RDFS_RANGE, _node(LITERAL_RANGE[item.literal_kind]))
            self._persist()

    def update_attribute(
        self,
        iri: str,
        *,
        label: str | None = None,
        definition: str | None = None,
        literal_kind: LiteralKind | None = None,
    ) -> None:
        with self._lock:
            current = self._attribute_by_iri(iri)
            if current is None:
                raise OntologyWriteError(f"attribute does not exist: {iri}")
            subject = _node(iri)
            if label is not None and label != current.label:
                self._assert_attribute_label_available(current.owner_iri, label, exclude_iri=iri)
                self._replace(subject, RDFS_LABEL, _literal(label))
            if definition is not None:
                self._replace(subject, RDFS_COMMENT, _literal(definition))
            if literal_kind is not None:
                self._replace(subject, RDFS_RANGE, _node(LITERAL_RANGE[literal_kind]))
            self._persist()

    def delete_attribute(self, iri: str) -> None:
        with self._lock:
            if self._attribute_by_iri(iri) is None:
                raise OntologyWriteError(f"attribute does not exist: {iri}")
            self._remove_subject(iri)
            self._persist()

    def create_relation(self, item: OntoRelation) -> None:
        with self._lock:
            if self.has_iri(item.iri):
                raise OntologyWriteError(f"IRI already exists: {item.iri}")
            if not self._is_class(item.source_iri):
                raise OntologyWriteError(f"source object does not exist: {item.source_iri}")
            if not self._is_class(item.target_iri):
                raise OntologyWriteError(f"target object does not exist: {item.target_iri}")
            subject = _node(item.iri)
            if any(self._store.quads_for_pattern(subject, RDFS_DOMAIN, None)):
                raise OntologyWriteError(f"relation already has a domain: {item.iri}")
            if any(self._store.quads_for_pattern(subject, RDFS_RANGE, None)):
                raise OntologyWriteError(f"relation already has a range: {item.iri}")
            self._add(subject, RDF_TYPE, OWL_OBJECT_PROPERTY)
            self._add(subject, RDFS_LABEL, _literal(item.label))
            self._add(subject, RDFS_COMMENT, _literal(item.definition))
            self._add(subject, RDFS_DOMAIN, _node(item.source_iri))
            self._add(subject, RDFS_RANGE, _node(item.target_iri))
            self._persist()

    def update_relation(
        self,
        iri: str,
        *,
        label: str | None = None,
        definition: str | None = None,
    ) -> None:
        with self._lock:
            if self._relation_by_iri(iri) is None:
                raise OntologyWriteError(f"relation does not exist: {iri}")
            subject = _node(iri)
            if label is not None:
                self._replace(subject, RDFS_LABEL, _literal(label))
            if definition is not None:
                self._replace(subject, RDFS_COMMENT, _literal(definition))
            self._persist()

    def delete_relation(self, iri: str) -> None:
        with self._lock:
            if self._relation_by_iri(iri) is None:
                raise OntologyWriteError(f"relation does not exist: {iri}")
            self._remove_subject(iri)
            self._persist()

    def inherited_attributes(self, object_iri: str) -> list[OntoAttribute]:
        with self._lock:
            if not self._is_class(object_iri):
                raise OntologyWriteError(f"object does not exist: {object_iri}")
            owners = set(self._ancestors(object_iri))
            return [attr for attr in self._attributes() if attr.owner_iri in owners]

    def attributes_for(self, object_iri: str) -> list[OntoAttribute]:
        with self._lock:
            if not self._is_class(object_iri):
                raise OntologyWriteError(f"object does not exist: {object_iri}")
            owners = {object_iri, *self._ancestors(object_iri)}
            return [attr for attr in self._attributes() if attr.owner_iri in owners]

    def inherited_relations(self, object_iri: str) -> list[OntoRelation]:
        with self._lock:
            if not self._is_class(object_iri):
                raise OntologyWriteError(f"object does not exist: {object_iri}")
            owners = set(self._ancestors(object_iri))
            return [rel for rel in self._relations() if rel.source_iri in owners]

    def export_turtle(self) -> str:
        with self._lock:
            data = self._store.dump(
                format=RdfFormat.TURTLE,
                from_graph=DefaultGraph(),
                prefixes={"": NS, "owl": OWL, "rdfs": RDFS, "xsd": XSD},
            )
            return data.decode("utf-8")

    def export_jsonld(self) -> str:
        with self._lock:
            try:
                data = self._store.dump(format=RdfFormat.JSON_LD)
                return data.decode("utf-8")
            except (ValueError, OSError):
                graph = [{"@id": item.iri} for item in self._objects()]
                graph.extend({"@id": item.iri} for item in self._attributes())
                graph.extend({"@id": item.iri} for item in self._relations())
                import json

                return json.dumps({"@graph": graph})

    def import_turtle(self, ttl: str, *, force: bool = False) -> None:
        incoming = load_turtle(ttl)
        incoming_iris = _declared_iris(incoming)
        with self._lock:
            extra_classes = {
                iri
                for iri in _declared_iris(self._store)
                if any(self._store.quads_for_pattern(_node(iri), RDF_TYPE, OWL_CLASS))
            }
            assert_profile_store(incoming, extra_classes=extra_classes)
            existing = _declared_iris(self._store)
            overlap = incoming_iris & existing
            if overlap and not force:
                raise OntologyWriteError("import IRI intersection is not empty")
            if overlap and force:
                for iri in overlap:
                    self._remove_subject(iri)
            for quad in incoming:
                self._store.add(quad)
            self._persist()

    def has_iri(self, iri: str) -> bool:
        with self._lock:
            node = _node(iri)
            return any(self._store.quads_for_pattern(node, None, None))

    def _add(self, subject: NamedNode, predicate: NamedNode, obj: NamedNode | Literal) -> None:
        self._store.add(Quad(subject, predicate, obj))

    def _clear_predicate(self, subject: NamedNode, predicate: NamedNode) -> None:
        for quad in list(self._store.quads_for_pattern(subject, predicate, None)):
            self._store.remove(quad)

    def _replace(self, subject: NamedNode, predicate: NamedNode, obj: NamedNode | Literal) -> None:
        self._clear_predicate(subject, predicate)
        self._add(subject, predicate, obj)

    def _remove_subject(self, iri: str) -> None:
        node = _node(iri)
        for quad in list(self._store.quads_for_pattern(node, None, None)):
            self._store.remove(quad)

    def _is_class(self, iri: str) -> bool:
        return any(self._store.quads_for_pattern(_node(iri), RDF_TYPE, OWL_CLASS))

    def _text(self, subject: NamedNode, predicate: NamedNode) -> str:
        for quad in self._store.quads_for_pattern(subject, predicate, None):
            obj = quad.object
            if isinstance(obj, Literal):
                return obj.value
        return ""

    def _named(self, subject: NamedNode, predicate: NamedNode) -> str | None:
        for quad in self._store.quads_for_pattern(subject, predicate, None):
            obj = quad.object
            if isinstance(obj, NamedNode):
                return obj.value
        return None

    def _parents(self, iri: str) -> list[str]:
        parents: list[str] = []
        for quad in self._store.quads_for_pattern(_node(iri), RDFS_SUBCLASS_OF, None):
            obj = quad.object
            if isinstance(obj, NamedNode):
                parents.append(obj.value)
        return parents

    def _objects(self) -> list[OntoObject]:
        items: list[OntoObject] = []
        for quad in self._store.quads_for_pattern(None, RDF_TYPE, OWL_CLASS):
            subject = quad.subject
            if not isinstance(subject, NamedNode):
                continue
            parents = self._parents(subject.value)
            items.append(
                OntoObject(
                    iri=subject.value,
                    label=self._text(subject, RDFS_LABEL),
                    definition=self._text(subject, RDFS_COMMENT),
                    parent_iri=parents[0] if parents else None,
                )
            )
        items.sort(key=lambda item: item.iri)
        return items

    def _attributes(self) -> list[OntoAttribute]:
        items: list[OntoAttribute] = []
        for quad in self._store.quads_for_pattern(None, RDF_TYPE, OWL_DATATYPE_PROPERTY):
            subject = quad.subject
            if not isinstance(subject, NamedNode):
                continue
            owner = self._named(subject, RDFS_DOMAIN)
            range_iri = self._named(subject, RDFS_RANGE)
            if owner is None or range_iri is None or range_iri not in RANGE_LITERAL:
                continue
            items.append(
                OntoAttribute(
                    iri=subject.value,
                    label=self._text(subject, RDFS_LABEL),
                    definition=self._text(subject, RDFS_COMMENT),
                    owner_iri=owner,
                    literal_kind=RANGE_LITERAL[range_iri],
                )
            )
        items.sort(key=lambda item: item.iri)
        return items

    def _relations(self) -> list[OntoRelation]:
        items: list[OntoRelation] = []
        for quad in self._store.quads_for_pattern(None, RDF_TYPE, OWL_OBJECT_PROPERTY):
            subject = quad.subject
            if not isinstance(subject, NamedNode):
                continue
            source = self._named(subject, RDFS_DOMAIN)
            target = self._named(subject, RDFS_RANGE)
            if source is None or target is None:
                continue
            items.append(
                OntoRelation(
                    iri=subject.value,
                    label=self._text(subject, RDFS_LABEL),
                    definition=self._text(subject, RDFS_COMMENT),
                    source_iri=source,
                    target_iri=target,
                )
            )
        items.sort(key=lambda item: item.iri)
        return items

    def _attribute_by_iri(self, iri: str) -> OntoAttribute | None:
        for item in self._attributes():
            if item.iri == iri:
                return item
        return None

    def _relation_by_iri(self, iri: str) -> OntoRelation | None:
        for item in self._relations():
            if item.iri == iri:
                return item
        return None

    def _ancestors(self, iri: str) -> list[str]:
        found: list[str] = []
        seen: set[str] = set()
        current = iri
        while True:
            parents = self._parents(current)
            if not parents:
                break
            parent = parents[0]
            if parent in seen:
                break
            seen.add(parent)
            found.append(parent)
            current = parent
        return found

    def _descendants(self, iri: str) -> list[str]:
        children_of: dict[str, list[str]] = {}
        for obj in self._objects():
            if obj.parent_iri is not None:
                children_of.setdefault(obj.parent_iri, []).append(obj.iri)
        found: list[str] = []
        stack = list(children_of.get(iri, []))
        seen: set[str] = set()
        while stack:
            child = stack.pop()
            if child in seen:
                continue
            seen.add(child)
            found.append(child)
            stack.extend(children_of.get(child, []))
        return found

    def _assert_attribute_label_available(
        self, owner_iri: str, label: str, *, exclude_iri: str | None
    ) -> None:
        related = {owner_iri, *self._ancestors(owner_iri), *self._descendants(owner_iri)}
        self._assert_label_free_on(related, label, exclude_iri=exclude_iri)

    def _assert_reparent_attribute_labels(self, iri: str, new_parent: str) -> None:
        subtree = {iri, *self._descendants(iri)}
        related = {iri, new_parent, *self._ancestors(new_parent), *self._descendants(iri)}
        for attr in self._attributes():
            if attr.owner_iri not in subtree:
                continue
            self._assert_label_free_on(related, attr.label, exclude_iri=attr.iri)

    def _assert_label_free_on(
        self, related: set[str], label: str, *, exclude_iri: str | None
    ) -> None:
        for attr in self._attributes():
            if exclude_iri is not None and attr.iri == exclude_iri:
                continue
            if attr.owner_iri in related and attr.label == label:
                raise OntologyWriteError(
                    f"attribute label {label!r} already exists on the inheritance chain"
                )
