import { FormEvent, ReactNode, useEffect, useState } from "react";
import { api, exportJsonldHref, exportTurtleHref, type ProviderDraft } from "../api";
import { tipText, useTip } from "../tips";

type Provider = ProviderDraft & { id: string };

type VendorDialog =
  | { mode: "create"; draft: ProviderDraft }
  | { mode: "edit"; index: number; draft: ProviderDraft };

function blankProvider(): ProviderDraft {
  return { label: "", prefix: "openai", api_base: "", api_key: "" };
}

function vendorKey(row: ProviderDraft, index: number) {
  return row.id ?? `new-${index}`;
}

function Dialog({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
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
        className="modal"
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

export function SettingsPage() {
  const showTip = useTip();
  const [providers, setProviders] = useState<ProviderDraft[]>([]);
  const [catalogs, setCatalogs] = useState<Record<string, string[]>>({});
  const [probeModels, setProbeModels] = useState<Record<string, string>>({});
  const [probeThinking, setProbeThinking] = useState(false);
  const [ttl, setTtl] = useState("");
  const [force, setForce] = useState(false);
  const [testing, setTesting] = useState(false);
  const [loadingModels, setLoadingModels] = useState(false);
  const [dialog, setDialog] = useState<VendorDialog | null>(null);

  useEffect(() => {
    void api
      .getSettings()
      .then((s) => {
        const body = s as { providers?: Provider[] };
        const rows = body.providers ?? [];
        setProviders(rows);
        const selected: Record<string, string> = {};
        rows.forEach((row, index) => {
          if (row.model) selected[vendorKey(row, index)] = row.model;
        });
        setProbeModels(selected);
        rows.forEach((row, index) => {
          if (!row.id && !row.api_base.trim()) return;
          void api
            .listSettingsModels({
              provider_id: row.id,
              prefix: row.prefix,
              api_base: row.api_base.trim(),
            })
            .then((result) => {
              const key = vendorKey(row, index);
              setCatalogs((prev) => ({ ...prev, [key]: result.models }));
              setProbeModels((prev) => ({
                ...prev,
                [key]: result.models.includes(prev[key]) ? prev[key] : result.models[0] ?? "",
              }));
            })
            .catch((e) => showTip("error", tipText(e)));
        });
      })
      .catch((e) => showTip("error", tipText(e)));
  }, [showTip]);

  function dialogKey() {
    if (!dialog) return "draft";
    if (dialog.mode === "create") return "new-create";
    return vendorKey(dialog.draft, dialog.index);
  }

  function patchDraft(patch: Partial<ProviderDraft>) {
    setDialog((cur) => (cur ? { ...cur, draft: { ...cur.draft, ...patch } } : cur));
  }

  async function persist(next: ProviderDraft[]) {
    const saved = (await api.putSettings({
      providers: next
        .filter((p) => p.label.trim() || p.api_base.trim() || p.has_api_key || (p.api_key && p.api_key.trim()))
        .map((p, index) => ({
          id: p.id,
          label: p.label.trim() || "未命名模型供应商",
          prefix: p.prefix,
          api_base: p.api_base,
          api_key: p.api_key && p.api_key.trim() !== "" ? p.api_key : null,
          model: probeModels[vendorKey(p, index)]?.trim() || p.model || "",
        })),
    })) as { providers: Provider[] };
    const rows = saved.providers;
    setProviders(rows);
    setCatalogs((prev) => {
      const mapped: Record<string, string[]> = {};
      rows.forEach((row, index) => {
        const old = prev[vendorKey(row, index)] ?? catalogs[vendorKey(providers[index], index)];
        if (old) mapped[vendorKey(row, index)] = old;
      });
      return mapped;
    });
    setProbeModels((prev) => {
      const mapped: Record<string, string> = {};
      rows.forEach((row, index) => {
        const old = prev[vendorKey(row, index)] ?? probeModels[vendorKey(providers[index], index)];
        if (old) mapped[vendorKey(row, index)] = old;
      });
      return mapped;
    });
    showTip("ok", "已保存模型供应商");
    return rows;
  }

  async function fetchModels() {
    if (!dialog) return;
    const row = dialog.draft;
    setLoadingModels(true);
    try {
      const result = await api.listSettingsModels({
        provider_id: row.id,
        prefix: row.prefix,
        api_base: row.api_base.trim(),
        api_key: row.api_key && row.api_key.trim() !== "" ? row.api_key : null,
      });
      const key = dialogKey();
      setCatalogs((prev) => ({ ...prev, [key]: result.models }));
      setProbeModels((prev) => ({
        ...prev,
        [key]: result.models.includes(prev[key]) ? prev[key] : result.models[0] ?? "",
      }));
      showTip("ok", `已拉取 ${result.models.length} 个模型`);
    } catch (e) {
      showTip("error", tipText(e));
    } finally {
      setLoadingModels(false);
    }
  }

  async function saveDialog(ev: FormEvent) {
    ev.preventDefault();
    if (!dialog) return;
    try {
      const draft = {
        ...dialog.draft,
        model: probeModels[dialogKey()]?.trim() || dialog.draft.model || "",
      };
      const next =
        dialog.mode === "create"
          ? [...providers, draft]
          : providers.map((row, i) => (i === dialog.index ? draft : row));
      const rows = await persist(next);
      setDialog(null);
      if (rows.length) {
        const idx = dialog.mode === "create" ? rows.length - 1 : dialog.index;
        const saved = rows[idx];
        if (saved) {
          const savedKey = vendorKey(saved, idx);
          setProbeModels((prev) => ({
            ...prev,
            [savedKey]: draft.model || prev[savedKey] || "",
          }));
          setCatalogs((prev) => {
            const list = prev[dialogKey()];
            return list ? { ...prev, [savedKey]: list } : prev;
          });
        }
      }
    } catch (e) {
      showTip("error", tipText(e));
    }
  }

  async function testLink() {
    if (!dialog) return;
    const row = dialog.draft;
    const model = probeModels[dialogKey()]?.trim() ?? "";
    if (!model) {
      showTip("error", "请先拉取模型列表，再选择测试用模型");
      return;
    }
    setTesting(true);
    try {
      const result = (await api.testSettings({
        provider_id: row.id,
        prefix: row.prefix,
        api_base: row.api_base.trim(),
        api_key: row.api_key && row.api_key.trim() !== "" ? row.api_key : null,
        model,
        thinking: probeThinking,
      })) as { ok?: boolean; model?: string };
      showTip("ok", result.ok ? `联通成功：${result.model}` : "联通成功");
    } catch (e) {
      showTip("error", tipText(e));
    } finally {
      setTesting(false);
    }
  }

  async function removeVendor() {
    if (!dialog || dialog.mode !== "edit") return;
    try {
      await persist(providers.filter((_, i) => i !== dialog.index));
      setDialog(null);
    } catch (e) {
      showTip("error", tipText(e));
    }
  }

  async function doImport(ev: FormEvent) {
    ev.preventDefault();
    try {
      await api.importOntology(ttl, force);
      showTip("ok", "导入完成");
    } catch (e) {
      showTip("error", tipText(e));
    }
  }

  const key = dialog ? dialogKey() : "";
  const models = dialog ? (catalogs[key] ?? []) : [];
  const dialogTitle =
    dialog?.mode === "create"
      ? "新增模型供应商"
      : dialog?.draft.label.trim() || "编辑模型供应商";

  return (
    <main className="page">
      <header className="page-head">
        <div>
          <h1>设置</h1>
          <p className="kicker">配置模型供应商，导入已有本体</p>
        </div>
      </header>
      <div className="settings-stack">
        <section className="stack">
          <h2>模型供应商</h2>
          <p className="muted">
            这里只登记模型供应商的地址和密钥。上传时再选具体模型。
          </p>
          <div className="vendor-panel">
            <div className="vendor-grid">
              {providers.map((row, index) => {
                const tileKey = vendorKey(row, index);
                const title = row.label.trim() || `模型供应商 ${index + 1}`;
                const model = probeModels[tileKey] || row.model || "未选模型";
                return (
                  <button
                    key={tileKey}
                    type="button"
                    className="vendor-card vendor-tile"
                    onClick={() =>
                      setDialog({ mode: "edit", index, draft: { ...row, api_key: "" } })
                    }
                  >
                    <header className="vendor-card-head">
                      <h3>{title}</h3>
                      <span className="muted">{String(index + 1).padStart(2, "0")}</span>
                    </header>
                    <p className="muted">{row.prefix}</p>
                    <p className="muted vendor-tile-model">{model}</p>
                  </button>
                );
              })}
              <button
                type="button"
                className="vendor-tile vendor-tile-add"
                onClick={() => setDialog({ mode: "create", draft: blankProvider() })}
              >
                新增模型供应商
              </button>
            </div>
          </div>
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

      <Dialog open={dialog !== null} title={dialogTitle} onClose={() => setDialog(null)}>
        {dialog ? (
          <form className="stack" onSubmit={(e) => void saveDialog(e)} autoComplete="off">
            <label>
              模型供应商名称
              <input
                value={dialog.draft.label}
                onChange={(e) => patchDraft({ label: e.target.value })}
                placeholder="DeepSeek"
                autoComplete="off"
                name="vendor-label"
              />
            </label>
            <label>
              调用前缀
              <select
                value={dialog.draft.prefix}
                onChange={(e) => patchDraft({ prefix: e.target.value })}
                autoComplete="off"
                name="vendor-prefix"
              >
                <option value="openai">openai（兼容接口）</option>
                <option value="deepseek">deepseek</option>
                <option value="anthropic">anthropic</option>
              </select>
            </label>
            <label>
              Base URL
              <input
                value={dialog.draft.api_base}
                onChange={(e) => patchDraft({ api_base: e.target.value })}
                placeholder="https://api.deepseek.com"
                autoComplete="off"
                name="vendor-api-base"
              />
            </label>
            <label>
              API Key
              <input
                type="password"
                value={dialog.draft.api_key ?? ""}
                onChange={(e) => patchDraft({ api_key: e.target.value })}
                placeholder={dialog.draft.has_api_key ? "已保存密钥" : "sk-…"}
                autoComplete="new-password"
                name="vendor-api-key"
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
                onClick={() => void fetchModels()}
                disabled={loadingModels || testing}
              >
                {loadingModels ? "拉取中…" : "拉取模型"}
              </button>
              <button
                type="button"
                className="btn-ghost"
                onClick={() => void testLink()}
                disabled={testing || loadingModels}
              >
                {testing ? "测试中…" : "测试联通"}
              </button>
              {dialog.mode === "edit" ? (
                <button type="button" className="btn-danger" onClick={() => void removeVendor()}>
                  去掉此模型供应商
                </button>
              ) : null}
              <button type="submit">保存模型供应商</button>
            </div>
          </form>
        ) : null}
      </Dialog>
    </main>
  );
}
