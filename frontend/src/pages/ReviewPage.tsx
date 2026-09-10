import { FormEvent, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ApiError, api } from "../api";

type TypeCandidate = {
  id: string;
  kind: string;
  job_id: string;
  status: string;
  payload: { label?: string; definition?: string; evidence?: string };
};

export function ReviewPage() {
  const [params, setParams] = useSearchParams();
  const jobFromQuery = params.get("job") ?? "";
  const [jobId, setJobId] = useState(jobFromQuery);
  const [candidates, setCandidates] = useState<TypeCandidate[]>([]);
  const [projectResult, setProjectResult] = useState<unknown>(null);
  const [error, setError] = useState("");

  const proposed = useMemo(
    () => candidates.filter((c) => c.status === "proposed"),
    [candidates],
  );

  async function load(ev?: FormEvent) {
    ev?.preventDefault();
    setError("");
    setParams({ job: jobId });
    try {
      const rows = (await api.typeCandidates(jobId)) as TypeCandidate[];
      setCandidates(rows);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    }
  }

  async function act(id: string, accept: boolean) {
    try {
      if (accept) await api.acceptType(id);
      else await api.rejectType(id);
      const rows = (await api.typeCandidates(jobId)) as TypeCandidate[];
      setCandidates(rows);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    }
  }

  async function project() {
    try {
      const result = await api.projectJob(jobId);
      setProjectResult(result);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    }
  }

  return (
    <main className="page">
      <section className="panel stack">
        <h2>审阅</h2>
        <form className="stack" onSubmit={load}>
          <label>
            作业编号
            <input value={jobId} onChange={(e) => setJobId(e.target.value)} required />
          </label>
          <button type="submit">加载候选</button>
        </form>
        {error ? <p className="error">{error}</p> : null}
        <table>
          <thead>
            <tr>
              <th>候选</th>
              <th>显示名</th>
              <th>定义</th>
              <th>证据</th>
              <th>状态</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {candidates.map((c) => (
              <tr key={c.id}>
                <td>{c.kind === "object" ? "对象" : c.kind === "attribute" ? "属性" : "关系"}</td>
                <td>{c.payload.label}</td>
                <td>{c.payload.definition}</td>
                <td>{c.payload.evidence}</td>
                <td>{c.status}</td>
                <td>
                  {c.status === "proposed" ? (
                    <>
                      <button type="button" onClick={() => act(c.id, true)}>
                        接受
                      </button>
                      <button type="button" onClick={() => act(c.id, false)}>
                        拒绝
                      </button>
                    </>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <button type="button" onClick={project} disabled={!jobId}>
          投影到图
        </button>
        {proposed.length ? <p className="muted">仍有未处理候选 {proposed.length} 条</p> : null}
        {projectResult ? <pre className="muted">{JSON.stringify(projectResult, null, 2)}</pre> : null}
      </section>
    </main>
  );
}
