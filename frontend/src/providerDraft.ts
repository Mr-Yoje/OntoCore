import type { ProviderDraft } from "./api";

export function providerSaveTip(
  draft: Pick<ProviderDraft, "label" | "prefix" | "api_base" | "api_key" | "has_api_key">,
  mode: "create" | "edit",
): string | null {
  const missing: string[] = [];
  if (!draft.label.trim()) missing.push("名称");
  if (!draft.prefix.trim()) missing.push("调用前缀");
  if (!draft.api_base.trim()) missing.push("Base URL");
  const needKey = mode === "create" || !draft.has_api_key;
  if (needKey && !(draft.api_key ?? "").trim()) missing.push("API Key");
  if (!missing.length) return null;
  return `请填写${missing.join("、")}`;
}
