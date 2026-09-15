import Graph from "graphology";

export type NetworkNode = { iri: string; label: string };

export type NetworkEdge = {
  iri: string;
  label: string;
  source_iri: string;
  target_iri: string;
};

export function buildNetworkGraph(
  nodes: NetworkNode[],
  edges: NetworkEdge[],
): Graph {
  const g = new Graph({ multi: true, type: "directed" });
  for (const n of nodes) {
    if (!g.hasNode(n.iri)) {
      g.addNode(n.iri, { label: n.label });
    }
  }
  for (const e of edges) {
    if (!g.hasNode(e.source_iri) || !g.hasNode(e.target_iri)) continue;
    if (g.hasEdge(e.iri)) continue;
    g.addEdgeWithKey(e.iri, e.source_iri, e.target_iri, { label: e.label });
  }
  return g;
}
