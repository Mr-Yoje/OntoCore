import { FormEvent, useCallback, useEffect, useState } from "react";
import { ApiError, api, localName } from "../api";
import { TypeNetwork } from "../components/TypeNetwork";

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

type TypeNet = {
  nodes: { iri: string; label: string; definition: string; parent_iri: string | null }[];
  edges: { iri: string; label: string; source_iri: string; target_iri: string }[];
};

export function OntologyPage() {
  const [objects, setObjects] = useState<OntoObject[]>([]);
  const [relations, setRelations] = useState<OntoRelation[]>([]);
  const [attributes, setAttributes] = useState<OntoAttribute[]>([]);
  const [network, setNetwork] = useState<TypeNet>({ nodes: [], edges: [] });
  const [selectedIri, setSelectedIri] = useState<string | null>(null);
  const [error, setError] = useState("");

  const [label, setLabel] = useState("");
  const [definition, setDefinition] = useState("");
  const [parent, setParent] = useState("");
  const [local, setLocal] = useState("");

  const [attrLabel, setAttrLabel] = useState("");
  const [attrDef, setAttrDef] = useState("");
  const [attrKind, setAttrKind] = useState<"text" | "number" | "date">("text");
  const [attrLocal, setAttrLocal] = useState("");

  const [relLabel, setRelLabel] = useState("");
  const [relDef, setRelDef] = useState("");
  const [relLocal, setRelLocal] = useState("");
  const [relSource, setRelSource] = useState("");
  const [relTarget, setRelTarget] = useState("");

  const selected = objects.find((o) => o.iri === selectedIri) ?? null;
  const [editLabel, setEditLabel] = useState("");
  const [editDef, setEditDef] = useState("");
  const [editParent, setEditParent] = useState("");

  const refresh = useCallback(async () => {
    setError("");
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
      setError(e instanceof ApiError ? e.detail : String(e));
    }
  }, [selectedIri]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!selected) return;
    setEditLabel(selected.label);
    setEditDef(selected.definition);
    setEditParent(selected.parent_iri ? localName(selected.parent_iri) : "");
  }, [selected]);

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
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    }
  }

  async function onDeleteObject() {
    if (!selected) return;
    try {
      await api.deleteObject(localName(selected.iri));
      setSelectedIri(null);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    }
  }

  async function onCreateObject(ev: FormEvent) {
    ev.preventDefault();
    try {
      await api.createObject({
        local_name: local,
        label,
        definition,
        parent_local_name: parent || null,
      });
      setLabel("");
      setDefinition("");
      setParent("");
      setLocal("");
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
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
      setError(e instanceof ApiError ? e.detail : String(e));
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
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    }
  }

  return (
    <main className="page layout">
      <div className="stack">
        <section className="panel stack">
          <h2>对象</h2>
          {error ? <p className="error">{error}</p> : null}
          <ul>
            {objects.map((o) => (
              <li key={o.iri}>
                <button type="button" onClick={() => setSelectedIri(o.iri)}>
                  {o.label}
                </button>
              </li>
            ))}
          </ul>
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
            <button type="submit">新建对象</button>
          </form>
        </section>

        {selected ? (
          <section className="panel stack">
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
              <button type="submit">保存对象</button>
              <button type="button" onClick={() => void onDeleteObject()}>
                删除对象
              </button>
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
                    <td>{a.label}{a.owner_iri !== selectedIri ? "（自父对象）" : ""}</td>
                    <td>{a.definition}</td>
                    <td>
                      {a.owner_iri === selectedIri ? (
                      <button
                        type="button"
                        onClick={async () => {
                          try {
                            await api.deleteAttribute(localName(a.iri));
                            await refresh();
                          } catch (e) {
                            setError(e instanceof ApiError ? e.detail : String(e));
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
          </section>
        ) : null}

        <section className="panel stack">
          <h2>关系</h2>
          <table>
            <thead>
              <tr>
                <th>名称</th>
                <th>起点</th>
                <th>终点</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {relations.map((r) => (
                <tr key={r.iri}>
                  <td>{r.label}</td>
                  <td>{objects.find((o) => o.iri === r.source_iri)?.label ?? r.source_iri}</td>
                  <td>{objects.find((o) => o.iri === r.target_iri)?.label ?? r.target_iri}</td>
                  <td>
                    <button
                      type="button"
                      onClick={async () => {
                        try {
                          await api.deleteRelation(localName(r.iri));
                          await refresh();
                        } catch (e) {
                          setError(e instanceof ApiError ? e.detail : String(e));
                        }
                      }}
                    >
                      删除
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
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
            <button type="submit">新建关系</button>
          </form>
        </section>
      </div>

      <section className="panel">
        <TypeNetwork
          nodes={network.nodes}
          edges={network.edges}
          onSelect={(kind, iri) => {
            if (kind === "node") setSelectedIri(iri);
          }}
        />
      </section>
    </main>
  );
}
