# COBOL Package Isolation — Design Spec

**Date:** 2026-05-29
**Status:** Approved (design); pending implementation plan
**Type:** Pure refactor — **no behavior change**, same test outcomes.
**Related:** `docs/superpowers/specs/2026-05-29-cobol-proleap-design.md` (the feature this isolates)

---

## 1. Goal & Motivation

Keep COBOL support **completely isolated** from the core pipeline. Other languages
(Python via `ast`, JS/TS/Go/Rust/Java via tree-sitter) are handled inline in `parser.py`
and are "straightforward"; COBOL is the outlier (external Java/ProLeap subprocess behind a
JSON contract) and benefits from a hard boundary.

The COBOL code is already ~95% isolated:
- The Java extractor (`tools/cobol-extractor/`) is **already a separate Maven package** — untouched by this work.
- The COBOL Python logic is **already a single module** (`src/code_context_graph/cobol_parser.py`, 186 lines).
- The only genuine coupling is a direct import + 2 lines in `parser.py:parse_directory`.

This refactor formalizes the boundary: a COBOL sub-package plus a small registry seam so the
core pipeline has **zero COBOL-specific imports**.

### Decision: in-repo sub-package + registry seam

Chosen over (a) a separate installable `ccg-cobol` distribution — rejected as over-engineering
for a single-repo app (packaging/versioning/release overhead, core↔plugin dependency to
manage), and (b) a light tidy that keeps the direct import — rejected because it doesn't
invert the dependency.

### Non-goals
- No change to the Java extractor or the JSON contract.
- No change to runtime behavior, env vars, CLI, or API.
- **Not** moving the shared graph vocabulary out of the core (see §5) — that would break the
  single shared `kind` vocabulary used by Neo4j, the API, and the UI.

---

## 2. Target Structure

```
src/code_context_graph/
  __init__.py              # adds one line to register the COBOL extractor (see §4)
  language_registry.py     # NEW — repo-level extractor registry (~20 lines)
  cobol/
    __init__.py            # registers the COBOL extractor; re-exports public names
    mapping.py             # JSON contract -> ParseResult mapping (from cobol_parser.py)
    parser.py              # CobolParser subprocess driver (from cobol_parser.py)
  parser.py                # parse_directory uses the registry; NO cobol import
  cobol_parser.py          # DELETED (contents split into cobol/mapping.py + cobol/parser.py)
tests/
  cobol/                   # NEW — all COBOL unit tests live here
    test_mapping.py
    test_parser.py
    test_subprocess.py
    test_parse_directory.py
    test_models.py
  integration/
    test_cobol_e2e.py      # stays (gated e2e); import path updated
```

---

## 3. Module Responsibilities

- **`language_registry.py`** — a process-wide registry of *repo-level* extractors (functions
  `Path -> list[ParseResult]`). Public API:
  - `register_repo_extractor(fn: RepoExtractor) -> None`
  - `run_repo_extractors(repo_root: Path) -> list[ParseResult]` — runs each registered
    extractor and concatenates results.
  - `RepoExtractor = Callable[[Path], list[ParseResult]]` type alias.
  Has no knowledge of COBOL or any specific language.

- **`cobol/mapping.py`** — pure JSON→model mapping (moved verbatim from `cobol_parser.py`):
  `SUPPORTED_SCHEMA_VERSION`, `_entity_from_json`, `_relationship_from_json`,
  `cobol_json_to_parse_results`. Imports only `code_context_graph.models` + stdlib.

- **`cobol/parser.py`** — the subprocess driver (moved from `cobol_parser.py`):
  `CobolParser` (with `from_env`, `discover_files`, `parse_repo`, `_java_executable`,
  `_java_works`, `_run_extractor`), plus `COBOL_EXTENSIONS`, `_SKIP_PARTS`, and the module
  `logger`. Imports from `cobol.mapping` + `code_context_graph.models` + stdlib.

- **`cobol/__init__.py`** — wiring + public surface:
  - Re-exports `CobolParser`, `cobol_json_to_parse_results`, `SUPPORTED_SCHEMA_VERSION`,
    `COBOL_EXTENSIONS` so the package has a clean public API.
  - Defines the extractor and registers it:
    ```python
    def _cobol_repo_extractor(repo_root):
        return CobolParser.from_env(repo_root).parse_repo()
    register_repo_extractor(_cobol_repo_extractor)
    ```

---

## 4. Wiring & Dependency Direction

- `parser.py` drops `from code_context_graph.cobol_parser import CobolParser`. The tail of
  `parse_directory` becomes:
  ```python
  from code_context_graph.language_registry import run_repo_extractors
  ...
  results.extend(run_repo_extractors(repo_root))
  return results
  ```
  The per-file Python/tree-sitter dispatch is unchanged.

- Registration is triggered once, in `code_context_graph/__init__.py`:
  ```python
  from code_context_graph import cobol as _cobol  # noqa: F401  registers COBOL extractor
  ```

**Resulting dependency direction:**
```
code_context_graph/__init__  ──imports──>  cobol/__init__  ──>  cobol.parser, cobol.mapping
parser.py  ──imports──>  language_registry        (no COBOL symbol)
cobol/__init__  ──calls──>  language_registry.register_repo_extractor
```

**No import cycle:** `cobol.parser`/`cobol.mapping` import only `code_context_graph.models`
(which imports just `enum` + `pydantic`) and stdlib. Importing `code_context_graph` triggers
`__init__` → imports `cobol` → imports `models` (loads cleanly, no back-reference) → registers.
Registration is cheap (no JAR/subprocess touched at import time).

---

## 5. Shared-by-Design Items (intentionally NOT moved)

These are cross-cutting graph vocabulary/rendering and must stay in the core:
- `models.py`: `EntityKind.PROGRAM/SECTION/PARAGRAPH/COPYBOOK` and the generic `is_external`
  field — the single `kind` vocabulary keyed on by Neo4j, the graph API, and the UI.
- `web/src/lib/colors.ts` (4 entries) and `web/src/components/GraphView.tsx` (4 size entries).

Treatment: add `# COBOL` / `// COBOL` grouping comments for clarity only. Moving these would
fragment the shared vocabulary and break rendering/queries.

---

## 6. Tests

- Move the 5 COBOL unit tests into `tests/cobol/`, renamed for the package layout, updating
  imports to the new module paths:
  - `test_cobol_mapping.py`   → `tests/cobol/test_mapping.py`  (import from `code_context_graph.cobol`)
  - `test_cobol_parser.py`    → `tests/cobol/test_parser.py`
  - `test_cobol_subprocess.py`→ `tests/cobol/test_subprocess.py`
  - `test_parse_directory_cobol.py` → `tests/cobol/test_parse_directory.py` (monkeypatches the
    registry or the cobol extractor seam instead of `parser_mod.CobolParser`)
  - `test_models_cobol.py`    → `tests/cobol/test_models.py`
- `tests/integration/test_cobol_e2e.py` stays; only its `from code_context_graph.cobol_parser
  import CobolParser` becomes `from code_context_graph.cobol import CobolParser`.
- No `__init__.py` added under `tests/cobol/` (matches the repo's top-level test convention;
  pytest `rootdir` import works without it).

Public import compatibility: after the move, `from code_context_graph.cobol import CobolParser,
cobol_json_to_parse_results, SUPPORTED_SCHEMA_VERSION, COBOL_EXTENSIONS` all resolve via the
package `__init__` re-exports. The old `code_context_graph.cobol_parser` module is removed; all
references are updated (only `parser.py` and the tests referenced it).

---

## 7. Verification (acceptance criteria)

1. `uv run pytest -q` → **92 passed, 1 skipped** (unchanged from before the refactor).
2. `uv run python -c "import code_context_graph; from code_context_graph.language_registry
   import run_repo_extractors; print('ok')"` → succeeds (registration + no import cycle).
3. `grep -rn "cobol" src/code_context_graph/parser.py` → **no matches** (core pipeline is
   COBOL-agnostic).
4. The JAVA_HOME end-to-end snippet (Python → JAR on `sample_cobol`) still returns the same
   graph (2 files, 11 entities, 13 relationships).
5. `ruff` clean on changed files.

---

## 8. Risks & Mitigations

- **Import cycle / eager-import cost** — mitigated: COBOL modules import only models+stdlib;
  registration is cheap; verified by acceptance check 2.
- **Stale references to `cobol_parser`** — only `parser.py` + tests reference it; all updated.
  Acceptance check 1 catches misses.
- **Test discovery for the new `tests/cobol/` dir** — no `__init__.py`, consistent with
  existing top-level tests; covered by check 1.
