import { useEffect, useRef, useState } from "react";
import { circular } from "graphology-layout";
import forceAtlas2 from "graphology-layout-forceatlas2";
import Sigma from "sigma";
import { EdgeArrowProgram } from "sigma/rendering";
import {
  buildNetworkGraph,
  type NetworkEdge,
  type NetworkNode,
} from "./buildNetworkGraph";

export type { NetworkEdge, NetworkNode };
export type NetworkSelect = (kind: "node" | "edge", iri: string) => void;

const NODE_COLOR = "#155eef";
const EDGE_COLOR = "#84adff";
const LABEL_COLOR = "#101828";

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
  const hostRef = useRef<HTMLDivElement>(null);
  const sigmaRef = useRef<Sigma | null>(null);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const [layoutBusy, setLayoutBusy] = useState(false);

  useEffect(() => {
    const el = hostRef.current;
    if (!el || nodes.length === 0) {
      sigmaRef.current?.kill();
      sigmaRef.current = null;
      return;
    }

    const g = buildNetworkGraph(nodes, edges);
    g.forEachNode((id) => {
      g.mergeNodeAttributes(id, {
        size: 8,
        color: NODE_COLOR,
      });
    });
    g.forEachEdge((id) => {
      g.mergeEdgeAttributes(id, {
        size: 1.5,
        color: EDGE_COLOR,
        type: "arrow",
      });
    });

    setLayoutBusy(true);
    if (g.order > 0) {
      circular.assign(g, { scale: 120 });
      forceAtlas2.assign(g, {
        iterations: 80,
        settings: {
          ...forceAtlas2.inferSettings(g),
          gravity: 0.35,
          scalingRatio: 22,
          outboundAttractionDistribution: true,
        },
      });
    }
    setLayoutBusy(false);

    sigmaRef.current?.kill();
    const sigma = new Sigma(g, el, {
      allowInvalidContainer: true,
      renderEdgeLabels: true,
      defaultEdgeType: "arrow",
      edgeProgramClasses: { arrow: EdgeArrowProgram },
      labelColor: { color: LABEL_COLOR },
      labelSize: 13,
      labelFont: '"Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif',
      labelRenderedSizeThreshold: 4,
    });

    let dragged: string | null = null;
    sigma.on("downNode", ({ node }) => {
      dragged = node;
      if (!sigma.getCustomBBox()) sigma.setCustomBBox(sigma.getBBox());
    });
    sigma.getMouseCaptor().on("mousemovebody", (e) => {
      if (!dragged) return;
      const pos = sigma.viewportToGraph(e);
      g.setNodeAttribute(dragged, "x", pos.x);
      g.setNodeAttribute(dragged, "y", pos.y);
      e.preventSigmaDefault();
      sigma.refresh();
    });
    const endDrag = () => {
      dragged = null;
      sigma.setCustomBBox(null);
    };
    sigma.getMouseCaptor().on("mouseup", endDrag);
    sigma.getMouseCaptor().on("mouseleave", endDrag);

    sigma.on("clickNode", ({ node }) => onSelectRef.current("node", node));
    sigma.on("clickEdge", ({ edge }) => onSelectRef.current("edge", edge));

    sigmaRef.current = sigma;
    return () => {
      sigma.kill();
      if (sigmaRef.current === sigma) sigmaRef.current = null;
    };
  }, [nodes, edges]);

  if (nodes.length === 0) {
    return (
      <p className="muted" style={{ padding: "2rem", color: "var(--text)" }}>
        {emptyText}
      </p>
    );
  }

  return (
    <div className="network-shell">
      <div ref={hostRef} className="network-canvas" />
      {layoutBusy ? <div className="network-layout-hint">布局中…</div> : null}
      <div className="network-tools">
        <button
          type="button"
          className="btn-secondary"
          title="放大"
          onClick={() =>
            sigmaRef.current?.getCamera().animatedZoom({ duration: 220 })
          }
        >
          +
        </button>
        <button
          type="button"
          className="btn-secondary"
          title="缩小"
          onClick={() =>
            sigmaRef.current?.getCamera().animatedUnzoom({ duration: 220 })
          }
        >
          −
        </button>
        <button
          type="button"
          className="btn-secondary"
          title="复位"
          onClick={() =>
            sigmaRef.current?.getCamera().animatedReset({ duration: 300 })
          }
        >
          ⌂
        </button>
      </div>
    </div>
  );
}
