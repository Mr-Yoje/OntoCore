import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { ApiError, sanitizePublicError } from "./api";

export type TipKind = "ok" | "error" | "business" | "system";

type Tip = { id: number; kind: TipKind; text: string };

type ShowTip = (kind: TipKind, text: string) => void;

const TipContext = createContext<ShowTip>(() => {});

export function tipText(error: unknown): string {
  const raw = error instanceof ApiError ? error.detail : String(error);
  return sanitizePublicError(raw);
}

export function reportError(show: ShowTip, error: unknown): void {
  const kind = error instanceof ApiError && error.kind === "system" ? "system" : "business";
  show(kind, tipText(error));
}

export function useTip(): ShowTip {
  return useContext(TipContext);
}

export function TipHost({ children }: { children: ReactNode }) {
  const [tips, setTips] = useState<Tip[]>([]);

  const showTip = useCallback<ShowTip>((kind, text) => {
    const message = sanitizePublicError(text);
    if (!message) return;
    const id = Date.now() + Math.random();
    const visual: TipKind = kind === "error" ? "business" : kind;
    setTips((rows) => [...rows, { id, kind: visual, text: message }]);
    window.setTimeout(() => {
      setTips((rows) => rows.filter((row) => row.id !== id));
    }, 4200);
  }, []);

  function dismiss(id: number) {
    setTips((rows) => rows.filter((row) => row.id !== id));
  }

  return (
    <TipContext.Provider value={showTip}>
      {children}
      <div className="tip-stack" aria-live="polite">
        {tips.map((row) => (
          <div
            key={row.id}
            className={`tip ${row.kind === "ok" ? "tip-ok" : row.kind === "system" ? "tip-system" : "tip-business"}`}
            role="status"
          >
            <p>{row.text}</p>
            <button type="button" className="tip-dismiss" onClick={() => dismiss(row.id)} aria-label="关闭">
              ×
            </button>
          </div>
        ))}
      </div>
    </TipContext.Provider>
  );
}
