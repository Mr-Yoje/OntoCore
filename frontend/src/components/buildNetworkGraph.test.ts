import { describe, it, expect } from "vitest";
import { buildNetworkGraph } from "./buildNetworkGraph";

describe("buildNetworkGraph", () => {
  it("adds nodes with labels", () => {
    const g = buildNetworkGraph(
      [
        { iri: "n1", label: "设备" },
        { iri: "n2", label: "人员" },
      ],
      [],
    );
    expect(g.order).toBe(2);
    expect(g.getNodeAttribute("n1", "label")).toBe("设备");
    expect(g.getNodeAttribute("n2", "label")).toBe("人员");
  });

  it("adds edges by iri and skips dangling endpoints", () => {
    const g = buildNetworkGraph(
      [
        { iri: "n1", label: "A" },
        { iri: "n2", label: "B" },
      ],
      [
        {
          iri: "e1",
          label: "属于",
          source_iri: "n1",
          target_iri: "n2",
        },
        {
          iri: "e-bad",
          label: "悬空",
          source_iri: "n1",
          target_iri: "missing",
        },
      ],
    );
    expect(g.size).toBe(1);
    expect(g.hasEdge("e1")).toBe(true);
    expect(g.getEdgeAttribute("e1", "label")).toBe("属于");
    expect(g.hasEdge("e-bad")).toBe(false);
  });
});
