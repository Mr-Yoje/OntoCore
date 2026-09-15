export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
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
    const detail =
      typeof body === "object" && body !== null && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : text || response.statusText;
    throw new ApiError(response.status, detail);
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
  createJob: (
    file: File,
    body: { extractor: string; provider_id?: string; model?: string; thinking?: boolean },
  ) => {
    const form = new FormData();
    form.append("file", file);
    form.append("extractor", body.extractor);
    if (body.provider_id) form.append("provider_id", body.provider_id);
    if (body.model) form.append("model", body.model);
    form.append("thinking", body.thinking ? "true" : "false");
    return fetch("/api/jobs", { method: "POST", body: form }).then(parse);
  },
  getJob: (id: string) => fetch(`/api/jobs/${encodeURIComponent(id)}`).then(parse),
  typeCandidates: (jobId: string) =>
    fetch(`/api/jobs/${encodeURIComponent(jobId)}/type-candidates`).then(parse),
  acceptType: (id: string) =>
    fetch(`/api/type-candidates/${encodeURIComponent(id)}/accept`, { method: "POST" }).then(parse),
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
