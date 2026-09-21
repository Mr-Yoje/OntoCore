import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type ProviderDraft } from "../api";
import { tipText, useTip } from "../tips";

type Job = {
  id: string;
  filename: string;
  model: string;
  status: string;
  error: string | null;
};

type OntoObject = {
  iri: string;
  label: string;
  parent_iri: string | null;
};

type OntoRelation = {
  iri: string;
  label: string;
};

type GraphNode = {
  onto_iri: string;
  type_iri: string;
  onto_label: string;
};

function Dialog({
  open,
  title,
  onClose,
  wide,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  wide?: boolean;
  children: ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    function onKey(ev: KeyboardEvent) {
      if (ev.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className={wide ? "modal modal-wide" : "modal"}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="modal-head">
          <h2>{title}</h2>
          <button type="button" className="btn-ghost" onClick={onClose} aria-label="关闭">
            ×
          </button>
        </header>
        <div className="modal-body stack">{children}</div>
      </div>
    </div>
  );
}

function toggle(list: string[], value: string): string[] {
  return list.includes(value) ? list.filter((item) => item !== value) : [...list, value];
}

function objectRows(objects: OntoObject[]): { iri: string; label: string; depth: number }[] {
  const byIri = new Map(objects.map((o) => [o.iri, o]));
  const children = new Map<string | null, OntoObject[]>();
  for (const o of objects) {
    const parent = o.parent_iri && byIri.has(o.parent_iri) ? o.parent_iri : null;
    const list = children.get(parent) ?? [];
    list.push(o);
    children.set(parent, list);
  }
  for (const list of children.values()) {
    list.sort((a, b) => a.label.localeCompare(b.label, "zh"));
  }
  const rows: { iri: string; label: string; depth: number }[] = [];
  function walk(parent: string | null, depth: number) {
    for (const o of children.get(parent) ?? []) {
      rows.push({ iri: o.iri, label: o.label, depth });
      walk(o.iri, depth + 1);
    }
  }
  walk(null, 0);
  return rows;
}

export function UploadPage() {
  const navigate = useNavigate();
  const showTip = useTip();
  const [file, setFile] = useState<File | null>(null);
  const [providers, setProviders] = useState<ProviderDraft[]>([]);
  const [providerId, setProviderId] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [model, setModel] = useState("");
  const [embedModel, setEmbedModel] = useState("");
  const [thinking, setThinking] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [loadingModels, setLoadingModels] = useState(false);
  const [guideOpen, setGuideOpen] = useState(false);
  const [guideSearch, setGuideSearch] = useState("");
  const [objects, setObjects] = useState<OntoObject[]>([]);
  const [relations, setRelations] = useState<OntoRelation[]>([]);
  const [instances, setInstances] = useState<GraphNode[]>([]);
  const [guide_object_iris, setGuideObjectIris] = useState<string[]>([]);
  const [guideRelationIris, setGuideRelationIris] = useState<string[]>([]);
  const [guideInstanceIris, setGuideInstanceIris] = useState<string[]>([]);
  const [draftObjects, setDraftObjects] = useState<string[]>([]);
  const [draftRelations, setDraftRelations] = useState<string[]>([]);
  const [draftInstances, setDraftInstances] = useState<string[]>([]);

  useEffect(() => {
    void api
      .getSettings()
      .then((s) => {
        const rows = ((s as { providers?: ProviderDraft[] }).providers ?? []).filter((p) => p.id);
        setProviders(rows);
        if (rows[0]?.id) setProviderId(rows[0].id);
      })
      .catch((e) => showTip("error", tipText(e)));
  }, [showTip]);

  useEffect(() => {
    if (!providerId) {
      setModels([]);
      setModel("");
      setEmbedModel("");
      return;
    }
    setLoadingModels(true);
    void api
      .listSettingsModels({ provider_id: providerId })
      .then((result) => {
        setModels(result.models);
        setModel((current) => (result.models.includes(current) ? current : result.models[0] ?? ""));
        setEmbedModel((current) => (current && result.models.includes(current) ? current : ""));
      })
      .catch((e) => {
        setModels([]);
        setModel("");
        setEmbedModel("");
        showTip("error", tipText(e));
      })
      .finally(() => setLoadingModels(false));
  }, [providerId, showTip]);

  const selectedGuideCount = guide_object_iris.length + guideRelationIris.length + guideInstanceIris.length;
  const objectLabel = useMemo(() => new Map(objects.map((o) => [o.iri, o.label])), [objects]);
  const q = guideSearch.trim().toLowerCase();
  const shownObjects = objectRows(objects).filter((row) => !q || row.label.toLowerCase().includes(q));
  const shownRelations = relations.filter((row) => !q || row.label.toLowerCase().includes(q));
  const shownInstances = instances.filter((row) => {
    if (!q) return true;
    const typeLabel = objectLabel.get(row.type_iri) ?? "";
    return row.onto_label.toLowerCase().includes(q) || typeLabel.toLowerCase().includes(q);
  });

  async function openGuides() {
    try {
      const [objs, rels, net] = await Promise.all([
        api.listObjects() as Promise<OntoObject[]>,
        api.listRelations() as Promise<OntoRelation[]>,
        api.graphNetwork() as Promise<{ nodes?: GraphNode[] }>,
      ]);
      setObjects(objs);
      setRelations(rels);
      setInstances(net.nodes ?? []);
      setDraftObjects(guide_object_iris);
      setDraftRelations(guideRelationIris);
      setDraftInstances(guideInstanceIris);
      setGuideSearch("");
      setGuideOpen(true);
    } catch (e) {
      showTip("error", tipText(e));
    }
  }

  async function onSubmit(ev: FormEvent) {
    ev.preventDefault();
    if (!file) return;
    try {
      const created = (await api.createJob(file, {
        provider_id: providerId,
        model,
        thinking,
        embed_model: embedModel || undefined,
        guide_object_iris,
        guide_relation_iris: guideRelationIris,
        guide_instance_iris: guideInstanceIris,
      })) as Job;
      setJob(created);
      if (created.error) showTip("error", created.error);
      else showTip("ok", `作业已创建：${created.status}`);
    } catch (e) {
      showTip("error", tipText(e));
    }
  }

  return (
    <main className="page">
      <header className="page-head">
        <div>
          <h1>上传</h1>
          <p className="kicker">上传文档，抽取对象、属性和关系</p>
        </div>
      </header>
      <section className="panel stack measure">
        <h2>文档抽取</h2>
        <form className="stack" onSubmit={onSubmit}>
          <label className="file-field">
            文件
            <input
              type="file"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              required
            />
          </label>
          <label>
            供应商
            <select value={providerId} onChange={(e) => setProviderId(e.target.value)} required>
              <option value="">选择供应商</option>
              {providers.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            具体模型
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              required
              disabled={loadingModels || models.length === 0}
            >
              {models.length === 0 ? (
                <option value="">{loadingModels ? "正在拉取模型…" : "暂无模型，请先到设置里测试供应商"}</option>
              ) : (
                models.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))
              )}
            </select>
          </label>
          <label className="inline">
            <input
              type="checkbox"
              checked={thinking}
              onChange={(e) => setThinking(e.target.checked)}
            />
            开启 thinking
          </label>
          <label>
            嵌入模型
            <select value={embedModel} onChange={(e) => setEmbedModel(e.target.value)}>
              <option value="">不使用嵌入</option>
              {models.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <div className="actions">
            <button type="button" className="btn-ghost" onClick={() => void openGuides()}>
              选择引导
            </button>
            <span className="muted">已选 {selectedGuideCount}</span>
          </div>
          {providers.length === 0 ? (
            <p className="muted">还没有供应商，请先到设置里添加。</p>
          ) : null}
          <button type="submit">开始抽取</button>
        </form>
        {job ? (
          <div className="inspector stack">
            <h2>作业 {job.id}</h2>
            <p>状态：{job.status}</p>
            <button type="button" onClick={() => navigate(`/review?job=${encodeURIComponent(job.id)}`)}>
              去审阅
            </button>
          </div>
        ) : null}
      </section>
      <Dialog open={guideOpen} title="选择引导" wide onClose={() => setGuideOpen(false)}>
        <label>
          搜索
          <input
            value={guideSearch}
            onChange={(e) => setGuideSearch(e.target.value)}
            placeholder="按显示名筛选"
          />
        </label>
        <p className="guide-section-title">对象</p>
        <div className="guide-pick">
          {shownObjects.map((row) => (
            <label key={row.iri} className="guide-option" style={{ paddingLeft: row.depth * 16 }}>
              <input
                type="checkbox"
                checked={draftObjects.includes(row.iri)}
                onChange={() => setDraftObjects(toggle(draftObjects, row.iri))}
              />
              {row.label}
            </label>
          ))}
          {shownObjects.length === 0 ? <p className="muted">没有可引导的对象</p> : null}
        </div>
        <p className="guide-section-title">关系</p>
        <div className="guide-pick">
          {shownRelations.map((row) => (
            <label key={row.iri} className="guide-option">
              <input
                type="checkbox"
                checked={draftRelations.includes(row.iri)}
                onChange={() => setDraftRelations(toggle(draftRelations, row.iri))}
              />
              {row.label}
            </label>
          ))}
          {shownRelations.length === 0 ? <p className="muted">没有可引导的关系</p> : null}
        </div>
        <p className="guide-section-title">实例</p>
        <div className="guide-pick">
          {shownInstances.map((row) => (
            <label key={row.onto_iri} className="guide-option">
              <input
                type="checkbox"
                checked={draftInstances.includes(row.onto_iri)}
                onChange={() => setDraftInstances(toggle(draftInstances, row.onto_iri))}
              />
              {row.onto_label}
              <span className="muted">{objectLabel.get(row.type_iri) ?? "未指定对象"}</span>
            </label>
          ))}
          {shownInstances.length === 0 ? <p className="muted">没有可引导的实例</p> : null}
        </div>
        <div className="actions">
          <button
            type="button"
            className="btn-ghost"
            onClick={() => {
              setDraftObjects([]);
              setDraftRelations([]);
              setDraftInstances([]);
            }}
          >
            清空
          </button>
          <button
            type="button"
            onClick={() => {
              setGuideObjectIris(draftObjects);
              setGuideRelationIris(draftRelations);
              setGuideInstanceIris(draftInstances);
              setGuideOpen(false);
            }}
          >
            确定
          </button>
        </div>
      </Dialog>
    </main>
  );
}
