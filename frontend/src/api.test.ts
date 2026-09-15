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
    expect(t.includes("createAttribute")).toBe(true);
    expect(t.includes("属性（可选）")).toBe(true);
  });

  it("graph page can delete instance edges", () => {
    const t = readFileSync("src/pages/GraphPage.tsx", "utf8");
    expect(t.includes("deleteGraphRel")).toBe(true);
  });

  it("settings page can test model connectivity", () => {
    const t = readFileSync("src/pages/SettingsPage.tsx", "utf8") + readFileSync("src/api.ts", "utf8");
    expect(t.includes("testSettings")).toBe(true);
    expect(t.includes("listSettingsModels")).toBe(true);
    expect(t.includes("测试联通")).toBe(true);
    expect(t.includes("拉取模型")).toBe(true);
    expect(t.includes("供应商")).toBe(true);
    expect(t.includes("settings-stack")).toBe(true);
    expect(t.includes("vendor-card")).toBe(true);
    expect(t.includes("model:")).toBe(true);
  });

  it("upload page picks vendor and model", () => {
    const t = readFileSync("src/pages/UploadPage.tsx", "utf8");
    expect(t.includes("provider_id")).toBe(true);
    expect(t.includes("具体模型")).toBe(true);
    expect(t.includes("供应商")).toBe(true);
    expect(t.includes("listSettingsModels")).toBe(true);
  });

  it("shows flash messages as popup tips", () => {
    const app = readFileSync("src/App.tsx", "utf8");
    const tips = readFileSync("src/tips.tsx", "utf8");
    expect(app.includes("TipHost")).toBe(true);
    expect(tips.includes("tip-stack")).toBe(true);
    expect(tips.includes("showTip")).toBe(true);
    const pages = [
      "src/pages/OntologyPage.tsx",
      "src/pages/SettingsPage.tsx",
      "src/pages/UploadPage.tsx",
      "src/pages/ReviewPage.tsx",
      "src/pages/GraphPage.tsx",
    ];
    for (const f of pages) {
      const t = readFileSync(f, "utf8");
      expect(t.includes("useTip"), f).toBe(true);
      expect(t.includes('className="error"'), f).toBe(false);
      expect(t.includes('className="ok"'), f).toBe(false);
    }
  });
});
