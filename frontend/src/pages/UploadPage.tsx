import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api } from "../api";

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
  const [model, setModel] = useState("openai/gpt-4o-mini");
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");

  async function onSubmit(ev: FormEvent) {
    ev.preventDefault();
    if (!file) return;
    setError("");
    try {
      const created = (await api.createJob(file, extractor, model)) as Job;
      setJob(created);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    }
  }

  return (
    <main className="page">
      <section className="panel stack">
        <h2>上传</h2>
        <form className="stack" onSubmit={onSubmit}>
          <label>
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
          <label>
            模型
            <input value={model} onChange={(e) => setModel(e.target.value)} />
          </label>
          <button type="submit">开始抽取</button>
        </form>
        {error ? <p className="error">{error}</p> : null}
        {job ? (
          <div>
            <p>作业 {job.id}</p>
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
