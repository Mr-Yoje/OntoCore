export type NetworkNode = {
  iri: string;
  label: string;
};

export type NetworkEdge = {
  iri: string;
  label: string;
  source_iri: string;
  target_iri: string;
};

export type NetworkSelect = (kind: "node" | "edge", iri: string) => void;

function layout(count: number, width: number, height: number) {
  const cx = width / 2;
  const cy = height / 2;
  const radius = Math.min(width, height) * 0.36;
  return Array.from({ length: count }, (_, i) => {
    const angle = (2 * Math.PI * i) / Math.max(count, 1) - Math.PI / 2;
    return { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) };
  });
}

function NetworkSvg({
  nodes,
  edges,
  onSelect,
  emptyText,
}: {
  nodes: NetworkNode[];
  edges: NetworkEdge[];
  onSelect: NetworkSelect;
  emptyText: string;
}) {
  const width = 640;
  const height = 480;
  if (nodes.length === 0) {
    return <p className="muted" style={{ padding: "2rem", color: "var(--text)" }}>{emptyText}</p>;
  }
  const points = layout(nodes.length, width, height);
  const byIri = new Map(nodes.map((n, i) => [n.iri, points[i]!]));
  return (
    <svg className="network" viewBox={`0 0 ${width} ${height}`}>
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="18" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#84adff" />
        </marker>
      </defs>
      {edges.map((e) => {
        const s = byIri.get(e.source_iri);
        const t = byIri.get(e.target_iri);
        if (!s || !t) return null;
        return (
          <g key={e.iri} className="hit" onClick={() => onSelect("edge", e.iri)}>
            <line
              x1={s.x}
              y1={s.y}
              x2={t.x}
              y2={t.y}
              stroke="#84adff"
              strokeWidth={1.5}
              markerEnd="url(#arrow)"
            />
            <text
              x={(s.x + t.x) / 2}
              y={(s.y + t.y) / 2 - 8}
              fontSize={12}
              textAnchor="middle"
              fill="#354052"
              fontFamily="Noto Sans SC, sans-serif"
            >
              {e.label}
            </text>
          </g>
        );
      })}
      {nodes.map((n, i) => {
        const p = points[i]!;
        return (
          <g key={n.iri} className="hit" onClick={() => onSelect("node", n.iri)}>
            <circle cx={p.x} cy={p.y} r={22} fill="rgb(21 94 239 / 0.08)" />
            <circle cx={p.x} cy={p.y} r={11} fill="#155eef" />
            <text
              x={p.x}
              y={p.y + 36}
              fontSize={13}
              fontWeight={600}
              textAnchor="middle"
              fill="#101828"
              fontFamily="Noto Sans SC, sans-serif"
            >
              {n.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export function TypeNetwork({
  nodes,
  edges,
  onSelect,
  emptyText = "还没有对象，请先新建",
}: {
  nodes: NetworkNode[];
  edges: NetworkEdge[];
  onSelect: NetworkSelect;
  emptyText?: string;
}) {
  return <NetworkSvg nodes={nodes} edges={edges} onSelect={onSelect} emptyText={emptyText} />;
}
