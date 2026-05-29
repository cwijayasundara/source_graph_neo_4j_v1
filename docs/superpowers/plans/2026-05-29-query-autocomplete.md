# Query-Box Autocomplete Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add typeahead autocomplete to the graph Query panel so it suggests matching entity names (repo-scoped, case-insensitive prefix) as you type, and selecting one fills the qualified name.

**Architecture:** A new repo-scoped `suggest_entities` Cypher query + `GET /api/suggest` endpoint return name suggestions by case-insensitive prefix. The `QueryPanel` debounces input and shows a suggestion dropdown (reusing the SearchBar row style); selecting fills the box with the qualified name. Query execution is unchanged.

**Tech Stack:** Python 3.11 (FastAPI, Neo4j, pytest, `uv`); Next.js/React/TypeScript frontend.

**Reference spec:** `docs/superpowers/specs/2026-05-29-query-autocomplete-design.md`

**Baseline:** `uv run pytest -q` → **97 passed, 1 skipped**. Keep it green; this plan adds 3 tests.

---

## Task 1: `suggest_entities` query

**Files:**
- Modify: `src/code_context_graph/queries.py` (add a method to `CodeGraphQueries`)
- Test: `tests/test_queries.py` (FakeClient — no Neo4j)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_queries.py`:

```python
def test_suggest_entities_uses_case_insensitive_prefix() -> None:
    client = FakeClient()

    CodeGraphQueries(client).suggest_entities("pay")

    query, params = client.calls[0]
    assert "toLower(e.simple_name) STARTS WITH toLower($prefix)" in query
    assert "toLower(e.qualified_name) STARTS WITH toLower($prefix)" in query
    assert params == {"prefix": "pay", "limit": 10}


def test_suggest_entities_scopes_to_repo_and_limit() -> None:
    client = FakeClient()

    CodeGraphQueries(client).suggest_entities("pay", repo="owner/repo", limit=5)

    query, params = client.calls[0]
    assert "properties(e).repo = $repo" in query
    assert params == {"prefix": "pay", "repo": "owner/repo", "limit": 5}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_queries.py -k suggest -v`
Expected: FAIL — `AttributeError: 'CodeGraphQueries' object has no attribute 'suggest_entities'`.

- [ ] **Step 3: Implement the method**

In `src/code_context_graph/queries.py`, add this method to `CodeGraphQueries` (e.g. right after `search`):

```python
    def suggest_entities(self, prefix: str, repo: str | None = None, limit: int = 10) -> list[dict]:
        """Entity-name suggestions for typeahead: case-insensitive prefix match on
        simple or qualified name, optionally scoped to a repo. Shortest qualified
        names first."""
        return self.client.run(
            f"""
            MATCH (e:CodeEntity)
            WHERE (toLower(e.simple_name) STARTS WITH toLower($prefix)
                   OR toLower(e.qualified_name) STARTS WITH toLower($prefix))
              {self._repo_filter("e", repo)}
            RETURN e.qualified_name AS qualified_name,
                   e.simple_name AS simple_name,
                   e.kind AS kind
            ORDER BY size(e.qualified_name), e.qualified_name
            LIMIT $limit
            """,
            **self._params(repo, prefix=prefix, limit=limit),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_queries.py -k suggest -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: **99 passed, 1 skipped** (97 baseline + 2 new).

- [ ] **Step 6: Commit**

```bash
git add src/code_context_graph/queries.py tests/test_queries.py
git commit -m "feat(queries): add case-insensitive prefix suggest_entities query"
```

## Rules
- Modify ONLY the two named files. Do NOT `git add -A`/`git add .` — unrelated dirty files exist (.env.example, README.md, pyproject.toml, docker-compose.yml, source_code_to_analyse/, web/*).

---

## Task 2: `GET /api/suggest` endpoint

**Files:**
- Modify: `src/code_context_graph/api.py` (add endpoint; `Query` is already imported)
- Test: `tests/test_api.py`

- [ ] **Step 1: Write the failing tests**

In `tests/test_api.py`, add `/api/suggest` to the route-registration assertions in
`test_app_routes_registered` (after the `assert "/api/search" in paths` line):

```python
    assert "/api/suggest" in paths
```

Then append a new test:

```python
def test_suggest_endpoint_delegates_to_query(monkeypatch) -> None:
    from code_context_graph import api

    class FakeClient:
        def run(self, query: str, **params):
            return [{"qualified_name": "PAYROLL", "simple_name": "PAYROLL", "kind": "Program"}]

    monkeypatch.setattr(api, "get_client", lambda: FakeClient())

    out = api.suggest(q="pay", repo="sample_cobol", limit=10)

    assert out == [{"qualified_name": "PAYROLL", "simple_name": "PAYROLL", "kind": "Program"}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api.py -v`
Expected: FAIL — `test_app_routes_registered` fails the new assert, and `test_suggest_endpoint_delegates_to_query` fails with `AttributeError: module 'code_context_graph.api' has no attribute 'suggest'`.

- [ ] **Step 3: Implement the endpoint**

In `src/code_context_graph/api.py`, add this endpoint right after the existing `search_entities`
function (the `@app.get("/api/search")` block). `Query` is already imported at the top of the file:

```python
@app.get("/api/suggest")
def suggest(
    q: str = Query(..., min_length=1),
    repo: str | None = Query(None),
    limit: int = Query(10, ge=1, le=50),
) -> list[dict]:
    client = get_client()
    return CodeGraphQueries(client).suggest_entities(q, repo, limit)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_api.py -v`
Expected: PASS (all `test_api.py` tests pass, including the two touched/added).

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: **100 passed, 1 skipped** (99 + 1 new).

- [ ] **Step 6: Commit**

```bash
git add src/code_context_graph/api.py tests/test_api.py
git commit -m "feat(api): add GET /api/suggest entity-name typeahead endpoint"
```

## Rules
- Modify ONLY the two named files. Do NOT `git add -A`/`git add .`.

---

## Task 3: Query-panel typeahead (frontend)

**Files:**
- Modify: `web/src/lib/api.ts` (add `suggest` helper)
- Modify: `web/src/components/QueryPanel.tsx` (full replacement below)

No JS test framework here — verification is `npx tsc --noEmit` plus a live check.

- [ ] **Step 1: Add the `suggest` api helper**

In `web/src/lib/api.ts`, add this entry to the `api` object immediately after the `search:`
helper (the `search: (q: string) => ...` block):

```typescript
  suggest: (q: string, repo?: string) => {
    const params = new URLSearchParams({ q });
    if (repo) params.set("repo", repo);
    return json<{ qualified_name: string; simple_name: string; kind: string }[]>(
      `/api/suggest?${params.toString()}`
    );
  },
```

- [ ] **Step 2: Replace `web/src/components/QueryPanel.tsx` with the typeahead version**

Replace the ENTIRE contents of `web/src/components/QueryPanel.tsx` with:

```tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { kindColor } from "@/lib/colors";
import { Play, Loader2 } from "lucide-react";

const QUERY_TYPES = [
  { value: "callers", label: "What calls this?", placeholder: "function name" },
  { value: "calls", label: "What does it call?", placeholder: "function name" },
  { value: "impact", label: "Impact analysis", placeholder: "entity name" },
  { value: "hierarchy", label: "Class hierarchy", placeholder: "class name" },
  { value: "imports", label: "Module dependencies", placeholder: "module name" },
  { value: "importers", label: "Who imports this?", placeholder: "module name" },
  { value: "path", label: "Full call path", placeholder: "entry point name" },
  { value: "cochange", label: "Co-changed files", placeholder: "module name" },
  { value: "owners", label: "File owners", placeholder: "file path" },
  { value: "complex", label: "Complex functions", placeholder: "min complexity" },
];

type Suggestion = { qualified_name: string; simple_name: string; kind: string };

interface Props {
  repo?: string;
}

export function QueryPanel({ repo }: Props) {
  const [kind, setKind] = useState("callers");
  const [name, setName] = useState("");
  const [results, setResults] = useState<Record<string, unknown>[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [showSuggest, setShowSuggest] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const justSelected = useRef(false);

  const selected = QUERY_TYPES.find((q) => q.value === kind)!;
  // "complex" takes a number (min complexity), not an entity name — no suggestions.
  const suggestEnabled = kind !== "complex";

  // Debounced, repo-scoped suggestions as the user types. The cancelled flag
  // ignores out-of-order responses; cleanup clears the pending timer each keystroke.
  useEffect(() => {
    if (justSelected.current) {
      justSelected.current = false;
      return;
    }
    const term = name.trim();
    if (!suggestEnabled || term.length < 2) {
      setSuggestions([]);
      setShowSuggest(false);
      return;
    }
    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const data = await api.suggest(term, repo);
        if (!cancelled) {
          setSuggestions(data);
          setShowSuggest(data.length > 0);
          setActiveIndex(-1);
        }
      } catch {
        if (!cancelled) {
          setSuggestions([]);
          setShowSuggest(false);
        }
      }
    }, 200);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [name, repo, suggestEnabled]);

  const selectSuggestion = (s: Suggestion) => {
    justSelected.current = true;
    setName(s.qualified_name);
    setShowSuggest(false);
    setSuggestions([]);
    setActiveIndex(-1);
  };

  const onNameKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!showSuggest || suggestions.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, suggestions.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && activeIndex >= 0) {
      // Selecting from the dropdown; do not submit the query.
      e.preventDefault();
      selectSuggestion(suggestions[activeIndex]);
    } else if (e.key === "Escape") {
      setShowSuggest(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setShowSuggest(false);
    setLoading(true);
    setError(null);
    try {
      const minComplexity = kind === "complex" ? Number.parseInt(name.trim(), 10) || 5 : 5;
      const queryName = kind === "complex" ? "" : name.trim();
      const res = await api.runQuery(kind, queryName, 3, minComplexity, repo);
      setResults(res.results);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Query failed");
      setResults(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 space-y-4">
      <h3 className="text-sm font-medium text-zinc-300">Query the Graph</h3>

      <form onSubmit={handleSubmit} className="flex flex-wrap gap-3">
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value)}
          className="bg-zinc-800 border border-zinc-700 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          {QUERY_TYPES.map((q) => (
            <option key={q.value} value={q.value}>
              {q.label}
            </option>
          ))}
        </select>

        <div className="relative flex-1 min-w-[200px]">
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={onNameKeyDown}
            onFocus={() => {
              if (suggestions.length > 0) setShowSuggest(true);
            }}
            onBlur={() => setTimeout(() => setShowSuggest(false), 120)}
            placeholder={selected.placeholder}
            autoComplete="off"
            className="w-full bg-zinc-800 border border-zinc-700 rounded-md px-3 py-2 text-sm placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
          {showSuggest && suggestions.length > 0 && (
            <div className="absolute z-20 mt-1 w-full bg-zinc-900 border border-zinc-700 rounded-md shadow-lg divide-y divide-zinc-800 max-h-64 overflow-y-auto">
              {suggestions.map((s, i) => (
                <button
                  key={s.qualified_name}
                  type="button"
                  // Prevent the input's onBlur from firing before this click.
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => selectSuggestion(s)}
                  className={`w-full flex items-center gap-2 px-3 py-1.5 text-left transition ${
                    i === activeIndex ? "bg-zinc-800" : "hover:bg-zinc-800/50"
                  }`}
                >
                  <span
                    className="w-2 h-2 rounded-full shrink-0"
                    style={{ backgroundColor: kindColor(s.kind) }}
                  />
                  <span className="text-sm text-zinc-200 truncate">{s.qualified_name}</span>
                  <span className="ml-auto text-xs text-zinc-500 shrink-0">{s.kind}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        <button
          type="submit"
          disabled={loading || !name.trim()}
          className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 disabled:bg-zinc-700 disabled:text-zinc-400 px-4 py-2 rounded-md text-sm font-medium transition"
        >
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Play className="w-4 h-4" />
          )}
          Run
        </button>
      </form>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {results && (
        <div className="overflow-x-auto">
          {results.length === 0 ? (
            <p className="text-zinc-500 text-sm">No results found.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800">
                  {Object.keys(results[0]).map((col) => (
                    <th
                      key={col}
                      className="text-left text-zinc-400 font-medium py-2 px-3"
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {results.map((row, i) => (
                  <tr
                    key={i}
                    className="border-b border-zinc-800/50 hover:bg-zinc-800/30"
                  >
                    {Object.values(row).map((val, j) => (
                      <td key={j} className="py-1.5 px-3 text-zinc-300 font-mono text-xs">
                        {Array.isArray(val)
                          ? val.join(" -> ")
                          : String(val ?? "")}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: exit 0, no errors.

- [ ] **Step 4: Live check (optional, with API + Neo4j running)**

With the API server up and Java available, confirm the endpoint returns suggestions:
```bash
curl -s "http://localhost:8000/api/suggest?q=pay&repo=sample_cobol" | head -c 400
```
Expected: a JSON array including an entry with `"qualified_name":"PAYROLL"`. (If the server
isn't running, skip — the unit tests already cover the query/endpoint logic.)

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/api.ts web/src/components/QueryPanel.tsx
git commit -m "feat(ui): typeahead autocomplete for the query panel"
```

## Rules
- Modify ONLY the two named files. Do NOT `git add -A`/`git add .`.

---

## Self-review notes (spec coverage)

- §3.1 `suggest_entities` query (case-insensitive prefix, repo scope, limit, ordering) → Task 1.
- §3.2 `GET /api/suggest` → Task 2.
- §4.1 `api.suggest` helper → Task 3 Step 1.
- §4.2 debounced typeahead, qualified-name fill, ArrowUp/Down/Enter/Escape, blur dismissal,
  out-of-order guard (`cancelled`), select-suppression (`justSelected`) → Task 3 Step 2.
- §4.3 swallow suggest errors → Task 3 Step 2 (the `catch` in the effect).
- §5 tests → Task 1 (query) + Task 2 (endpoint) + Task 3 (tsc/live). Frontend has no unit-test
  framework, so it is verified via `tsc` + the live check.
- Not kind-aware except disabling suggestions for the numeric "complex" query (`suggestEnabled`)
  — a small, sensible refinement consistent with the spec's non-goal of kind filtering.

**Type consistency:** `suggest_entities(prefix, repo, limit)` ↔ endpoint `suggest(q, repo, limit)`
↔ `api.suggest(q, repo)` ↔ `Suggestion = {qualified_name, simple_name, kind}` (matches the query's
`RETURN` aliases) are consistent across tasks.
