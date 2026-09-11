import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { ApiError } from "./api";

export type TipKind = "ok" | "error";

type Tip = { id: number; kind: TipKind; text: string };

type ShowTip = (kind: TipKind, text: string) => void;

const TipContext = createContext<ShowTip>(() => {});

export function tipText(error: unknown): string {
  return error instanceof ApiError ? error.detail : String(error);
}

export function useTip(): ShowTip {
  return useContext(TipContext);
}

export function TipHost({ children }: { children: ReactNode }) {
  const [tips, setTips] = useState<Tip[]>([]);

  const showTip = useCallback<ShowTip>((kind, text) => {
    const message = text.trim();
    if (!message) return;
    const id = Date.now() + Math.random();
    setTips((rows) => [...rows, { id, kind, text: message }]);
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
          <div key={row.id} className={`tip tip-${row.kind}`} role="status">
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
