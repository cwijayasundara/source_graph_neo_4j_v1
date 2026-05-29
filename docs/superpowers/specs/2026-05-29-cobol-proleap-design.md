# COBOL Support via ProLeap — Design Spec

**Date:** 2026-05-29
**Status:** Approved (design); pending implementation plan
**Scope:** Add COBOL codebase analysis to `code_context_graph`, producing a structural
call graph in Neo4j, surfaced through the existing API and `GraphView` UI.

---

## 1. Goals & Decisions

Add first-class COBOL support to the existing code-context-graph pipeline.

Decisions locked during brainstorming:

- **Corpus:** real mainframe COBOL — **fixed-format**, with **copybooks** and embedded
  **EXEC CICS / EXEC SQL**.
- **Parser:** **ProLeap** (ANTLR4, Java). Chosen over tree-sitter because it provides a
  real preprocessor (COPY/REPLACE expansion), configurable source formats (FIXED), and an
  AST/ASG proven on production banking/insurance COBOL. tree-sitter COBOL grammars are
  COBOL85-only, assume free-format, and do not expand copybooks.
- **JVM:** available in the deployment environment (Java 17 alongside the Python service).
- **Integration style:** **batch JSON extractor CLI** (Approach A) — a standalone Java
  artifact emits a versioned JSON contract; Python shells out once per repo.
- **v1 analysis depth:** **structural call graph** only. Data items, data-flow, and
  CICS/SQL/file modeling are explicitly deferred to v2.
- **Copybooks:** available on disk in known directories, configured as ProLeap search paths.

### Non-goals (v1)

- WORKING-STORAGE / LINKAGE data items, 88-level condition names.
- `READS` / `WRITES` / `MOVE` data-flow relationships.
- Modeling `EXEC CICS`, `EXEC SQL`, or file (`SELECT` / `FD`) usage as entities/edges.
  (v1 only confirms these constructs do not break parsing.)

---

## 2. Architecture

One new Java artifact plus one new Python module. Everything downstream — Neo4j ingestion,
enrichment, API, UI — is untouched except for **additive** entity vocabulary and colors.

```
                         ┌──────────────────────────────────────┐
  COBOL repo on disk ──► │  ccg-cobol-extractor.jar (Java 17)     │
  (.cbl/.cob/.cpy +      │  • ProLeap parse (FIXED format)        │
   copybook dirs)        │  • preprocessor expands COPY/REPLACE   │
                         │  • walk AST/ASG → entities + rels      │
                         │  • emit normalized JSON (v1 schema)    │
                         └───────────────┬────────────────────────┘
                                         │ stdout / output file (JSON)
                                         ▼
  parse_directory() ──► CobolParser (Python adapter)
      (parser.py)          • discovers COBOL files + copybook dirs
                           • subprocess → the JAR (one batch call)
                           • validates JSON, maps → list[ParseResult]
                                         │
                                         ▼
              existing CodeGraphIngester → Neo4j → enrichment → API → GraphView
```

### Components

1. **`ccg-cobol-extractor`** — new Java/Maven sub-project at `tools/cobol-extractor/`.
   A thin CLI wrapping ProLeap. Sole responsibility: COBOL AST/ASG → our JSON contract.
   It has no knowledge of Neo4j or Python. The versioned JSON schema is its only coupling
   surface.

2. **`CobolParser`** — new Python class in `parser.py`, peer to `PythonASTParser` and
   `TreeSitterCodeParser`. Locates the JAR, shells out once per repo, validates and maps
   the JSON into the existing `CodeEntity` / `CodeRelationship` / `ParseResult` models.

### Integration change

`parse_directory()` gains a COBOL branch. Unlike the per-file Python/tree-sitter dispatch,
COBOL is handled as a **single batch call** (one JVM startup; cross-file copybook and `CALL`
resolution), then its `ParseResult`s are appended to the returned list.

### Key design choice

The **JSON contract — not ProLeap's API — is the durable interface**. This lets us later
replace the subprocess CLI with a long-running sidecar service (Approach B) without changing
any Python code.

---

## 3. COBOL → Graph Mapping (v1)

### New entity kinds (added to `EntityKind` in `models.py`) — 4 only

| COBOL construct | `EntityKind`            | `qualified_name` scheme         | Notes                                  |
|-----------------|-------------------------|----------------------------------|----------------------------------------|
| Source file     | `MODULE` *(existing)*   | path-based, as today             | file-level container node              |
| `PROGRAM-ID`    | **`PROGRAM`** (new)     | program-id (uppercased)          | resolvable key for cross-program `CALL`|
| Procedure section | **`SECTION`** (new)   | `PROGID.SECTION`                 | PERFORM target                         |
| Paragraph       | **`PARAGRAPH`** (new)   | `PROGID.SECTION.PARA` or `PROGID.PARA` | PERFORM / GO TO target          |
| Copybook        | **`COPYBOOK`** (new)    | copybook name                    | COPY target                            |

Divisions (IDENTIFICATION/ENVIRONMENT/DATA/PROCEDURE) are **not** modeled as entities in v1.

### Relationships — all reuse existing `RelKind` (no new relationship types)

| COBOL                  | `RelKind`  | Direction                       | `metadata`              |
|------------------------|------------|---------------------------------|-------------------------|
| file contains program  | `DEFINES`  | MODULE → PROGRAM                | —                       |
| program contains unit  | `CONTAINS` | PROGRAM → SECTION → PARAGRAPH   | —                       |
| `PERFORM para/section` | `CALLS`    | paragraph → target              | `{"type": "perform"}`   |
| `GO TO para`           | `CALLS`    | paragraph → target              | `{"type": "goto"}`      |
| `CALL 'SUBPROG'`       | `CALLS`    | program → program (cross-prog)  | `{"type": "call"}`      |
| `COPY copybook`        | `IMPORTS`  | program → copybook              | —                       |

### Naming, hierarchy, resolution

- **Paragraph hierarchy:** real `SECTION → PARAGRAPH` nesting is preserved (paragraphs not
  inside a section attach directly to the program).
- **Program key = program-id.** Duplicate program-ids across an estate would merge into one
  node; v1 **accepts this and logs a warning**. (File-qualified keys are rejected for v1
  because they complicate `CALL` resolution, which keys on the literal program-id.)
- **Unresolved targets:** `CALL` / `COPY` whose target is not in the parsed set become
  **stub nodes** (`PROGRAM` / `COPYBOOK`) flagged `isExternal: true`, keeping the graph
  connected and letting the UI render externals distinctly. In-repo PERFORM/CALL/COPY
  resolve to real nodes.

### Model change

One **additive** field on `CodeEntity`: `is_external: bool = False`. Flows through to Neo4j
props and enables distinct UI styling of stubs. No other model changes.

### Frontend ripple (additive, polish-only)

Add the 4 new kinds to `kindColor()` in `web/src/lib/colors.ts` and to the `nodeVal` size
map in `GraphView.tsx` (suggested: PROGRAM large, SECTION medium, PARAGRAPH small,
COPYBOOK small). Missing entries fall back to defaults, so the graph renders correctly even
before this is added.

---

## 4. Interfaces & Contract

### JSON contract (`schemaVersion: 1`) — the durable boundary

One object per run, with one entry per file mirroring `ParseResult`:

```json
{
  "schemaVersion": 1,
  "files": [
    {
      "filePath": "src/PAYROLL.cbl",
      "parseStatus": "ok",
      "error": null,
      "entities": [
        {
          "kind": "Program",
          "qualifiedName": "PAYROLL",
          "simpleName": "PAYROLL",
          "filePath": "src/PAYROLL.cbl",
          "startLine": 1,
          "endLine": 420,
          "isExternal": false
        }
      ],
      "relationships": [
        {
          "sourceQname": "PAYROLL",
          "targetQname": "PAYROLL.MAIN-SECTION",
          "kind": "CONTAINS",
          "filePath": "src/PAYROLL.cbl",
          "line": 30,
          "metadata": {}
        }
      ]
    }
  ]
}
```

- `parseStatus`: `"ok"` | `"error"`. On `"error"`, `error` carries the message and the file
  contributes no entities/relationships.
- Field names map 1:1 onto `CodeEntity` / `CodeRelationship`.

### Java CLI (`ccg-cobol-extractor.jar`)

```
java -jar ccg-cobol-extractor.jar \
  --source-dir <repo> \
  --copybook-dir <dir>     # repeatable
  --format FIXED \         # FIXED | VARIABLE | FREE | TANDEM (default FIXED)
  --extensions .cbl,.cob,.cpy \
  --out -                  # '-' = stdout (default), else file path
```

- **Exit 0** = ran to completion, *even if some files failed* (those carry
  `parseStatus:"error"` inline — one bad program never sinks the batch).
- **Non-zero** only on fatal/config errors (bad args, unreadable `--source-dir`).
- stdout is **pure JSON**; all logs go to stderr.

### Python adapter (`CobolParser` in `parser.py`)

```python
class CobolParser:
    def __init__(self, repo_root, *, jar_path, copybook_dirs, source_format="FIXED"): ...
    def parse_repo(self) -> list[ParseResult]:
        # 1. glob COBOL files; if none -> return []
        # 2. subprocess the jar (one batch call), capture stdout
        # 3. validate schemaVersion, parse JSON -> list[ParseResult]
        # 4. log per-file parse errors; skip error files
```

Called **once** from `parse_directory()`. Configuration via env / `ccg.toml`:
`CCG_COBOL_EXTRACTOR_JAR`, copybook directories, source format.

**Graceful absence:** if COBOL files exist but the JAR is missing/unconfigured, log a clear
warning and **skip COBOL** — ingestion of other languages still succeeds. Never crash the
whole run.

---

## 5. Data Flow (ingest / clone path)

```
ccg ingest <repo>
  └─ parse_directory(repo_root)
       ├─ per-file: Python / tree-sitter parsers  (unchanged)
       └─ once: CobolParser.parse_repo()
            └─ subprocess → ccg-cobol-extractor.jar  (ProLeap, COPY expansion)
                 → JSON → validate → list[ParseResult]
  └─ CodeGraphIngester: _load_entity / _load_relationship   (unchanged)
       └─ Neo4j  →  SemanticEnricher (language-agnostic, unchanged)  →  API  →  GraphView
```

COBOL `ParseResult`s are appended to the list `parse_directory` already returns; the
ingester, enrichment, API, and UI need no behavioral change (only additive `EntityKind`s
and colors).

---

## 6. Error Handling

| Failure                              | Behavior                                                      |
|--------------------------------------|--------------------------------------------------------------|
| JAR missing / unconfigured, COBOL present | Warn, skip COBOL; other languages ingest normally       |
| Single program fails to parse        | `parseStatus:"error"` inline; that file skipped, batch continues |
| `schemaVersion` mismatch             | Raise clear error (contract drift must be loud)              |
| Subprocess non-zero exit             | Raise with captured stderr                                   |
| Unresolved CALL/COPY target          | Stub node, `isExternal:true` — not an error                  |
| Missing copybook (some present)      | ProLeap warns; affected COPY → external stub; batch continues|
| Subprocess timeout (configurable)    | Raise; surfaced in CLI output                                |

---

## 7. Testing Strategy (TDD, layered)

- **Java extractor (JUnit + golden files):** fixture COBOL programs — a main with
  sections/paragraphs + PERFORM/GO TO; a `CALL`er/callee pair; a program with `COPY`
  resolved from a copybook dir; one with `EXEC SQL` / `EXEC CICS` (confirm parsing does not
  break); one deliberately malformed. Assert emitted JSON against committed golden JSON.
- **Python adapter (pytest, no JVM):** feed canned JSON (including error files, externals,
  schema mismatch) to `CobolParser`'s JSON→`ParseResult` mapping via a stubbed subprocess.
  Pure, fast, hermetic.
- **Integration (opt-in, JVM-gated):** a tiny COBOL fixture repo run through the real JAR
  end-to-end, asserting node/edge counts in a throwaway graph. Marked to **skip cleanly when
  no JVM/JAR present**, so the core Python suite stays green everywhere.

---

## 8. Build & Packaging

- New Maven sub-project at `tools/cobol-extractor/` producing a fat JAR (ProLeap from Maven
  Central). Built via `mvn -f tools/cobol-extractor package`.
- Docker: add a Java 17 layer + the built JAR; `CCG_COBOL_EXTRACTOR_JAR` points at it.
  Update README and `docker-compose.yml`.
- The JAR is a **build artifact**, not committed to git; CI builds it (or it is vendored
  into the image).

---

## 9. Future Extensions (v2+)

The JSON schema is forward-compatible (versioned, additive). v2 candidates, in priority
order:

1. Data items (WORKING-STORAGE / LINKAGE, 88-levels) as entities.
2. `READS` / `WRITES` / `MOVE` data-flow relationships (from ProLeap's ASG).
3. `EXEC CICS` / `EXEC SQL` and file (`SELECT` / `FD`) usage as first-class entities/edges.
4. Optional transport swap: subprocess CLI → long-running Java sidecar (no Python change).
```
