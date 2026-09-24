export class ApiError extends Error {
  status: number;
  detail: string;
  kind: "business" | "system";
  code: string;
  constructor(status: number, detail: string, kind: "business" | "system" = "business", code = "") {
    const safe = sanitizePublicError(detail);
    super(safe);
    this.status = status;
    this.detail = safe;
    this.kind = kind;
    this.code = code;
  }
}

function looksLikeInternalDump(text: string): boolean {
  const low = text.toLowerCase();
  return (
    low.includes("traceback") ||
    text.includes('File "') ||
    low.includes("litellm") ||
    low.includes("exception") ||
    low.includes("internalservererror") ||
    text.includes("rel=") ||
    low.includes("data:image") ||
    low.includes("<!doctype") ||
    low.includes("<html") ||
    text.includes("href=") ||
    /(?:Error|Exception)\b/.test(text)
  );
}

function looksLikeOffline(text: string): boolean {
  const low = text.toLowerCase();
  return (
    low.includes("getaddrinfo") ||
    low.includes("errno 11001") ||
    low.includes("failed to fetch") ||
    low.includes("networkerror") ||
    low.includes("network is unreachable") ||
    low.includes("offline")
  );
}

export function sanitizePublicError(text: string): string {
  const trimmed = text.trim();
  if (!trimmed) return "操作失败";
  if (looksLikeOffline(trimmed)) return "无法连接服务，请检查网络";
  if (looksLikeInternalDump(trimmed) || trimmed.includes("OC-")) {
    return "模型调用失败";
  }
  return trimmed;
}

async function parse(response: Response): Promise<unknown> {
  const text = await response.text();
  let body: unknown = text;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  if (!response.ok) {
    const record = typeof body === "object" && body !== null ? (body as Record<string, unknown>) : null;
    const detail =
      record && "detail" in record ? String(record.detail) : text || response.statusText;
    const kind = record && record.kind === "system" ? "system" : "business";
    const code = record && typeof record.code === "string" ? record.code : "";
    throw new ApiError(response.status, detail, kind, code);
  }
  return body;
}

function jsonHeaders(): HeadersInit {
  return { "Content-Type": "application/json" };
}

export function localName(iri: string): string {
  const hash = iri.split("#").pop() ?? iri;
  return hash.split("/").pop() ?? hash;
}

export type ProviderDraft = {
  id?: string;
  label: string;
  prefix: string;
  api_base: string;
  api_key?: string | null;
  has_api_key?: boolean;
  model?: string;
};

export type Job = {
  id: string;
  filename: string;
  model: string;
  status: string;
  error: string | null;
  error_kind?: string | null;
  created_at?: string;
  progress_done?: number;
  progress_total?: number;
  provider_id?: string | null;
  thinking?: boolean;
  embed_model?: string | null;
  embed_provider_id?: string | null;
  guide_object_iris?: string[];
  guide_relation_iris?: string[];
};

export const api = {
  listObjects: () => fetch("/api/objects").then(parse),
  createObject: (body: {
    local_name: string;
    label: string;
    definition: string;
    parent_local_name?: string | null;
  }) =>
    fetch("/api/objects", {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify(body),
    }).then(parse),
  patchObject: (
    name: string,
    body: { label?: string; definition?: string; parent_local_name?: string | null },
  ) =>
    fetch(`/api/objects/${encodeURIComponent(name)}`, {
      method: "PATCH",
      headers: jsonHeaders(),
      body: JSON.stringify(body),
    }).then(parse),
  deleteObject: (name: string) =>
    fetch(`/api/objects/${encodeURIComponent(name)}`, { method: "DELETE" }).then(parse),
  createAttribute: (
    owner: string,
    body: {
      local_name: string;
      label: string;
      definition: string;
      literal_kind: "text" | "number" | "date";
    },
  ) =>
    fetch(`/api/objects/${encodeURIComponent(owner)}/attributes`, {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify(body),
    }).then(parse),
  deleteAttribute: (name: string) =>
    fetch(`/api/attributes/${encodeURIComponent(name)}`, { method: "DELETE" }).then(parse),
  listRelations: () => fetch("/api/relations").then(parse),
  createRelation: (body: {
    local_name: string;
    label: string;
    definition: string;
    source_local_name: string;
    target_local_name: string;
  }) =>
    fetch("/api/relations", {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify(body),
    }).then(parse),
  deleteRelation: (name: string) =>
    fetch(`/api/relations/${encodeURIComponent(name)}`, { method: "DELETE" }).then(parse),
  ontologyNetwork: () => fetch("/api/ontology/network").then(parse),
  listJobs: () => fetch("/api/jobs").then(parse) as Promise<Job[]>,
  createJob: (
    file: File,
    body: {
      provider_id: string;
      model: string;
      thinking?: boolean;
      embed_provider_id: string;
      embed_model: string;
      guide_object_iris: string[];
      guide_relation_iris: string[];
    },
  ) => {
    const form = new FormData();
    form.append("file", file);
    form.append("provider_id", body.provider_id);
    form.append("model", body.model);
    form.append("thinking", body.thinking ? "true" : "false");
    form.append("embed_provider_id", body.embed_provider_id);
    form.append("embed_model", body.embed_model);
    for (const iri of body.guide_object_iris) form.append("guide_object_iris", iri);
    for (const iri of body.guide_relation_iris) form.append("guide_relation_iris", iri);
    return fetch("/api/jobs", { method: "POST", body: form }).then(parse) as Promise<Job>;
  },
  updateJob: (
    id: string,
    body: {
      file?: File | null;
      provider_id: string;
      model: string;
      thinking?: boolean;
      embed_provider_id: string;
      embed_model: string;
      guide_object_iris: string[];
      guide_relation_iris: string[];
    },
  ) => {
    const form = new FormData();
    if (body.file) form.append("file", body.file);
    form.append("provider_id", body.provider_id);
    form.append("model", body.model);
    form.append("thinking", body.thinking ? "true" : "false");
    form.append("embed_provider_id", body.embed_provider_id);
    form.append("embed_model", body.embed_model);
    for (const iri of body.guide_object_iris) form.append("guide_object_iris", iri);
    for (const iri of body.guide_relation_iris) form.append("guide_relation_iris", iri);
    return fetch(`/api/jobs/${encodeURIComponent(id)}`, { method: "PATCH", body: form }).then(
      parse,
    ) as Promise<Job>;
  },
  startJob: (id: string) =>
    fetch(`/api/jobs/${encodeURIComponent(id)}/start`, { method: "POST" }).then(parse) as Promise<Job>,
  getJob: (id: string) => fetch(`/api/jobs/${encodeURIComponent(id)}`).then(parse) as Promise<Job>,
  typeCandidates: (jobId: string) =>
    fetch(`/api/jobs/${encodeURIComponent(jobId)}/type-candidates`).then(parse),
  acceptType: (id: string, body?: { mode: string; target_iri?: string | null }) =>
    fetch(`/api/type-candidates/${encodeURIComponent(id)}/accept`, {
      method: "POST",
      headers: body ? jsonHeaders() : undefined,
      body: body ? JSON.stringify(body) : undefined,
    }).then(parse),
  rejectType: (id: string) =>
    fetch(`/api/type-candidates/${encodeURIComponent(id)}/reject`, { method: "POST" }).then(parse),
  projectJob: (jobId: string) =>
    fetch(`/api/jobs/${encodeURIComponent(jobId)}/project`, { method: "POST" }).then(parse),
  graphNetwork: (typeIri?: string) => {
    const q = typeIri ? `?type_iri=${encodeURIComponent(typeIri)}` : "";
    return fetch(`/api/graph/network${q}`).then(parse);
  },
  deleteGraphNode: (iri: string) =>
    fetch(`/api/graph/nodes/${encodeURIComponent(iri)}`, { method: "DELETE" }).then(parse),
  deleteGraphRel: (relId: string) =>
    fetch(`/api/graph/rels/${encodeURIComponent(relId)}`, { method: "DELETE" }).then(parse),
  listObjectAttributes: (name: string) =>
    fetch(`/api/objects/${encodeURIComponent(name)}/attributes`).then(parse),
  getSettings: () => fetch("/api/settings").then(parse),
  listSettingsPrefixes: () =>
    fetch("/api/settings/prefixes").then(parse) as Promise<{ prefixes: string[] }>,
  putSettings: (body: { providers: ProviderDraft[] }) =>
    fetch("/api/settings", {
      method: "PUT",
      headers: jsonHeaders(),
      body: JSON.stringify(body),
    }).then(parse),
  listSettingsModels: (body: {
    provider_id?: string | null;
    prefix?: string;
    api_base?: string;
    api_key?: string | null;
  }) =>
    fetch("/api/settings/models", {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify(body),
    }).then(parse) as Promise<{ models: string[] }>,
  testSettings: (body: {
    provider_id?: string | null;
    prefix?: string;
    api_base?: string;
    api_key?: string | null;
    model: string;
    thinking?: boolean;
  }) =>
    fetch("/api/settings/test", {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify(body),
    }).then(parse),
  importOntology: (ttl: string, force: boolean) =>
    fetch(`/api/ontology/import?force=${force ? "true" : "false"}`, {
      method: "POST",
      headers: { "Content-Type": "text/turtle" },
      body: ttl,
    }).then(parse),
};

export const exportTurtleHref = "/api/ontology/export?format=turtle";
export const exportJsonldHref = "/api/ontology/export?format=jsonld";
