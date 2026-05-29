# Query-Box Autocomplete — Design Spec

**Date:** 2026-05-29
**Status:** Approved (design); pending implementation plan
**Type:** Small feature (backend endpoint + frontend typeahead)

---

## 1. Goal & Motivation

The graph **Query** panel (`QueryPanel.tsx`) is a free-text box: you must already know an
entity's exact name to query it. This is especially hard for COBOL, whose entities have
UPPERCASE, dotted/hyphenated names (`PAYROLL`, `PAYROLL.MAIN-SECTION`). Add **typeahead
autocomplete** so the box suggests matching entity names (scoped to the current repo) as you
type, and selecting one fills in the precise qualified name.

This complements the recent case-insensitive query fix: case-insensitivity makes a typed name
match; autocomplete helps you find the name in the first place.

### Decisions (from brainstorming)
- **Suggestion source:** a new lightweight, repo-scoped, case-insensitive **prefix** endpoint
  (`name STARTS WITH`), not the existing fulltext `/api/search` (fulltext is fuzzy/whole-word
  and tokenizes COBOL's dotted names awkwardly).
- **On select:** fill the box with the entity's **qualified name** (unambiguous).

### Non-goals
- No change to how queries execute (`/api/query` unchanged).
- Not kind-aware (suggestions are not filtered by the selected query type) — deferred.
- No change to the separate `SearchBar` / `/api/search` fulltext feature.

---

## 2. Architecture

```
QueryPanel name input  ──(debounced prefix)──>  GET /api/suggest?q=&repo=&limit
                                                      │
                                                      ▼
                                       CodeGraphQueries.suggest_entities()
                                       (name STARTS WITH, case-insensitive, repo-scoped)
                                                      │
                                                      ▼
                              [{qualified_name, simple_name, kind}]  ──> dropdown
                                                      │ select
                                                      ▼
                              query box filled with qualified_name → run query as today
```

Two new units (backend query + endpoint) and one modified unit (the panel + an api helper).

---

## 3. Backend

### 3.1 `CodeGraphQueries.suggest_entities` (`src/code_context_graph/queries.py`)
```python
def suggest_entities(self, prefix: str, repo: str | None = None, limit: int = 10) -> list[dict]:
    """Entity-name suggestions for typeahead: case-insensitive prefix match on
    simple or qualified name, optionally scoped to a repo."""
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
- Reuses existing `_repo_filter` and `_params` helpers.
- `ORDER BY size(e.qualified_name)` surfaces shorter (closer) matches first, then alphabetical.
- `limit` is always passed as a parameter.

### 3.2 `GET /api/suggest` (`src/code_context_graph/api.py`)
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
Mirrors the existing `/api/search` endpoint shape (GET, `q`/`repo` query params).

---

## 4. Frontend

### 4.1 `api.ts` — new helper
```ts
suggest: (q: string, repo?: string) => {
  const params = new URLSearchParams({ q });
  if (repo) params.set("repo", repo);
  return json<{ qualified_name: string; simple_name: string; kind: string }[]>(
    `/api/suggest?${params.toString()}`
  );
},
```

### 4.2 `QueryPanel.tsx` — typeahead on the name input
- New state: `suggestions: Suggestion[]`, `showSuggest: boolean`, `activeIndex: number`.
- On name `onChange`: update `name`, and **debounced ~200ms**, if `name.trim().length >= 2`,
  call `api.suggest(name.trim(), repo)` → set `suggestions`, `showSuggest = true`. Below 2
  chars or empty → clear suggestions and hide.
- Render a dropdown beneath the input when `showSuggest && suggestions.length > 0`, reusing
  `SearchBar`'s row styling (kind-colored dot + qualified name + kind label).
- **Selection** (click or keyboard): set `name = suggestion.qualified_name`, hide the dropdown.
  Does NOT auto-run the query (user still picks the kind / presses Run) — keeps control explicit.
- **Keyboard:** ArrowDown/ArrowUp move `activeIndex`; Enter selects the active suggestion when
  the dropdown is open (and does NOT submit the query in that case); Escape hides the dropdown.
- **Dismissal:** Escape, selecting an item, or input blur (with a small delay so a click on a
  suggestion still registers) hides the dropdown.
- **Debounce:** implemented with a `setTimeout` cleared on each keystroke (via `useRef` for the
  timer) or an effect keyed on the input; stale responses are ignored (guard against
  out-of-order results by tracking the latest query term).

### 4.3 Failure handling
Suggestion fetch errors are swallowed (typeahead is a convenience): on error, clear suggestions
and hide the dropdown — never block typing or surface an error toast. The existing Run-query
error handling is unchanged.

---

## 5. Testing

- **Backend (`tests/test_queries.py`, FakeClient — no Neo4j):**
  - `suggest_entities("pay")` builds a query containing
    `toLower(e.simple_name) STARTS WITH toLower($prefix)` and
    `toLower(e.qualified_name) STARTS WITH toLower($prefix)`, params `{"prefix": "pay", "limit": 10}`.
  - `suggest_entities("pay", repo="r", limit=5)` includes `properties(e).repo = $repo` and
    params `{"prefix": "pay", "repo": "r", "limit": 5}`.
- **Live check (with running Neo4j + sample_cobol):** `suggest_entities("pay", "sample_cobol")`
  returns an entry with `qualified_name == "PAYROLL"`; `suggest_entities("payroll.", "sample_cobol")`
  returns the paragraphs/sections under `PAYROLL`.
- **Frontend:** `npx tsc --noEmit` clean. Manual: typing `pay` in the query box shows `PAYROLL`
  etc.; selecting fills the box with the qualified name; ↑/↓/Enter/Esc behave as specified.
- **Regression:** full Python suite stays green (97 passed, 1 skipped before this change; +2
  new suggest tests → 99 passed, 1 skipped).

---

## 6. Risks & Mitigations

- **Out-of-order async responses** (fast typing): track the latest term and ignore responses
  that don't match the current input. Mitigated in §4.2.
- **Enter ambiguity** (select vs. run): when the dropdown is open with an active item, Enter
  selects; otherwise Enter runs the query. Specified in §4.2.
- **Performance:** prefix match + `LIMIT 10` is cheap; debounce avoids a request per keystroke.
- **No `entity_name` index coverage for qualified_name prefix:** acceptable at this scale; the
  `simple_name` index helps, and graphs are small. Revisit only if suggest latency is felt.
