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

  it("ontology main page is a graph with dialogs for create and detail", () => {
    const t = readFileSync("src/pages/OntologyPage.tsx", "utf8");
    expect(t.includes("TypeNetwork")).toBe(true);
    expect(t.includes("entity-list")).toBe(false);
    expect(t.includes("object-panel")).toBe(false);
    expect(t.includes('role="dialog"')).toBe(true);
    expect(t.includes("新建对象")).toBe(true);
    expect(t.includes("新建关系")).toBe(true);
    expect(t.includes('kind === "edge"') || t.includes("kind === \"edge\"")).toBe(true);
    const mainReturn = t.slice(t.indexOf("return ("));
    const firstDialog = mainReturn.indexOf('role="dialog"');
    const createForm = mainReturn.indexOf("onCreateObject");
    expect(firstDialog).toBeGreaterThan(-1);
    expect(createForm).toBeGreaterThan(firstDialog);
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
    expect(t.includes("模型供应商")).toBe(true);
    expect(t.includes("settings-stack")).toBe(true);
    expect(t.includes("vendor-card")).toBe(true);
    expect(t.includes("model:")).toBe(true);
  });

  it("settings vendors use a card grid; add and edit open dialogs", () => {
    const t = readFileSync("src/pages/SettingsPage.tsx", "utf8");
    expect(t.includes("vendor-grid")).toBe(true);
    expect(t.includes("新增模型供应商")).toBe(true);
    expect(t.includes("vendor-slot")).toBe(false);
    expect(t.includes('role="dialog"')).toBe(true);
    expect(t.includes("modal-backdrop")).toBe(true);
    expect(t.includes("putSettings")).toBe(true);
    const page = t.slice(t.indexOf("export function SettingsPage"));
    const gridAt = page.indexOf("vendor-grid");
    const dialogAt = page.indexOf("<Dialog");
    expect(gridAt).toBeGreaterThan(-1);
    expect(dialogAt).toBeGreaterThan(-1);
    expect(dialogAt).toBeGreaterThan(gridAt);
    const gridChunk = page.slice(gridAt, dialogAt);
    expect(gridChunk.includes("测试联通")).toBe(false);
    expect(gridChunk.includes("拉取模型")).toBe(false);
    const dialogChunk = page.slice(dialogAt);
    expect(dialogChunk.includes("测试联通")).toBe(true);
    expect(dialogChunk.includes("拉取模型")).toBe(true);
  });

  it("settings page does not keep vendor keys in the client", () => {
    const page = readFileSync("src/pages/SettingsPage.tsx", "utf8");
    const api = readFileSync("src/api.ts", "utf8");
    expect(page.includes("localStorage")).toBe(false);
    expect(page.includes("sessionStorage")).toBe(false);
    expect(page.includes("has_api_key")).toBe(true);
    expect(page.includes("已保存密钥")).toBe(true);
    expect(api.includes("has_api_key")).toBe(true);
  });

  it("upload page picks vendor and model", () => {
    const t = readFileSync("src/pages/UploadPage.tsx", "utf8");
    expect(t.includes("provider_id")).toBe(true);
    expect(t.includes("具体模型")).toBe(true);
    expect(t.includes("供应商")).toBe(true);
    expect(t.includes("listSettingsModels")).toBe(true);
    expect(t.includes("抽取器")).toBe(false);
  });

  it("upload page selects guides not extractors", () => {
    const t = readFileSync("src/pages/UploadPage.tsx", "utf8");
    expect(t.includes("hybrid")).toBe(false);
    expect(t.includes("rules_only")).toBe(false);
    expect(t.includes("llm_only")).toBe(false);
    expect(t.includes("选择引导")).toBe(true);
    expect(t.includes("guide_object_iris")).toBe(true);
    expect(t.includes("embed_model")).toBe(true);
    expect(t.includes("不使用嵌入")).toBe(true);
  });

  it("review page import modes when similar", () => {
    const t = readFileSync("src/pages/ReviewPage.tsx", "utf8");
    expect(t.includes("similar_to")).toBe(true);
    expect(t.includes("覆盖")).toBe(true);
    expect(t.includes("新增")).toBe(true);
    expect(t.includes("融合")).toBe(true);
    expect(t.includes("acceptType")).toBe(true);
    expect(t.includes("target_iri")).toBe(true);
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

  it("TypeNetwork stack uses sigma and graphology", () => {
    const pkg = readFileSync("package.json", "utf8");
    expect(pkg.includes('"sigma"')).toBe(true);
    expect(pkg.includes('"graphology"')).toBe(true);
    expect(pkg.includes("graphology-layout-forceatlas2")).toBe(true);
    const tn = readFileSync("src/components/TypeNetwork.tsx", "utf8");
    expect(tn.includes('from "sigma"') || tn.includes("from 'sigma'")).toBe(true);
    expect(tn.includes("buildNetworkGraph")).toBe(true);
    expect(tn.includes("forceAtlas2")).toBe(true);
    expect(tn.includes("animatedZoom") || tn.includes("ZoomIn") || tn.includes("放大")).toBe(true);
  });
});
