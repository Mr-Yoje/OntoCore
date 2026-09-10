import { readFileSync } from "node:fs";
import { describe, it, expect } from "vitest";

describe("copy", () => {
  it("does not mention domain pack or TBox", () => {
    const files = [
      "src/App.tsx",
      "src/pages/OntologyPage.tsx",
      "src/pages/ReviewPage.tsx",
      "src/pages/UploadPage.tsx",
    ];
    for (const f of files) {
      const t = readFileSync(f, "utf8");
      expect(t.includes("领域包"), f).toBe(false);
      expect(t.includes("TBox"), f).toBe(false);
      expect(t.includes("对象属性"), f).toBe(false);
      expect(t.includes("数据属性"), f).toBe(false);
    }
  });

  it("does not mention class as product copy", () => {
    const t = readFileSync("src/App.tsx", "utf8") + readFileSync("src/pages/OntologyPage.tsx", "utf8");
    expect(t.includes("类")).toBe(false);
  });

  it("does not render instance accept", () => {
    const t = readFileSync("src/pages/ReviewPage.tsx", "utf8");
    expect(t.includes("acceptInstance")).toBe(false);
    expect(t.includes("投影到图")).toBe(true);
  });

  it("wires graph rel delete", () => {
    const t = readFileSync("src/api.ts", "utf8");
    expect(t.includes("/api/graph/rels/")).toBe(true);
    expect(t.includes("deleteGraphRel")).toBe(true);
  });

  it("ontology page can patch and delete objects and relations", () => {
    const t = readFileSync("src/pages/OntologyPage.tsx", "utf8");
    expect(t.includes("patchObject")).toBe(true);
    expect(t.includes("deleteObject")).toBe(true);
    expect(t.includes("deleteRelation")).toBe(true);
    expect(t.includes("listObjectAttributes")).toBe(true);
  });

  it("graph page can delete instance edges", () => {
    const t = readFileSync("src/pages/GraphPage.tsx", "utf8");
    expect(t.includes("deleteGraphRel")).toBe(true);
  });
});
