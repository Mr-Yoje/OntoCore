import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "../api";
import { InstanceNetwork } from "../components/InstanceNetwork";

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
  const [typeIri, setTypeIri] = useState("");
  const [network, setNetwork] = useState<GraphNet>({ nodes: [], edges: [] });
  const [objects, setObjects] = useState<{ iri: string; label: string }[]>([]);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [selectedRel, setSelectedRel] = useState<GraphRel | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const [net, objs] = await Promise.all([
        api.graphNetwork(typeIri || undefined) as Promise<GraphNet>,
        api.listObjects() as Promise<{ iri: string; label: string }[]>,
      ]);
      setNetwork(net);
      setObjects(objs);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    }
  }, [typeIri]);

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
      setError(e instanceof ApiError ? e.detail : String(e));
    }
  }

  async function removeSelectedRel() {
    if (!selectedRel) return;
    try {
      await api.deleteGraphRel(selectedRel.rel_id);
      setSelectedRel(null);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    }
  }

  return (
    <main className="page stack">
      <section className="panel stack">
        <h2>图</h2>
        {error ? <p className="error">{error}</p> : null}
        <label>
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
        {selected ? (
          <div>
            <p>{selected.onto_label}</p>
            <p className="muted">{selected.evidence}</p>
            <pre className="muted">{JSON.stringify(selected.data, null, 2)}</pre>
            <button type="button" onClick={removeSelected}>
              删除节点
            </button>
          </div>
        ) : null}
        {selectedRel ? (
          <div>
            <p>{selectedRel.onto_label}</p>
            <p className="muted">
              {selectedRel.source_iri} → {selectedRel.target_iri}
            </p>
            <button type="button" onClick={() => void removeSelectedRel()}>
              删除关系
            </button>
          </div>
        ) : null}
      </section>
    </main>
  );
}
