import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api";
import { tipText, useTip } from "../tips";

type SimilarRef = { iri: string; label: string };

type TypeCandidate = {
  id: string;
  kind: string;
  job_id: string;
  status: string;
  payload: {
    label?: string;
    definition?: string;
    evidence?: string;
    similar_to?: SimilarRef[];
  };
};

type ImportDialog = {
  candidate: TypeCandidate;
  mode: "create" | "overwrite" | "merge";
  target_iri: string;
};

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

function similarOf(candidate: TypeCandidate): SimilarRef[] {
  return candidate.payload.similar_to ?? [];
}

function similarHint(candidate: TypeCandidate): string | null {
  if (candidate.kind === "attribute") return null;
  const similar_to = similarOf(candidate);
  if (!similar_to.length) return null;
  return `与${similar_to.map((item) => item.label).join("、")}相似`;
}

export function ReviewPage() {
  const showTip = useTip();
  const [params, setParams] = useSearchParams();
  const jobFromQuery = params.get("job") ?? "";
  const [jobId, setJobId] = useState(jobFromQuery);
  const [candidates, setCandidates] = useState<TypeCandidate[]>([]);
  const [projectResult, setProjectResult] = useState<unknown>(null);
  const [importDlg, setImportDlg] = useState<ImportDialog | null>(null);

  const proposed = useMemo(
    () => candidates.filter((c) => c.status === "proposed"),
    [candidates],
  );

  async function reload() {
    const rows = (await api.typeCandidates(jobId)) as TypeCandidate[];
    setCandidates(rows);
  }

  async function load(ev?: FormEvent) {
    ev?.preventDefault();
    setParams({ job: jobId });
    try {
      await reload();
    } catch (e) {
      showTip("error", tipText(e));
    }
  }

  async function act(id: string, accept: boolean) {
    const row = candidates.find((c) => c.id === id);
    try {
      if (!accept) {
        await api.rejectType(id);
        await reload();
        return;
      }
      const similar_to = row && row.kind !== "attribute" ? similarOf(row) : [];
      if (!row || row.kind === "attribute" || similar_to.length === 0) {
        await api.acceptType(id);
        await reload();
        return;
      }
      setImportDlg({
        candidate: row,
        mode: "create",
        target_iri: similar_to[0]?.iri ?? "",
      });
    } catch (e) {
      showTip("error", tipText(e));
    }
  }

  async function confirmImport() {
    if (!importDlg) return;
    try {
      await api.acceptType(importDlg.candidate.id, {
        mode: importDlg.mode,
        target_iri: importDlg.mode === "create" ? null : importDlg.target_iri,
      });
      setImportDlg(null);
      await reload();
    } catch (e) {
      showTip("error", tipText(e));
    }
  }

  async function project() {
    try {
      const result = await api.projectJob(jobId);
      setProjectResult(result);
      showTip("ok", "已投影到图");
    } catch (e) {
      showTip("error", tipText(e));
    }
  }

  const similarChoices = importDlg ? similarOf(importDlg.candidate) : [];

  return (
    <main className="page">
      <header className="page-head">
        <div>
          <h1>审阅</h1>
          <p className="kicker">确认抽取结果后再写入</p>
        </div>
        {proposed.length ? <p className="muted">未处理 {proposed.length}</p> : null}
      </header>
      <section className="panel stack">
        <form className="stack" onSubmit={load} style={{ maxWidth: 420 }}>
          <label>
            作业编号
            <input value={jobId} onChange={(e) => setJobId(e.target.value)} required />
          </label>
          <button type="submit">加载候选</button>
        </form>
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
            {candidates.map((c) => {
              const hint = similarHint(c);
              return (
                <tr key={c.id}>
                  <td>{c.kind === "object" ? "对象" : c.kind === "attribute" ? "属性" : "关系"}</td>
                  <td>
                    <div>{c.payload.label}</div>
                    {hint ? <div className="muted">{hint}</div> : null}
                  </td>
                  <td>{c.payload.definition}</td>
                  <td>{c.payload.evidence}</td>
                  <td>{c.status}</td>
                  <td>
                    {c.status === "proposed" ? (
                      <div className="actions">
                        <button type="button" onClick={() => act(c.id, true)}>
                          接受
                        </button>
                        <button type="button" className="btn-ghost" onClick={() => act(c.id, false)}>
                          拒绝
                        </button>
                      </div>
                    ) : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <div className="actions">
          <button type="button" onClick={project} disabled={!jobId}>
            投影到图
          </button>
        </div>
        {proposed.length ? <p className="muted">仍有未处理候选 {proposed.length} 条</p> : null}
        {projectResult ? <pre className="muted">{JSON.stringify(projectResult, null, 2)}</pre> : null}
      </section>
      <Dialog open={Boolean(importDlg)} title="选择导入方式" onClose={() => setImportDlg(null)}>
        {importDlg ? (
          <>
            <p className="muted">
              {similarHint(importDlg.candidate)}
            </p>
            <label>
              对齐到
              <select
                value={importDlg.target_iri}
                onChange={(e) => setImportDlg({ ...importDlg, target_iri: e.target.value })}
              >
                {similarChoices.map((item) => (
                  <option key={item.iri} value={item.iri}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <fieldset className="stack">
              <legend>导入方式</legend>
              <label className="inline">
                <input
                  type="radio"
                  name="import-mode"
                  checked={importDlg.mode === "overwrite"}
                  onChange={() => setImportDlg({ ...importDlg, mode: "overwrite" })}
                />
                覆盖
              </label>
              <label className="inline">
                <input
                  type="radio"
                  name="import-mode"
                  checked={importDlg.mode === "create"}
                  onChange={() => setImportDlg({ ...importDlg, mode: "create" })}
                />
                新增
              </label>
              <label className="inline">
                <input
                  type="radio"
                  name="import-mode"
                  checked={importDlg.mode === "merge"}
                  onChange={() => setImportDlg({ ...importDlg, mode: "merge" })}
                />
                融合
              </label>
            </fieldset>
            <div className="actions">
              <button type="button" className="btn-ghost" onClick={() => setImportDlg(null)}>
                取消
              </button>
              <button type="button" onClick={() => void confirmImport()}>
                确认
              </button>
            </div>
          </>
        ) : null}
      </Dialog>
    </main>
  );
}
