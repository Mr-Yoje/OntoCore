const LABELS: Record<string, string> = {
  queued: "待启动",
  extracting: "抽取中",
  merging: "合并中",
  aligning: "判重中",
  reviewable: "待审阅",
  reviewable_partial: "待审阅",
  failed: "失败",
  types_accepted_graph_pending: "待投影",
  // legacy
  running: "抽取中",
  completed: "待审阅",
  partial: "待审阅",
};

export const RUNNING = new Set(["extracting", "merging", "aligning", "running"]);
export const STARTABLE = new Set([
  "queued",
  "failed",
  "reviewable",
  "reviewable_partial",
  "completed",
  "partial",
  "types_accepted_graph_pending",
]);
export const REVIEWABLE = new Set(["reviewable", "reviewable_partial", "completed", "partial"]);
export const EDITABLE = new Set(["queued"]);

export function jobStatusLabel(status: string): string {
  return LABELS[status] ?? status;
}
