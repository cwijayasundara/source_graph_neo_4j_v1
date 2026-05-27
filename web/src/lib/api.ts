const BASE = "";

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, init);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  return res.json();
}

export interface Repo {
  slug: string;
  url: string;
  files_parsed: number;
  entities: number;
  relationships: number;
  authors: number;
  ingested_at: string;
  local_path?: string;
}

export interface GraphNode {
  id: string;
  name: string;
  kind: string;
  file: string;
  complexity: number | null;
  signature: string | null;
  docstring: string | null;
  is_async: boolean | null;
  layer: string | null;
  summary: string | null;
}

export interface GraphLink {
  source: string;
  target: string;
  type: string;
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

export interface EntityDetail {
  entity: Record<string, unknown>;
  incoming: { source: string; source_kind: string; relationship: string }[];
  outgoing: { target: string; target_kind: string; relationship: string }[];
}

export interface QueryResult {
  kind: string;
  name: string;
  results: Record<string, unknown>[];
}

export interface AskResult {
  answer: string;
  cypher: string;
  rows: Record<string, unknown>[];
  explanation: string;
}

export const api = {
  listRepos: () => json<Repo[]>("/api/repos"),

  getRepo: (slug: string) => json<Repo>(`/api/repos/${slug}`),

  cloneRepo: (url: string, branch?: string) =>
    json<{ status: string; repo: Repo; stats: Record<string, number> }>(
      "/api/repos/clone",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, branch }),
      }
    ),

  ingestLocal: (path: string) =>
    json<{ status: string; repo: Repo; stats: Record<string, number> }>(
      "/api/repos/local",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
      }
    ),

  deleteRepo: (slug: string) =>
    json<{ status: string }>(`/api/repos/${slug}`, { method: "DELETE" }),

  getGraph: (repo?: string, limit = 200) => {
    const params = new URLSearchParams();
    if (repo) params.set("repo", repo);
    params.set("limit", String(limit));
    return json<GraphData>(`/api/graph?${params}`);
  },

  getEntity: (qname: string) =>
    json<EntityDetail>(`/api/entity/${qname}`),

  runQuery: (
    kind: string,
    name: string,
    depth = 3,
    minComplexity = 5,
    repo?: string
  ) =>
    json<QueryResult>("/api/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kind,
        name,
        repo,
        depth,
        min_complexity: minComplexity,
      }),
    }),

  search: (q: string) =>
    json<Record<string, unknown>[]>(`/api/search?q=${encodeURIComponent(q)}`),

  askCodebase: (repo: string, question: string) =>
    json<AskResult>("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ repo, question }),
    }),

  stats: () =>
    json<{
      entity_counts: { kind: string; count: number }[];
      relationship_counts: { rel_type: string; count: number }[];
    }>("/api/stats"),
};
