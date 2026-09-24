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

  it("settings prefix dropdown uses LiteLLM prefixes from the api", () => {
    const page = readFileSync("src/pages/SettingsPage.tsx", "utf8");
    const api = readFileSync("src/api.ts", "utf8");
    expect(api.includes("/api/settings/prefixes")).toBe(true);
    expect(api.includes("listSettingsPrefixes")).toBe(true);
    expect(page.includes("listSettingsPrefixes")).toBe(true);
    expect(page.includes('value="deepseek"')).toBe(false);
    expect(page.includes('value="anthropic"')).toBe(false);
  });

  it("settings page can test model connectivity", () => {
    const t = readFileSync("src/pages/SettingsPage.tsx", "utf8") + readFileSync("src/api.ts", "utf8");
    expect(t.includes("testSettings")).toBe(true);
    expect(t.includes("listSettingsModels")).toBe(true);
    expect(t.includes("测试联通")).toBe(false);
    expect(t.includes('{testing ? "测试中…" : "测试"}')).toBe(true);
    expect(t.includes('{loadingModels ? "拉取中…" : "拉取模型"}')).toBe(true);
    expect(t.includes("正在拉取模型")).toBe(true);
    expect(t.includes("去掉此模型供应商")).toBe(false);
    expect(t.includes(">删除<")).toBe(true);
    expect(t.includes(">保存模型供应商</button>")).toBe(false);
    expect(t.includes(">保存</button>")).toBe(true);
    expect(t.includes("模型供应商")).toBe(true);
    expect(t.includes("settings-stack")).toBe(true);
    expect(t.includes("vendor-card")).toBe(true);
    expect(t.includes("model:")).toBe(true);
  });

  it("settings fetches vendor models when the dialog opens not on page load", () => {
    const page = readFileSync("src/pages/SettingsPage.tsx", "utf8");
    const settings = page.slice(page.indexOf("export function SettingsPage"));
    const loadStart = settings.indexOf("useEffect");
    const fetchStart = settings.indexOf("useEffect", loadStart + 1);
    const dialogKeyAt = settings.indexOf("function dialogKey");
    expect(settings.slice(loadStart, fetchStart).includes("listSettingsModels")).toBe(false);
    expect(settings.slice(fetchStart, dialogKeyAt).includes("listSettingsModels")).toBe(true);
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
    expect(gridChunk.includes(">删除<")).toBe(false);
    expect(gridChunk.includes(">保存</button>")).toBe(false);
    const dialogChunk = page.slice(dialogAt);
    expect(dialogChunk.includes("测试联通")).toBe(false);
    expect(dialogChunk.includes('{testing ? "测试中…" : "测试"}')).toBe(true);
    expect(dialogChunk.includes('{loadingModels ? "拉取中…" : "拉取模型"}')).toBe(true);
    expect(dialogChunk.includes("正在拉取模型")).toBe(true);
    expect(dialogChunk.includes(">删除<")).toBe(true);
    expect(dialogChunk.includes(">保存</button>")).toBe(true);
  });

  it("settings save uses popup tips for empty required fields", () => {
    const page = readFileSync("src/pages/SettingsPage.tsx", "utf8");
    const saveAt = page.indexOf("async function saveDialog");
    const persistAt = page.indexOf("await persist(next)", saveAt);
    expect(saveAt).toBeGreaterThan(-1);
    expect(persistAt).toBeGreaterThan(saveAt);
    const save = page.slice(saveAt, persistAt);
    expect(save.includes("providerSaveTip")).toBe(true);
    expect(save.includes('showTip("error"')).toBe(true);
    expect(save.includes("field-hint")).toBe(false);
    expect(save.includes("field-error")).toBe(false);
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
    expect(t.includes("抽取模型")).toBe(true);
    expect(t.includes("具体模型")).toBe(false);
    expect(t.includes("供应商")).toBe(true);
    expect(t.includes("listSettingsModels")).toBe(true);
    expect(t.includes("抽取器")).toBe(false);
  });

  it("upload page selects embed vendor independently", () => {
    const page = readFileSync("src/pages/UploadPage.tsx", "utf8");
    const api = readFileSync("src/api.ts", "utf8");
    expect(page.includes("embed_provider_id")).toBe(true);
    expect(page.includes("嵌入供应商")).toBe(true);
    expect(api.includes("embed_provider_id")).toBe(true);
  });

  it("sidebar labels the source page 数据源", () => {
    const app = readFileSync("src/App.tsx", "utf8");
    const page = readFileSync("src/pages/UploadPage.tsx", "utf8");
    expect(app.includes('label: "数据源"')).toBe(true);
    expect(app.includes('to: "/upload"')).toBe(true);
    expect(app.includes('label: "上传"')).toBe(false);
    expect(app.includes("M12 16V5m0 0 4 4M12 5 8 9M5 19h14")).toBe(false);
    expect(app.includes("M7 6h11v13H7V6Zm-2 2v11a2 2 0 0 0 2 2h9M10 10h5M10 13.5h5")).toBe(true);
    expect(page.includes("<h1>数据源</h1>") || page.includes(">数据源</h1>")).toBe(true);
  });

  it("upload page lists jobs with create and detail dialogs", () => {
    const page = readFileSync("src/pages/UploadPage.tsx", "utf8");
    const api = readFileSync("src/api.ts", "utf8");
    const status = readFileSync("src/jobStatus.ts", "utf8");
    expect(api.includes("listJobs")).toBe(true);
    expect(api.includes("/api/jobs")).toBe(true);
    expect(api.includes("startJob")).toBe(true);
    expect(api.includes("/start")).toBe(true);
    expect(api.includes("progress_done")).toBe(true);
    expect(api.includes("progress_total")).toBe(true);
    expect(api.includes("created_at")).toBe(true);
    expect(page.includes("listJobs")).toBe(true);
    expect(page.includes("新建抽取")).toBe(true);
    expect(page.includes("保存作业")).toBe(true);
    expect(page.includes("启动抽取")).toBe(true);
    expect(page.includes("job-action-link")).toBe(true);
    expect(page.includes("ClipText") || page.includes("cell-ellipsis")).toBe(true);
    expect(page.includes("作业已保存")).toBe(true);
    expect(page.includes("开始抽取")).toBe(false);
    expect(page.includes("还没有作业")).toBe(true);
    expect(page.includes("作业编号")).toBe(true);
    expect(page.includes("抽取模型")).toBe(true);
    expect(page.includes("嵌入模型")).toBe(true);
    expect(page.includes("引导对象")).toBe(true);
    expect(page.includes("引导关系")).toBe(true);
    expect(page.includes("保存修改")).toBe(true);
    expect(page.includes("updateJob")).toBe(true);
    expect(api.includes("updateJob")).toBe(true);
    expect(api.includes("method: \"PATCH\"") || api.includes("method: 'PATCH'")).toBe(true);
    expect(api.includes("embed_model")).toBe(true);
    expect(api.includes("guide_object_iris")).toBe(true);
    expect(api.includes("guide_relation_iris")).toBe(true);
    const listSection = page.slice(page.indexOf("<table"), page.indexOf('title="新建抽取"'));
    expect(listSection.includes("<th>模型</th>") || listSection.includes(">模型</th>")).toBe(false);
    expect(page.includes("jobStatusLabel")).toBe(true);
    expect(page.includes("审阅")).toBe(true);
    expect(page.includes("重新抽取")).toBe(true);
    expect(page.includes("去审阅")).toBe(false);
    expect(page.includes("setInterval") || page.includes("1500") || page.includes("1000")).toBe(true);
    expect(page.includes('role="dialog"')).toBe(true);
    expect(status.includes("待启动")).toBe(true);
    expect(status.includes("排队中")).toBe(false);
    expect(status.includes("抽取中")).toBe(true);
    expect(status.includes("待审阅")).toBe(true);
    expect(status.includes("已完成")).toBe(false);
    expect(status.includes("部分完成")).toBe(false);
    expect(status.includes("失败")).toBe(true);
    expect(status.includes("待投影")).toBe(true);
    const main = page.slice(page.indexOf("export function UploadPage"));
    const mainReturn = main.slice(main.indexOf("return ("));
    const listHint = Math.max(
      mainReturn.indexOf("还没有作业"),
      mainReturn.indexOf("job-list"),
      mainReturn.indexOf("<table"),
    );
    const createDialog = mainReturn.indexOf('title="新建抽取"');
    const formAt = mainReturn.indexOf("onSubmit={onSubmit}");
    expect(listHint).toBeGreaterThan(-1);
    expect(createDialog).toBeGreaterThan(-1);
    expect(formAt).toBeGreaterThan(createDialog);
  });

  it("jobStatusLabel maps statuses from the async jobs spec", async () => {
    const { jobStatusLabel } = await import("./jobStatus");
    expect(jobStatusLabel("queued")).toBe("待启动");
    expect(jobStatusLabel("extracting")).toBe("抽取中");
    expect(jobStatusLabel("merging")).toBe("合并中");
    expect(jobStatusLabel("aligning")).toBe("判重中");
    expect(jobStatusLabel("reviewable")).toBe("待审阅");
    expect(jobStatusLabel("reviewable_partial")).toBe("待审阅");
    expect(jobStatusLabel("running")).toBe("抽取中");
    expect(jobStatusLabel("completed")).toBe("待审阅");
    expect(jobStatusLabel("partial")).toBe("待审阅");
    expect(jobStatusLabel("failed")).toBe("失败");
    expect(jobStatusLabel("types_accepted_graph_pending")).toBe("待投影");
  });

  it("jobStatus exports action sets for upload page", async () => {
    const { RUNNING, STARTABLE, REVIEWABLE, EDITABLE } = await import("./jobStatus");
    expect(RUNNING.has("extracting")).toBe(true);
    expect(RUNNING.has("merging")).toBe(true);
    expect(RUNNING.has("aligning")).toBe(true);
    expect(RUNNING.has("running")).toBe(true);
    expect(STARTABLE.has("queued")).toBe(true);
    expect(STARTABLE.has("failed")).toBe(true);
    expect(STARTABLE.has("reviewable")).toBe(true);
    expect(STARTABLE.has("reviewable_partial")).toBe(true);
    expect(STARTABLE.has("completed")).toBe(true);
    expect(STARTABLE.has("partial")).toBe(true);
    expect(STARTABLE.has("types_accepted_graph_pending")).toBe(true);
    expect(REVIEWABLE.has("reviewable")).toBe(true);
    expect(REVIEWABLE.has("reviewable_partial")).toBe(true);
    expect(REVIEWABLE.has("completed")).toBe(true);
    expect(REVIEWABLE.has("partial")).toBe(true);
    expect(EDITABLE.has("queued")).toBe(true);
    expect(EDITABLE.size).toBe(1);
  });

  it("upload page selects guides not extractors", () => {
    const t = readFileSync("src/pages/UploadPage.tsx", "utf8");
    expect(t.includes("hybrid")).toBe(false);
    expect(t.includes("rules_only")).toBe(false);
    expect(t.includes("llm_only")).toBe(false);
    expect(t.includes("选择引导")).toBe(true);
    expect(t.includes("guide_object_iris")).toBe(true);
    expect(t.includes("embed_model")).toBe(true);
    expect(t.includes("请选择嵌入模型")).toBe(true);
    expect(t.includes("不使用嵌入")).toBe(false);
    expect(t.includes("没有可引导的实例")).toBe(false);
    expect(t.includes("guide_instance_iris")).toBe(false);
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

  it("review page loads candidates from job query", () => {
    const t = readFileSync("src/pages/ReviewPage.tsx", "utf8");
    expect(t.includes("api.typeCandidates(jobFromQuery)")).toBe(true);
  });

  it("shows flash messages as popup tips", () => {
    const app = readFileSync("src/App.tsx", "utf8");
    const tips = readFileSync("src/tips.tsx", "utf8");
    const css = readFileSync("src/index.css", "utf8");
    const api = readFileSync("src/api.ts", "utf8");
    expect(app.includes("TipHost")).toBe(true);
    expect(tips.includes("tip-stack")).toBe(true);
    expect(tips.includes("showTip")).toBe(true);
    expect(tips.includes("tip-business")).toBe(true);
    expect(tips.includes("tip-system")).toBe(true);
    expect(css.includes("tip-business")).toBe(true);
    expect(css.includes("tip-system")).toBe(true);
    expect(css.includes("#98a2b3")).toBe(true);
    expect(css.includes("#161b26")).toBe(true);
    expect(api.includes("kind")).toBe(true);
    expect(api.includes("code")).toBe(true);
    expect(tips.includes("reportError")).toBe(true);
    expect(tips.includes("OC-")).toBe(false);
    expect(tips.includes("Traceback")).toBe(false);
    const upload = readFileSync("src/pages/UploadPage.tsx", "utf8");
    expect(upload.includes("reportError")).toBe(true);
    expect(upload.includes("error_kind")).toBe(true);
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

describe("public error copy", () => {
  it("offline and dump fallbacks match fault catalog copy", async () => {
    const { sanitizePublicError } = await import("./api");
    expect(sanitizePublicError("[Errno 11001] getaddrinfo failed")).toBe(
      "无法连接服务，请检查网络",
    );
    expect(sanitizePublicError("litellm.InternalServerError HTML")).toBe("模型调用失败");
    expect(sanitizePublicError("请填写 Base URL")).toBe("请填写 Base URL");
  });

  it("never shows LiteLLM, stacks, or HTML in tips", async () => {
    const { tipText } = await import("./tips");
    const { ApiError } = await import("./api");
    const dump =
      'litellm.InternalServerError: InternalServerError: OpenAIEx rel="icon" href="data:image/svg+xml;base64,PHN2ZyB4bWxucz0ia';
    const text = tipText(new ApiError(400, dump, "business", "OC-5001"));
    expect(text).toBe("模型调用失败");
    expect(text.includes("litellm")).toBe(false);
    expect(text.includes("rel=")).toBe(false);
    expect(text.includes("data:image")).toBe(false);
    expect(text.includes("OC-")).toBe(false);
    expect(tipText(new ApiError(400, "请填写 Base URL"))).toBe("请填写 Base URL");
  });

  it("maps offline DNS errors instead of generic model failure", async () => {
    const { tipText, appendTip } = await import("./tips");
    const { ApiError, sanitizePublicError } = await import("./api");
    const dns = "[Errno 11001] getaddrinfo failed";
    expect(sanitizePublicError(dns)).toBe("无法连接服务，请检查网络");
    expect(tipText(new ApiError(400, dns))).toBe("无法连接服务，请检查网络");
    expect(tipText(new TypeError("Failed to fetch"))).toBe("无法连接服务，请检查网络");
    const first = { id: 1, kind: "business" as const, text: "无法连接服务，请检查网络" };
    expect(appendTip([first], { id: 2, kind: "business", text: first.text })).toEqual([first]);
  });
});
