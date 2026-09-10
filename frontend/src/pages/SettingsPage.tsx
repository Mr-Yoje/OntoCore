import { FormEvent, useEffect, useState } from "react";
import { ApiError, api, exportJsonldHref, exportTurtleHref } from "../api";

export function SettingsPage() {
  const [extractor, setExtractor] = useState("hybrid");
  const [model, setModel] = useState("");
  const [ttl, setTtl] = useState("");
  const [force, setForce] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    void api
      .getSettings()
      .then((s) => {
        const body = s as { extractor: string; model: string };
        setExtractor(body.extractor);
        setModel(body.model);
      })
      .catch((e) => setError(e instanceof ApiError ? e.detail : String(e)));
  }, []);

  async function save(ev: FormEvent) {
    ev.preventDefault();
    setError("");
    try {
      await api.putSettings(extractor, model);
      setMessage("已保存");
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
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
      <section className="panel stack">
        <h2>设置</h2>
        {error ? <p className="error">{error}</p> : null}
        {message ? <p>{message}</p> : null}
        <form className="stack" onSubmit={save}>
          <label>
            抽取器
            <select value={extractor} onChange={(e) => setExtractor(e.target.value)}>
              <option value="hybrid">hybrid</option>
              <option value="llm_only">llm_only</option>
              <option value="rules_only">rules_only</option>
            </select>
          </label>
          <label>
            模型
            <input value={model} onChange={(e) => setModel(e.target.value)} />
          </label>
          <button type="submit">保存</button>
        </form>
        <p>
          导出：
          <a href={exportTurtleHref}>Turtle</a>
          {" · "}
          <a href={exportJsonldHref}>JSON-LD</a>
        </p>
        <form className="stack" onSubmit={doImport}>
          <label>
            导入
            <textarea rows={8} value={ttl} onChange={(e) => setTtl(e.target.value)} />
          </label>
          <label style={{ flexDirection: "row", alignItems: "center" }}>
            <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} />
            force
          </label>
          <button type="submit">导入</button>
        </form>
      </section>
    </main>
  );
}
