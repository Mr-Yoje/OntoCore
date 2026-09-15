import { FormEvent, ReactNode, useCallback, useEffect, useState } from "react";
import { api, localName } from "../api";
import { TypeNetwork } from "../components/TypeNetwork";
import { tipText, useTip } from "../tips";

type OntoObject = {
  iri: string;
  label: string;
  definition: string;
  parent_iri: string | null;
};

type OntoRelation = {
  iri: string;
  label: string;
  definition: string;
  source_iri: string;
  target_iri: string;
};

type OntoAttribute = {
  iri: string;
  label: string;
  definition: string;
  owner_iri: string;
  literal_kind: "text" | "number" | "date";
};

type AttrDraft = {
  key: number;
  label: string;
  definition: string;
  literal_kind: "text" | "number" | "date";
  local_name: string;
};

type TypeNet = {
  nodes: { iri: string; label: string; definition: string; parent_iri: string | null }[];
  edges: { iri: string; label: string; source_iri: string; target_iri: string }[];
};

function Modal({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    function onKey(ev: KeyboardEvent) {
      if (ev.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="modal-head">
          <h2>{title}</h2>
          <button type="button" className="btn-ghost" onClick={onClose} aria-label="关闭">
            ×
          </button>
        </header>
        <div className="modal-body stack">{children}</div>
      </div>
    </div>
  );
}

export function OntologyPage() {
  const showTip = useTip();
  const [objects, setObjects] = useState<OntoObject[]>([]);
  const [relations, setRelations] = useState<OntoRelation[]>([]);
  const [attributes, setAttributes] = useState<OntoAttribute[]>([]);
  const [network, setNetwork] = useState<TypeNet>({ nodes: [], edges: [] });
  const [selectedIri, setSelectedIri] = useState<string | null>(null);
  const [selectedRelIri, setSelectedRelIri] = useState<string | null>(null);
  const [objectModal, setObjectModal] = useState<"create" | "edit" | null>(null);
  const [relModal, setRelModal] = useState<"create" | "detail" | null>(null);

  const [label, setLabel] = useState("");
  const [definition, setDefinition] = useState("");
  const [parent, setParent] = useState("");
  const [local, setLocal] = useState("");

  const [attrLabel, setAttrLabel] = useState("");
  const [attrDef, setAttrDef] = useState("");
  const [attrKind, setAttrKind] = useState<"text" | "number" | "date">("text");
  const [attrLocal, setAttrLocal] = useState("");

  const [newAttrs, setNewAttrs] = useState<AttrDraft[]>([]);
  const [nextAttrKey, setNextAttrKey] = useState(1);

  const [relLabel, setRelLabel] = useState("");
  const [relDef, setRelDef] = useState("");
  const [relLocal, setRelLocal] = useState("");
  const [relSource, setRelSource] = useState("");
  const [relTarget, setRelTarget] = useState("");

  const selected = objects.find((o) => o.iri === selectedIri) ?? null;
  const selectedRel = relations.find((r) => r.iri === selectedRelIri) ?? null;
  const [editLabel, setEditLabel] = useState("");
  const [editDef, setEditDef] = useState("");
  const [editParent, setEditParent] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [objs, rels, net] = await Promise.all([
        api.listObjects() as Promise<OntoObject[]>,
        api.listRelations() as Promise<OntoRelation[]>,
        api.ontologyNetwork() as Promise<TypeNet>,
      ]);
      setObjects(objs);
      setRelations(rels);
      setNetwork(net);
      if (selectedIri) {
        const attrs = (await api.listObjectAttributes(localName(selectedIri))) as OntoAttribute[];
        setAttributes(attrs);
      } else {
        setAttributes([]);
      }
    } catch (e) {
      showTip("error", tipText(e));
    }
  }, [selectedIri, showTip]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!selected) return;
    setEditLabel(selected.label);
    setEditDef(selected.definition);
    setEditParent(selected.parent_iri ? localName(selected.parent_iri) : "");
  }, [selected]);

  const closeObjectModal = useCallback(() => setObjectModal(null), []);
  const closeRelModal = useCallback(() => setRelModal(null), []);

  function openCreateObject() {
    setRelModal(null);
    setObjectModal("create");
  }

  function openEditObject(iri: string) {
    setRelModal(null);
    setSelectedIri(iri);
    setObjectModal("edit");
  }

  function openCreateRel() {
    setObjectModal(null);
    setRelModal("create");
  }

  function openRelDetail(iri: string) {
    setObjectModal(null);
    setSelectedRelIri(iri);
    setRelModal("detail");
  }

  async function onSaveObject(ev: FormEvent) {
    ev.preventDefault();
    if (!selected) return;
    try {
      await api.patchObject(localName(selected.iri), {
        label: editLabel,
        definition: editDef,
        parent_local_name: editParent || null,
      });
      await refresh();
      showTip("ok", "已保存对象");
    } catch (e) {
      showTip("error", tipText(e));
    }
  }

  async function onDeleteObject() {
    if (!selected) return;
    try {
      await api.deleteObject(localName(selected.iri));
      setSelectedIri(null);
      setObjectModal(null);
      await refresh();
    } catch (e) {
      showTip("error", tipText(e));
    }
  }

  function updateNewAttr(key: number, patch: Partial<AttrDraft>) {
    setNewAttrs((rows) => rows.map((row) => (row.key === key ? { ...row, ...patch } : row)));
  }

  async function onCreateObject(ev: FormEvent) {
    ev.preventDefault();
    let createdIri: string | null = null;
    try {
      const created = (await api.createObject({
        local_name: local,
        label,
        definition,
        parent_local_name: parent || null,
      })) as { iri: string };
      createdIri = created.iri;
      const owner = localName(created.iri);
      for (const row of newAttrs) {
        const attrLabel = row.label.trim();
        if (!attrLabel) continue;
        const attrLocal = row.local_name.trim() || `attr_${row.key}`;
        await api.createAttribute(owner, {
          local_name: attrLocal,
          label: attrLabel,
          definition: row.definition.trim(),
          literal_kind: row.literal_kind,
        });
      }
      setLabel("");
      setDefinition("");
      setParent("");
      setLocal("");
      setNewAttrs([]);
      setSelectedIri(created.iri);
      setObjectModal(null);
      await refresh();
    } catch (e) {
      showTip("error", tipText(e));
      if (createdIri) {
        setLabel("");
        setDefinition("");
        setParent("");
        setLocal("");
        setSelectedIri(createdIri);
        setObjectModal("edit");
        await refresh();
      }
    }
  }

  async function onCreateAttr(ev: FormEvent) {
    ev.preventDefault();
    if (!selected) return;
    try {
      const created = (await api.createAttribute(localName(selected.iri), {
        local_name: attrLocal,
        label: attrLabel,
        definition: attrDef,
        literal_kind: attrKind,
      })) as { iri: string; label: string; definition: string };
      setAttributes((prev) => [
        ...prev,
        {
          iri: created.iri,
          label: created.label,
          definition: created.definition,
          owner_iri: selected.iri,
          literal_kind: attrKind,
        },
      ]);
      setAttrLabel("");
      setAttrDef("");
      setAttrLocal("");
      await refresh();
    } catch (e) {
      showTip("error", tipText(e));
    }
  }

  async function onCreateRel(ev: FormEvent) {
    ev.preventDefault();
    try {
      await api.createRelation({
        local_name: relLocal,
        label: relLabel,
        definition: relDef,
        source_local_name: relSource,
        target_local_name: relTarget,
      });
      setRelLabel("");
      setRelDef("");
      setRelLocal("");
      setRelModal(null);
      await refresh();
    } catch (e) {
      showTip("error", tipText(e));
    }
  }

  async function onDeleteRel() {
    if (!selectedRel) return;
    try {
      await api.deleteRelation(localName(selectedRel.iri));
      setSelectedRelIri(null);
      setRelModal(null);
      await refresh();
    } catch (e) {
      showTip("error", tipText(e));
    }
  }

  return (
    <main className="page">
      <header className="page-head">
        <div>
          <h1>本体</h1>
          <p className="kicker">管理对象、属性和关系</p>
        </div>
        <div className="actions">
          <p className="muted">
            {objects.length} 对象 · {relations.length} 关系
          </p>
          <button type="button" className="btn-primary" onClick={openCreateObject}>
            新建对象
          </button>
          <button type="button" onClick={openCreateRel}>
            新建关系
          </button>
        </div>
      </header>
      <div className="layout">
        <section className="panel stack object-panel">
          <h2>对象</h2>
          {objects.length === 0 ? (
            <p className="muted">还没有对象，请先新建</p>
          ) : (
            <ul className="entity-list">
              {objects.map((o) => (
                <li key={o.iri}>
                  <button
                    type="button"
                    aria-pressed={selectedIri === o.iri && objectModal === "edit"}
                    onClick={() => openEditObject(o.iri)}
                  >
                    {o.label}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="panel panel-canvas">
          <TypeNetwork
            nodes={network.nodes}
            edges={network.edges}
            onSelect={(kind, iri) => {
              if (kind === "node") openEditObject(iri);
              if (kind === "edge") openRelDetail(iri);
            }}
          />
        </section>
      </div>

      <Modal open={objectModal === "create"} title="新建对象" onClose={closeObjectModal}>
        <form className="stack" onSubmit={onCreateObject}>
          <label>
            显示名
            <input value={label} onChange={(e) => setLabel(e.target.value)} required />
          </label>
          <label>
            定义
            <textarea value={definition} onChange={(e) => setDefinition(e.target.value)} required />
          </label>
          <label>
            父对象
            <select value={parent} onChange={(e) => setParent(e.target.value)}>
              <option value="">（无）</option>
              {objects.map((o) => (
                <option key={o.iri} value={localName(o.iri)}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            本地名
            <input value={local} onChange={(e) => setLocal(e.target.value)} required />
          </label>
          <div className="stack">
            <p className="muted">属性（可选）</p>
            {newAttrs.map((row) => (
              <div key={row.key} className="attr-draft">
                <div className="field-row">
                  <label>
                    显示名
                    <input
                      value={row.label}
                      onChange={(e) => updateNewAttr(row.key, { label: e.target.value })}
                    />
                  </label>
                  <label>
                    本地名
                    <input
                      value={row.local_name}
                      onChange={(e) => updateNewAttr(row.key, { local_name: e.target.value })}
                      placeholder="可空，默认自动生成"
                    />
                  </label>
                </div>
                <label>
                  定义
                  <input
                    value={row.definition}
                    onChange={(e) => updateNewAttr(row.key, { definition: e.target.value })}
                  />
                </label>
                <label>
                  字面量
                  <select
                    value={row.literal_kind}
                    onChange={(e) =>
                      updateNewAttr(row.key, {
                        literal_kind: e.target.value as AttrDraft["literal_kind"],
                      })
                    }
                  >
                    <option value="text">文本</option>
                    <option value="number">数字</option>
                    <option value="date">日期</option>
                  </select>
                </label>
                <button
                  type="button"
                  className="btn-ghost"
                  onClick={() => setNewAttrs((rows) => rows.filter((r) => r.key !== row.key))}
                >
                  去掉此属性
                </button>
              </div>
            ))}
            <button
              type="button"
              className="btn-ghost"
              onClick={() => {
                setNewAttrs((rows) => [
                  ...rows,
                  {
                    key: nextAttrKey,
                    label: "",
                    definition: "",
                    literal_kind: "text",
                    local_name: "",
                  },
                ]);
                setNextAttrKey((n) => n + 1);
              }}
            >
              添加属性
            </button>
          </div>
          <button type="submit">创建</button>
        </form>
      </Modal>

      <Modal open={objectModal === "edit" && Boolean(selected)} title="对象" onClose={closeObjectModal}>
        {selected ? (
          <>
            <h3>{selected.label}</h3>
            <form className="stack" onSubmit={onSaveObject}>
              <label>
                显示名
                <input value={editLabel} onChange={(e) => setEditLabel(e.target.value)} required />
              </label>
              <label>
                定义
                <textarea value={editDef} onChange={(e) => setEditDef(e.target.value)} required />
              </label>
              <label>
                父对象
                <select value={editParent} onChange={(e) => setEditParent(e.target.value)}>
                  <option value="">（无）</option>
                  {objects
                    .filter((o) => o.iri !== selected.iri)
                    .map((o) => (
                      <option key={o.iri} value={localName(o.iri)}>
                        {o.label}
                      </option>
                    ))}
                </select>
              </label>
              <div className="actions">
                <button type="submit">保存对象</button>
                <button type="button" className="btn-danger" onClick={() => void onDeleteObject()}>
                  删除对象
                </button>
              </div>
            </form>
            <table>
              <thead>
                <tr>
                  <th>属性</th>
                  <th>定义</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {attributes.map((a) => (
                  <tr key={a.iri}>
                    <td>
                      {a.label}
                      {a.owner_iri !== selectedIri ? "（自父对象）" : ""}
                    </td>
                    <td>{a.definition}</td>
                    <td>
                      {a.owner_iri === selectedIri ? (
                        <button
                          type="button"
                          className="btn-danger"
                          onClick={async () => {
                            try {
                              await api.deleteAttribute(localName(a.iri));
                              await refresh();
                            } catch (e) {
                              showTip("error", tipText(e));
                            }
                          }}
                        >
                          删除
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <form className="stack" onSubmit={onCreateAttr}>
              <label>
                显示名
                <input value={attrLabel} onChange={(e) => setAttrLabel(e.target.value)} required />
              </label>
              <label>
                定义
                <input value={attrDef} onChange={(e) => setAttrDef(e.target.value)} required />
              </label>
              <label>
                字面量
                <select value={attrKind} onChange={(e) => setAttrKind(e.target.value as typeof attrKind)}>
                  <option value="text">文本</option>
                  <option value="number">数字</option>
                  <option value="date">日期</option>
                </select>
              </label>
              <label>
                本地名
                <input value={attrLocal} onChange={(e) => setAttrLocal(e.target.value)} required />
              </label>
              <button type="submit">新建属性</button>
            </form>
          </>
        ) : null}
      </Modal>

      <Modal open={relModal === "create"} title="新建关系" onClose={closeRelModal}>
        <form className="stack" onSubmit={onCreateRel}>
          <label>
            显示名
            <input value={relLabel} onChange={(e) => setRelLabel(e.target.value)} required />
          </label>
          <label>
            定义
            <input value={relDef} onChange={(e) => setRelDef(e.target.value)} required />
          </label>
          <label>
            起点
            <select value={relSource} onChange={(e) => setRelSource(e.target.value)} required>
              <option value="">选择对象</option>
              {objects.map((o) => (
                <option key={o.iri} value={localName(o.iri)}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            终点
            <select value={relTarget} onChange={(e) => setRelTarget(e.target.value)} required>
              <option value="">选择对象</option>
              {objects.map((o) => (
                <option key={o.iri} value={localName(o.iri)}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            本地名
            <input value={relLocal} onChange={(e) => setRelLocal(e.target.value)} required />
          </label>
          <button type="submit">创建</button>
        </form>
      </Modal>

      <Modal open={relModal === "detail" && Boolean(selectedRel)} title="关系" onClose={closeRelModal}>
        {selectedRel ? (
          <>
            <p>
              <strong>{selectedRel.label}</strong>
            </p>
            <p className="muted">{selectedRel.definition}</p>
            <p>
              {objects.find((o) => o.iri === selectedRel.source_iri)?.label ?? selectedRel.source_iri}
              {" → "}
              {objects.find((o) => o.iri === selectedRel.target_iri)?.label ?? selectedRel.target_iri}
            </p>
            <button type="button" className="btn-danger" onClick={() => void onDeleteRel()}>
              删除
            </button>
          </>
        ) : null}
      </Modal>
    </main>
  );
}
