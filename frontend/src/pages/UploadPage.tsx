import { FormEvent, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api, type ProviderDraft } from "../api";

type Job = {
  id: string;
  filename: string;
  extractor: string;
  model: string;
  status: string;
  error: string | null;
};

export function UploadPage() {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [extractor, setExtractor] = useState("hybrid");
  const [providers, setProviders] = useState<ProviderDraft[]>([]);
  const [providerId, setProviderId] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [model, setModel] = useState("");
  const [thinking, setThinking] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const [loadingModels, setLoadingModels] = useState(false);

  useEffect(() => {
    void api
      .getSettings()
      .then((s) => {
        const rows = ((s as { providers?: ProviderDraft[] }).providers ?? []).filter((p) => p.id);
        setProviders(rows);
        if (rows[0]?.id) setProviderId(rows[0].id);
      })
      .catch((e) => setError(e instanceof ApiError ? e.detail : String(e)));
  }, []);

  useEffect(() => {
    if (!providerId) {
      setModels([]);
      setModel("");
      return;
    }
    setLoadingModels(true);
    setError("");
    void api
      .listSettingsModels({ provider_id: providerId })
      .then((result) => {
        setModels(result.models);
        setModel((current) => (result.models.includes(current) ? current : result.models[0] ?? ""));
      })
      .catch((e) => {
        setModels([]);
        setModel("");
        setError(e instanceof ApiError ? e.detail : String(e));
      })
      .finally(() => setLoadingModels(false));
  }, [providerId]);

  const needsModel = extractor !== "rules_only";

  async function onSubmit(ev: FormEvent) {
    ev.preventDefault();
    if (!file) return;
    setError("");
    try {
      const created = (await api.createJob(file, {
        extractor,
        provider_id: needsModel ? providerId : undefined,
        model: needsModel ? model : undefined,
        thinking: needsModel ? thinking : false,
      })) as Job;
      setJob(created);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
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
            抽取器
            <select value={extractor} onChange={(e) => setExtractor(e.target.value)}>
              <option value="hybrid">hybrid</option>
              <option value="llm_only">llm_only</option>
              <option value="rules_only">rules_only</option>
            </select>
          </label>
          {needsModel ? (
            <>
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
              {providers.length === 0 ? (
                <p className="muted">还没有供应商，请先到设置里添加。</p>
              ) : null}
            </>
          ) : (
            <p className="muted">规则抽取不调用模型。</p>
          )}
          <button type="submit">开始抽取</button>
        </form>
        {error ? <p className="error">{error}</p> : null}
        {job ? (
          <div className="inspector stack">
            <h2>作业 {job.id}</h2>
            <p>状态：{job.status}</p>
            {job.error ? <p className="error">{job.error}</p> : null}
            <button type="button" onClick={() => navigate(`/review?job=${encodeURIComponent(job.id)}`)}>
              去审阅
            </button>
          </div>
        ) : null}
      </section>
    </main>
  );
}
