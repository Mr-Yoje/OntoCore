import { FormEvent, useEffect, useState } from "react";
import { ApiError, api, exportJsonldHref, exportTurtleHref, type ProviderDraft } from "../api";

type Provider = ProviderDraft & { id: string };

function blankProvider(): ProviderDraft {
  return { label: "", prefix: "openai", api_base: "", api_key: "" };
}

function vendorKey(row: ProviderDraft, index: number) {
  return row.id ?? `new-${index}`;
}

export function SettingsPage() {
  const [providers, setProviders] = useState<ProviderDraft[]>([blankProvider()]);
  const [catalogs, setCatalogs] = useState<Record<string, string[]>>({});
  const [probeModels, setProbeModels] = useState<Record<string, string>>({});
  const [probeThinking, setProbeThinking] = useState(false);
  const [ttl, setTtl] = useState("");
  const [force, setForce] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [testing, setTesting] = useState<number | null>(null);
  const [loadingModels, setLoadingModels] = useState<number | null>(null);

  useEffect(() => {
    void api
      .getSettings()
      .then((s) => {
        const body = s as { providers?: Provider[] };
        if (body.providers && body.providers.length) setProviders(body.providers);
      })
      .catch((e) => setError(e instanceof ApiError ? e.detail : String(e)));
  }, []);

  function updateProvider(index: number, patch: Partial<ProviderDraft>) {
    setProviders((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  async function fetchModels(index: number) {
    const row = providers[index];
    if (!row) return;
    setError("");
    setMessage("");
    setLoadingModels(index);
    try {
      const result = await api.listSettingsModels({
        provider_id: row.id,
        prefix: row.prefix,
        api_base: row.api_base.trim(),
        api_key: row.api_key && row.api_key.trim() !== "" ? row.api_key : null,
      });
      const key = vendorKey(row, index);
      setCatalogs((prev) => ({ ...prev, [key]: result.models }));
      setProbeModels((prev) => ({
        ...prev,
        [key]: result.models.includes(prev[key]) ? prev[key] : result.models[0] ?? "",
      }));
      setMessage(`已拉取 ${result.models.length} 个模型`);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    } finally {
      setLoadingModels(null);
    }
  }

  async function save(ev: FormEvent) {
    ev.preventDefault();
    setError("");
    try {
      const saved = (await api.putSettings({
        providers: providers
          .filter((p) => p.label.trim() || p.api_base.trim() || p.api_key)
          .map((p) => ({
            ...p,
            label: p.label.trim() || "未命名供应商",
            api_key: p.api_key && p.api_key.trim() !== "" ? p.api_key : null,
          })),
      })) as { providers: Provider[] };
      setProviders(saved.providers.length ? saved.providers : [blankProvider()]);
      const next = saved.providers.length ? saved.providers : [blankProvider()];
      setCatalogs((prev) => {
        const mapped: Record<string, string[]> = {};
        next.forEach((row, index) => {
          const old = catalogs[vendorKey(providers[index], index)] ?? prev[vendorKey(row, index)];
          if (old) mapped[vendorKey(row, index)] = old;
        });
        return mapped;
      });
      setProbeModels((prev) => {
        const mapped: Record<string, string> = {};
        next.forEach((row, index) => {
          const old = probeModels[vendorKey(providers[index], index)] ?? prev[vendorKey(row, index)];
          if (old) mapped[vendorKey(row, index)] = old;
        });
        return mapped;
      });
      setMessage("已保存供应商");
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    }
  }

  async function testLink(index: number) {
    const row = providers[index];
    if (!row) return;
    const key = vendorKey(row, index);
    const model = probeModels[key]?.trim() ?? "";
    if (!model) {
      setError("请先拉取模型列表，再选择测试用模型");
      return;
    }
    setError("");
    setMessage("");
    setTesting(index);
    try {
      const result = (await api.testSettings({
        provider_id: row.id,
        prefix: row.prefix,
        api_base: row.api_base.trim(),
        api_key: row.api_key && row.api_key.trim() !== "" ? row.api_key : null,
        model,
        thinking: probeThinking,
      })) as { ok?: boolean; model?: string };
      setMessage(result.ok ? `联通成功：${result.model}` : "联通成功");
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    } finally {
      setTesting(null);
    }
  }

  async function doImport(ev: FormEvent) {
    ev.preventDefault();
    setError("");
    try {
      await api.importOntology(ttl, force);
      setMessage("导入完成");
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    }
  }

  return (
    <main className="page">
      <header className="page-head">
        <div>
          <h1>设置</h1>
          <p className="kicker">配置供应商，导入已有本体</p>
        </div>
      </header>
      <div className="settings-stack">
        <section className="stack">
          <h2>供应商</h2>
          {error ? <p className="error">{error}</p> : null}
          {message ? <p className="ok">{message}</p> : null}
          <p className="muted">
            这里只登记供应商的地址和密钥。抽取器和具体模型在上传页选择。
          </p>
          <form className="stack" onSubmit={save}>
            {providers.map((row, index) => {
              const key = vendorKey(row, index);
              const models = catalogs[key] ?? [];
              const title = row.label.trim() || `供应商 ${index + 1}`;
              return (
                <article key={key} className="vendor-card">
                  <header className="vendor-card-head">
                    <h3>{title}</h3>
                    <span className="muted">{String(index + 1).padStart(2, "0")}</span>
                  </header>
                  <label>
                    供应商名称
                    <input
                      value={row.label}
                      onChange={(e) => updateProvider(index, { label: e.target.value })}
                      placeholder="DeepSeek"
                    />
                  </label>
                  <label>
                    调用前缀
                    <select
                      value={row.prefix}
                      onChange={(e) => updateProvider(index, { prefix: e.target.value })}
                    >
                      <option value="openai">openai（兼容接口）</option>
                      <option value="deepseek">deepseek</option>
                      <option value="anthropic">anthropic</option>
                    </select>
                  </label>
                  <label>
                    Base URL
                    <input
                      value={row.api_base}
                      onChange={(e) => updateProvider(index, { api_base: e.target.value })}
                      placeholder="https://api.deepseek.com"
                      autoComplete="off"
                    />
                  </label>
                  <label>
                    API Key
                    <input
                      type="password"
                      value={row.api_key ?? ""}
                      onChange={(e) => updateProvider(index, { api_key: e.target.value })}
                      placeholder="sk-…"
                      autoComplete="off"
                    />
                  </label>
                  <div className="field-row">
                    <label>
                      测试用模型
                      <select
                        value={probeModels[key] ?? ""}
                        onChange={(e) =>
                          setProbeModels((prev) => ({ ...prev, [key]: e.target.value }))
                        }
                        disabled={models.length === 0}
                      >
                        {models.length === 0 ? (
                          <option value="">请先拉取模型列表</option>
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
                        checked={probeThinking}
                        onChange={(e) => setProbeThinking(e.target.checked)}
                      />
                      测试时开启 thinking
                    </label>
                  </div>
                  <div className="actions">
                    <button
                      type="button"
                      className="btn-ghost"
                      onClick={() => void fetchModels(index)}
                      disabled={loadingModels !== null || testing !== null}
                    >
                      {loadingModels === index ? "拉取中…" : "拉取模型"}
                    </button>
                    <button
                      type="button"
                      className="btn-ghost"
                      onClick={() => void testLink(index)}
                      disabled={testing !== null || loadingModels !== null}
                    >
                      {testing === index ? "测试中…" : "测试联通"}
                    </button>
                    <button
                      type="button"
                      className="btn-danger"
                      onClick={() =>
                        setProviders((rows) =>
                          rows.length === 1 ? [blankProvider()] : rows.filter((_, i) => i !== index),
                        )
                      }
                    >
                      去掉此供应商
                    </button>
                  </div>
                </article>
              );
            })}
            <div className="actions">
              <button
                type="button"
                className="btn-ghost"
                onClick={() => setProviders((rows) => [...rows, blankProvider()])}
              >
                添加供应商
              </button>
              <button type="submit">保存供应商</button>
            </div>
          </form>
          <p className="muted">
            导出：
            {" "}
            <a href={exportTurtleHref}>Turtle</a>
            {" · "}
            <a href={exportJsonldHref}>JSON-LD</a>
          </p>
        </section>
        <section className="panel stack">
          <h2>导入</h2>
          <form className="stack" onSubmit={doImport}>
            <label>
              Turtle
              <textarea rows={10} value={ttl} onChange={(e) => setTtl(e.target.value)} />
            </label>
            <label className="inline">
              <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} />
              force
            </label>
            <button type="submit">导入</button>
          </form>
        </section>
      </div>
    </main>
  );
}
