import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { InstanceNetwork } from "../components/InstanceNetwork";
import { tipText, useTip } from "../tips";

type GraphNode = {
  onto_iri: string;
  type_iri: string;
  onto_label: string;
  evidence: string;
  data: Record<string, unknown>;
};

type GraphRel = {
  rel_id: string;
  source_iri: string;
  target_iri: string;
  predicate_iri: string;
  onto_label: string;
};

type GraphNet = { nodes: GraphNode[]; edges: GraphRel[] };

export function GraphPage() {
  const showTip = useTip();
  const [typeIri, setTypeIri] = useState("");
  const [network, setNetwork] = useState<GraphNet>({ nodes: [], edges: [] });
  const [objects, setObjects] = useState<{ iri: string; label: string }[]>([]);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [selectedRel, setSelectedRel] = useState<GraphRel | null>(null);

  const load = useCallback(async () => {
    try {
      const [net, objs] = await Promise.all([
        api.graphNetwork(typeIri || undefined) as Promise<GraphNet>,
        api.listObjects() as Promise<{ iri: string; label: string }[]>,
      ]);
      setNetwork(net);
      setObjects(objs);
    } catch (e) {
      showTip("error", tipText(e));
    }
  }, [typeIri, showTip]);

  useEffect(() => {
    void load();
  }, [load]);

  async function removeSelected() {
    if (!selected) return;
    try {
      await api.deleteGraphNode(selected.onto_iri);
      setSelected(null);
      await load();
    } catch (e) {
      showTip("error", tipText(e));
    }
  }

  async function removeSelectedRel() {
    if (!selectedRel) return;
    try {
      await api.deleteGraphRel(selectedRel.rel_id);
      setSelectedRel(null);
      await load();
    } catch (e) {
      showTip("error", tipText(e));
    }
  }

  return (
    <main className="page">
      <header className="page-head">
        <div>
          <h1>图</h1>
          <p className="kicker">查看实例及其关系</p>
        </div>
        <label style={{ minWidth: 220 }}>
          按对象筛选
          <select value={typeIri} onChange={(e) => setTypeIri(e.target.value)}>
            <option value="">全部</option>
            {objects.map((o) => (
              <option key={o.iri} value={o.iri}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      </header>
      <section className="panel panel-canvas">
        <InstanceNetwork
          nodes={network.nodes.map((n) => ({ iri: n.onto_iri, label: n.onto_label }))}
          edges={network.edges.map((e) => ({
            iri: e.rel_id,
            label: e.onto_label,
            source_iri: e.source_iri,
            target_iri: e.target_iri,
          }))}
          onSelect={(kind, iri) => {
            if (kind === "node") {
              setSelectedRel(null);
              setSelected(network.nodes.find((n) => n.onto_iri === iri) ?? null);
            } else {
              setSelected(null);
              setSelectedRel(network.edges.find((e) => e.rel_id === iri) ?? null);
            }
          }}
        />
      </section>
      <section className="panel stack">
        <h2>检视</h2>
        {selected ? (
          <div className="stack">
            <h3>{selected.onto_label}</h3>
            <p className="muted">{selected.evidence}</p>
            <pre className="muted">{JSON.stringify(selected.data, null, 2)}</pre>
            <button type="button" className="btn-danger" onClick={removeSelected}>
              删除节点
            </button>
          </div>
        ) : null}
        {selectedRel ? (
          <div className="stack">
            <h3>{selectedRel.onto_label}</h3>
            <p className="muted">
              {selectedRel.source_iri} → {selectedRel.target_iri}
            </p>
            <button type="button" className="btn-danger" onClick={() => void removeSelectedRel()}>
              删除关系
            </button>
          </div>
        ) : null}
        {!selected && !selectedRel ? <p className="muted">点选节点或边</p> : null}
      </section>
    </main>
  );
}
