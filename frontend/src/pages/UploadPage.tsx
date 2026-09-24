import { FormEvent, ReactNode, SelectHTMLAttributes, useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type Job, type ProviderDraft } from "../api";
import { ClipText } from "../clipText";
import { EDITABLE, jobStatusLabel, REVIEWABLE, RUNNING, STARTABLE } from "../jobStatus";
import { reportError, useTip } from "../tips";

type OntoObject = {
  iri: string;
  label: string;
  parent_iri: string | null;
};

type OntoRelation = {
  iri: string;
  label: string;
};

const POLL_MS = 1500;

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

function progressText(job: Job): string {
  const done = job.progress_done ?? 0;
  const total = job.progress_total ?? 0;
  if (total <= 0) {
    if (job.status === "queued") return "—";
    if (RUNNING.has(job.status)) return "准备中";
    return "—";
  }
  return `${Math.floor((done / total) * 100)}%`;
}

function formatCreatedAt(value?: string): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("zh-CN", { hour12: false });
}

function shortIri(iri: string): string {
  const hash = iri.lastIndexOf("#");
  if (hash >= 0 && hash < iri.length - 1) return iri.slice(hash + 1);
  const slash = iri.lastIndexOf("/");
  if (slash >= 0 && slash < iri.length - 1) return iri.slice(slash + 1);
  return iri;
}

function guideText(iris: string[] | undefined, labels: Map<string, string>): string {
  if (!iris?.length) return "无";
  return iris.map((iri) => labels.get(iri) ?? shortIri(iri)).join("、");
}

function providerLabel(providers: ProviderDraft[], id: string): string {
  if (!id) return "";
  return providers.find((p) => p.id === id)?.label ?? id;
}

function EllipsisSelect({
  display,
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & { display: string; children: ReactNode }) {
  return (
    <span className="select-ellipsis" data-display={display} title={display}>
      <select {...props} title={display}>
        {children}
      </select>
    </span>
  );
}

export function UploadPage() {
  const navigate = useNavigate();
  const showTip = useTip();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [createOpen, setCreateOpen] = useState(false);
  const [detailJob, setDetailJob] = useState<Job | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [providers, setProviders] = useState<ProviderDraft[]>([]);
  const [providerId, setProviderId] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [model, setModel] = useState("");
  const [embedProviderId, setEmbedProviderId] = useState("");
  const [embedModels, setEmbedModels] = useState<string[]>([]);
  const [embedModel, setEmbedModel] = useState("");
  const [thinking, setThinking] = useState(false);
  const [loadingModels, setLoadingModels] = useState(false);
  const [loadingEmbedModels, setLoadingEmbedModels] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [startingId, setStartingId] = useState<string | null>(null);
  const [pollIds, setPollIds] = useState<string[]>([]);
  const [guideOpen, setGuideOpen] = useState(false);
  const [guideSearch, setGuideSearch] = useState("");
  const [objects, setObjects] = useState<OntoObject[]>([]);
  const [relations, setRelations] = useState<OntoRelation[]>([]);
  const [guide_object_iris, setGuideObjectIris] = useState<string[]>([]);
  const [guideRelationIris, setGuideRelationIris] = useState<string[]>([]);
  const [draftObjects, setDraftObjects] = useState<string[]>([]);
  const [draftRelations, setDraftRelations] = useState<string[]>([]);
  const [labelByIri, setLabelByIri] = useState<Map<string, string>>(() => new Map());
  const [guideTarget, setGuideTarget] = useState<"create" | "edit">("create");
  const [savingEdit, setSavingEdit] = useState(false);
  const [editFile, setEditFile] = useState<File | null>(null);
  const [editProviderId, setEditProviderId] = useState("");
  const [editModels, setEditModels] = useState<string[]>([]);
  const [editModel, setEditModel] = useState("");
  const [editEmbedProviderId, setEditEmbedProviderId] = useState("");
  const [editEmbedModels, setEditEmbedModels] = useState<string[]>([]);
  const [editEmbedModel, setEditEmbedModel] = useState("");
  const [editThinking, setEditThinking] = useState(false);
  const [loadingEditModels, setLoadingEditModels] = useState(false);
  const [loadingEditEmbedModels, setLoadingEditEmbedModels] = useState(false);
  const [editGuideObjects, setEditGuideObjects] = useState<string[]>([]);
  const [editGuideRelations, setEditGuideRelations] = useState<string[]>([]);

  const refreshJobs = useCallback(async () => {
    try {
      const rows = await api.listJobs();
      setJobs(rows);
      setDetailJob((current) => {
        if (!current) return null;
        return rows.find((j) => j.id === current.id) ?? current;
      });
    } catch (e) {
      reportError(showTip, e);
    }
  }, [showTip]);

  useEffect(() => {
    void refreshJobs();
  }, [refreshJobs]);

  useEffect(() => {
    if (!detailJob) return;
    let cancelled = false;
    void Promise.all([
      api.listObjects() as Promise<OntoObject[]>,
      api.listRelations() as Promise<OntoRelation[]>,
    ])
      .then(([objs, rels]) => {
        if (cancelled) return;
        const next = new Map<string, string>();
        for (const o of objs) next.set(o.iri, o.label);
        for (const r of rels) next.set(r.iri, r.label);
        setLabelByIri(next);
      })
      .catch((e) => reportError(showTip, e));
    return () => {
      cancelled = true;
    };
  }, [detailJob?.id, showTip]);

  useEffect(() => {
    if (!detailJob || !EDITABLE.has(detailJob.status)) return;
    setEditFile(null);
    setEditProviderId(detailJob.provider_id ?? "");
    setEditModel(detailJob.model ?? "");
    setEditThinking(Boolean(detailJob.thinking));
    setEditEmbedProviderId(detailJob.embed_provider_id ?? "");
    setEditEmbedModel(detailJob.embed_model ?? "");
    setEditGuideObjects(detailJob.guide_object_iris ?? []);
    setEditGuideRelations(detailJob.guide_relation_iris ?? []);
  }, [detailJob?.id, detailJob?.status]);

  useEffect(() => {
    if (!editProviderId || !detailJob || !EDITABLE.has(detailJob.status)) {
      setEditModels([]);
      return;
    }
    setLoadingEditModels(true);
    void api
      .listSettingsModels({ provider_id: editProviderId })
      .then((result) => {
        setEditModels(result.models);
        setEditModel((current) => (result.models.includes(current) ? current : result.models[0] ?? ""));
      })
      .catch((e) => {
        setEditModels([]);
        reportError(showTip, e);
      })
      .finally(() => setLoadingEditModels(false));
  }, [editProviderId, detailJob?.id, detailJob?.status, showTip]);

  useEffect(() => {
    if (!editEmbedProviderId || !detailJob || !EDITABLE.has(detailJob.status)) {
      setEditEmbedModels([]);
      return;
    }
    setLoadingEditEmbedModels(true);
    void api
      .listSettingsModels({ provider_id: editEmbedProviderId })
      .then((result) => {
        setEditEmbedModels(result.models);
        setEditEmbedModel((current) =>
          result.models.includes(current) ? current : result.models[0] ?? "",
        );
      })
      .catch((e) => {
        setEditEmbedModels([]);
        reportError(showTip, e);
      })
      .finally(() => setLoadingEditEmbedModels(false));
  }, [editEmbedProviderId, detailJob?.id, detailJob?.status, showTip]);

  useEffect(() => {
    const activePoll = pollIds.filter((id) => {
      const job = jobs.find((j) => j.id === id);
      return job != null && (job.status === "queued" || RUNNING.has(job.status));
    });
    if (activePoll.length !== pollIds.length) {
      setPollIds(activePoll);
    }
    const needPoll =
      jobs.some((j) => RUNNING.has(j.status)) ||
      activePoll.length > 0 ||
      (detailJob != null && RUNNING.has(detailJob.status));
    if (!needPoll) return;
    const timer = window.setInterval(() => {
      void refreshJobs();
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [jobs, detailJob, pollIds, refreshJobs]);

  useEffect(() => {
    void api
      .getSettings()
      .then((s) => {
        const rows = ((s as { providers?: ProviderDraft[] }).providers ?? []).filter((p) => p.id);
        setProviders(rows);
        if (rows[0]?.id) {
          setProviderId(rows[0].id);
          setEmbedProviderId(rows[0].id);
        }
      })
      .catch((e) => reportError(showTip, e));
  }, [showTip]);

  useEffect(() => {
    if (!providerId) {
      setModels([]);
      setModel("");
      return;
    }
    setLoadingModels(true);
    void api
      .listSettingsModels({ provider_id: providerId })
      .then((result) => {
        setModels(result.models);
        setModel((current) => (result.models.includes(current) ? current : result.models[0] ?? ""));
      })
      .catch((e) => {
        setModels([]);
        setModel("");
        reportError(showTip, e);
      })
      .finally(() => setLoadingModels(false));
  }, [providerId, showTip]);

  useEffect(() => {
    if (!embedProviderId) {
      setEmbedModels([]);
      setEmbedModel("");
      return;
    }
    setLoadingEmbedModels(true);
    void api
      .listSettingsModels({ provider_id: embedProviderId })
      .then((result) => {
        setEmbedModels(result.models);
        setEmbedModel((current) => (result.models.includes(current) ? current : result.models[0] ?? ""));
      })
      .catch((e) => {
        setEmbedModels([]);
        setEmbedModel("");
        reportError(showTip, e);
      })
      .finally(() => setLoadingEmbedModels(false));
  }, [embedProviderId, showTip]);

  const selectedGuideCount = guide_object_iris.length + guideRelationIris.length;
  const editGuideCount = editGuideObjects.length + editGuideRelations.length;
  const q = guideSearch.trim().toLowerCase();
  const shownObjects = objectRows(objects).filter((row) => !q || row.label.toLowerCase().includes(q));
  const shownRelations = relations.filter((row) => !q || row.label.toLowerCase().includes(q));

  async function openGuides(target: "create" | "edit" = "create") {
    try {
      const [objs, rels] = await Promise.all([
        api.listObjects() as Promise<OntoObject[]>,
        api.listRelations() as Promise<OntoRelation[]>,
      ]);
      setObjects(objs);
      setRelations(rels);
      setGuideTarget(target);
      if (target === "edit") {
        setDraftObjects(editGuideObjects);
        setDraftRelations(editGuideRelations);
      } else {
        setDraftObjects(guide_object_iris);
        setDraftRelations(guideRelationIris);
      }
      setGuideSearch("");
      setGuideOpen(true);
    } catch (e) {
      reportError(showTip, e);
    }
  }

  function openCreate() {
    setFile(null);
    setThinking(false);
    setCreateOpen(true);
  }

  async function onSubmit(ev: FormEvent) {
    ev.preventDefault();
    if (!file || submitting) return;
    setSubmitting(true);
    try {
      const created = await api.createJob(file, {
        provider_id: providerId,
        model,
        thinking,
        embed_provider_id: embedProviderId,
        embed_model: embedModel,
        guide_object_iris,
        guide_relation_iris: guideRelationIris,
      });
      showTip("ok", "作业已保存");
      setCreateOpen(false);
      setFile(null);
      await refreshJobs();
      setDetailJob(created);
    } catch (e) {
      reportError(showTip, e);
    } finally {
      setSubmitting(false);
    }
  }

  async function onSaveEdit(ev: FormEvent) {
    ev.preventDefault();
    if (!detailJob || !EDITABLE.has(detailJob.status) || savingEdit) return;
    setSavingEdit(true);
    try {
      const updated = await api.updateJob(detailJob.id, {
        file: editFile,
        provider_id: editProviderId,
        model: editModel,
        thinking: editThinking,
        embed_provider_id: editEmbedProviderId,
        embed_model: editEmbedModel,
        guide_object_iris: editGuideObjects,
        guide_relation_iris: editGuideRelations,
      });
      showTip("ok", "作业已更新");
      setEditFile(null);
      setDetailJob(updated);
      await refreshJobs();
    } catch (e) {
      reportError(showTip, e);
    } finally {
      setSavingEdit(false);
    }
  }

  async function onStart(jobId: string) {
    if (startingId) return;
    setStartingId(jobId);
    const wasReviewable = REVIEWABLE.has(
      (detailJob?.id === jobId ? detailJob : jobs.find((j) => j.id === jobId))?.status ?? "",
    );
    try {
      const updated = await api.startJob(jobId);
      if (updated.error) {
        showTip(updated.error_kind === "system" ? "system" : "business", updated.error);
      } else {
        showTip("ok", wasReviewable ? "已重新抽取" : "已启动抽取");
        setPollIds((ids) => (ids.includes(jobId) ? ids : [...ids, jobId]));
      }
      await refreshJobs();
      setDetailJob((current) => (current?.id === jobId ? updated : current));
    } catch (e) {
      reportError(showTip, e);
    } finally {
      setStartingId(null);
    }
  }

  return (
    <main className="page">
      <header className="page-head">
        <div>
          <h1>数据源</h1>
          <p className="kicker">上传文档，抽取对象、属性和关系</p>
        </div>
        <button type="button" className="btn-primary" onClick={openCreate}>
          新建抽取
        </button>
      </header>

      <section className="panel stack">
        {jobs.length === 0 ? (
          <div className="empty-state stack">
            <p className="muted">还没有作业</p>
            <div className="actions">
              <button type="button" className="btn-primary" onClick={openCreate}>
                新建抽取
              </button>
            </div>
          </div>
        ) : (
          <div className="job-list">
            <table>
              <thead>
                <tr>
                  <th>作业编号</th>
                  <th>文件</th>
                  <th>状态</th>
                  <th>进度</th>
                  <th>创建时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr
                    key={job.id}
                    className="job-row"
                    onClick={() => setDetailJob(job)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setDetailJob(job);
                      }
                    }}
                    tabIndex={0}
                    role="button"
                  >
                    <td>
                      <ClipText text={job.id} className="job-id" />
                    </td>
                    <td>
                      <ClipText text={job.filename} />
                    </td>
                    <td>
                      <ClipText text={jobStatusLabel(job.status)} />
                    </td>
                    <td>
                      <ClipText text={progressText(job)} />
                    </td>
                    <td>
                      <ClipText text={formatCreatedAt(job.created_at)} />
                    </td>
                    <td className="cell-actions">
                      {REVIEWABLE.has(job.status) ? (
                        <span
                          className="job-action-link"
                          role="button"
                          tabIndex={0}
                          title="审阅"
                          onClick={(e) => {
                            e.stopPropagation();
                            navigate(`/review?job=${encodeURIComponent(job.id)}`);
                          }}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              e.stopPropagation();
                              navigate(`/review?job=${encodeURIComponent(job.id)}`);
                            }
                          }}
                        >
                          审阅
                        </span>
                      ) : STARTABLE.has(job.status) ? (
                        <span
                          className="job-action-link"
                          role="button"
                          tabIndex={0}
                          aria-disabled={startingId === job.id}
                          title={startingId === job.id ? "启动中…" : "启动抽取"}
                          onClick={(e) => {
                            e.stopPropagation();
                            if (startingId === job.id) return;
                            void onStart(job.id);
                          }}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              e.stopPropagation();
                              if (startingId === job.id) return;
                              void onStart(job.id);
                            }
                          }}
                        >
                          {startingId === job.id ? "启动中…" : "启动抽取"}
                        </span>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <Dialog open={createOpen} title="新建抽取" onClose={() => setCreateOpen(false)}>
        <form className="stack" onSubmit={onSubmit}>
          <label className="file-field">
            文件
            <input
              type="file"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              required
            />
          </label>
          <div className="field-row">
            <label>
              供应商
              <EllipsisSelect
                value={providerId}
                onChange={(e) => setProviderId(e.target.value)}
                required
                display={providerLabel(providers, providerId) || "选择供应商"}
              >
                <option value="">选择供应商</option>
                {providers.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </EllipsisSelect>
            </label>
            <label>
              抽取模型
              <EllipsisSelect
                value={model}
                onChange={(e) => setModel(e.target.value)}
                required
                disabled={loadingModels || models.length === 0}
                display={
                  model ||
                  (loadingModels ? "正在拉取模型…" : "暂无模型，请先到设置里测试供应商")
                }
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
              </EllipsisSelect>
            </label>
          </div>
          <label className="inline">
            <input
              type="checkbox"
              checked={thinking}
              onChange={(e) => setThinking(e.target.checked)}
            />
            开启 thinking
          </label>
          <div className="field-row">
            <label>
              嵌入供应商
              <EllipsisSelect
                value={embedProviderId}
                onChange={(e) => setEmbedProviderId(e.target.value)}
                required
                display={providerLabel(providers, embedProviderId) || "选择供应商"}
              >
                <option value="">选择供应商</option>
                {providers.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </EllipsisSelect>
            </label>
            <label>
              嵌入模型
              <EllipsisSelect
                value={embedModel}
                onChange={(e) => setEmbedModel(e.target.value)}
                required
                disabled={loadingEmbedModels || embedModels.length === 0}
                display={
                  embedModel || (loadingEmbedModels ? "正在拉取模型…" : "请选择嵌入模型")
                }
              >
                {embedModels.length === 0 ? (
                  <option value="">
                    {loadingEmbedModels ? "正在拉取模型…" : "请选择嵌入模型"}
                  </option>
                ) : (
                  embedModels.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))
                )}
              </EllipsisSelect>
            </label>
          </div>
          <div className="actions">
            <button type="button" className="btn-ghost" onClick={() => void openGuides("create")}>
              选择引导
            </button>
            <span className="muted">已选 {selectedGuideCount}</span>
          </div>
          {providers.length === 0 ? (
            <p className="muted">还没有供应商，请先到设置里添加。</p>
          ) : null}
          <button type="submit" disabled={submitting}>
            {submitting ? "保存中…" : "保存作业"}
          </button>
        </form>
      </Dialog>

      <Dialog
        open={detailJob !== null}
        title="作业详情"
        onClose={() => setDetailJob(null)}
      >
        {detailJob ? (
          EDITABLE.has(detailJob.status) ? (
            <form className="stack" onSubmit={onSaveEdit}>
              <p>
                <strong>作业编号</strong> <ClipText text={detailJob.id} className="job-id" />
              </p>
              <p>
                <strong>状态</strong> {jobStatusLabel(detailJob.status)}
              </p>
              <label className="file-field">
                文件（可选，不选则保留「{detailJob.filename}」）
                <input
                  type="file"
                  onChange={(e) => setEditFile(e.target.files?.[0] ?? null)}
                />
              </label>
              <div className="field-row">
                <label>
                  供应商
                  <EllipsisSelect
                    value={editProviderId}
                    onChange={(e) => setEditProviderId(e.target.value)}
                    required
                    display={providerLabel(providers, editProviderId) || "选择供应商"}
                  >
                    <option value="">选择供应商</option>
                    {providers.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.label}
                      </option>
                    ))}
                  </EllipsisSelect>
                </label>
                <label>
                  抽取模型
                  <EllipsisSelect
                    value={editModel}
                    onChange={(e) => setEditModel(e.target.value)}
                    required
                    disabled={loadingEditModels || editModels.length === 0}
                    display={editModel || (loadingEditModels ? "正在拉取模型…" : "暂无模型")}
                  >
                    {editModels.length === 0 ? (
                      <option value="">
                        {loadingEditModels ? "正在拉取模型…" : "暂无模型"}
                      </option>
                    ) : (
                      editModels.map((name) => (
                        <option key={name} value={name}>
                          {name}
                        </option>
                      ))
                    )}
                  </EllipsisSelect>
                </label>
              </div>
              <label className="inline">
                <input
                  type="checkbox"
                  checked={editThinking}
                  onChange={(e) => setEditThinking(e.target.checked)}
                />
                开启 thinking
              </label>
              <div className="field-row">
                <label>
                  嵌入供应商
                  <EllipsisSelect
                    value={editEmbedProviderId}
                    onChange={(e) => setEditEmbedProviderId(e.target.value)}
                    required
                    display={providerLabel(providers, editEmbedProviderId) || "选择供应商"}
                  >
                    <option value="">选择供应商</option>
                    {providers.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.label}
                      </option>
                    ))}
                  </EllipsisSelect>
                </label>
                <label>
                  嵌入模型
                  <EllipsisSelect
                    value={editEmbedModel}
                    onChange={(e) => setEditEmbedModel(e.target.value)}
                    required
                    disabled={loadingEditEmbedModels || editEmbedModels.length === 0}
                    display={
                      editEmbedModel ||
                      (loadingEditEmbedModels ? "正在拉取模型…" : "请选择嵌入模型")
                    }
                  >
                    {editEmbedModels.length === 0 ? (
                      <option value="">
                        {loadingEditEmbedModels ? "正在拉取模型…" : "请选择嵌入模型"}
                      </option>
                    ) : (
                      editEmbedModels.map((name) => (
                        <option key={name} value={name}>
                          {name}
                        </option>
                      ))
                    )}
                  </EllipsisSelect>
                </label>
              </div>
              <div className="actions">
                <button type="button" className="btn-ghost" onClick={() => void openGuides("edit")}>
                  选择引导
                </button>
                <span className="muted">已选 {editGuideCount}</span>
              </div>
              <div className="actions">
                <button type="submit" disabled={savingEdit}>
                  {savingEdit ? "保存中…" : "保存修改"}
                </button>
                <button
                  type="button"
                  className="btn-primary"
                  disabled={startingId === detailJob.id || savingEdit}
                  onClick={() => void onStart(detailJob.id)}
                >
                  {startingId === detailJob.id ? "启动中…" : "启动抽取"}
                </button>
              </div>
            </form>
          ) : (
            <>
              <p>
                <strong>作业编号</strong> <ClipText text={detailJob.id} className="job-id" />
              </p>
              <p>
                <strong>文件</strong> {detailJob.filename}
              </p>
              <p>
                <strong>状态</strong> {jobStatusLabel(detailJob.status)}
              </p>
              <p>
                <strong>进度</strong> {progressText(detailJob)}
              </p>
              <p>
                <strong>抽取模型</strong> {detailJob.model || "—"}
              </p>
              <p>
                <strong>嵌入模型</strong> {detailJob.embed_model || "—"}
              </p>
              <p>
                <strong>引导对象</strong> {guideText(detailJob.guide_object_iris, labelByIri)}
              </p>
              <p>
                <strong>引导关系</strong> {guideText(detailJob.guide_relation_iris, labelByIri)}
              </p>
              {detailJob.error ? (
                <p className="muted">{detailJob.error}</p>
              ) : null}
              <div className="actions">
                {STARTABLE.has(detailJob.status) ? (
                  <button
                    type="button"
                    className="btn-primary"
                    disabled={startingId === detailJob.id}
                    onClick={() => void onStart(detailJob.id)}
                  >
                    {startingId === detailJob.id ? "启动中…" : "启动抽取"}
                  </button>
                ) : null}
                {REVIEWABLE.has(detailJob.status) ? (
                  <>
                    <button
                      type="button"
                      onClick={() => navigate(`/review?job=${encodeURIComponent(detailJob.id)}`)}
                    >
                      审阅
                    </button>
                    <button
                      type="button"
                      className="btn-ghost"
                      disabled={startingId === detailJob.id}
                      onClick={() => void onStart(detailJob.id)}
                    >
                      {startingId === detailJob.id ? "启动中…" : "重新抽取"}
                    </button>
                  </>
                ) : null}
              </div>
            </>
          )
        ) : null}
      </Dialog>

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
        <div className="actions">
          <button
            type="button"
            className="btn-ghost"
            onClick={() => {
              setDraftObjects([]);
              setDraftRelations([]);
            }}
          >
            清空
          </button>
          <button
            type="button"
            onClick={() => {
              if (guideTarget === "edit") {
                setEditGuideObjects(draftObjects);
                setEditGuideRelations(draftRelations);
              } else {
                setGuideObjectIris(draftObjects);
                setGuideRelationIris(draftRelations);
              }
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
