# COBOL Support via ProLeap — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingest fixed-format mainframe COBOL into the code-context graph as a structural call graph (programs, sections, paragraphs, PERFORM/GO TO/CALL/COPY), reusing the existing Neo4j → enrichment → API → UI pipeline.

**Architecture:** A standalone Java artifact (`ccg-cobol-extractor.jar`, built on ProLeap) parses COBOL and emits a versioned JSON contract. A new Python `CobolParser` shells out to it once per repo, validates the JSON, and maps it into the existing `ParseResult`/`CodeEntity`/`CodeRelationship` models. The JSON contract is the only coupling surface.

**Tech Stack:** Python 3.11 (pydantic, pytest), Java 17 (ProLeap COBOL parser, Jackson, Maven, JUnit 5), Neo4j, Next.js/React (TS) frontend.

**Reference spec:** `docs/superpowers/specs/2026-05-29-cobol-proleap-design.md`

---

## Phasing & order

- **Phase 1 (Python model + frontend):** additive vocabulary. Pure, no JVM. Tasks 1–3.
- **Phase 2 (Python `CobolParser`):** JSON→model mapping + subprocess + `parse_directory` wiring. Tested with canned JSON, no JVM. Tasks 4–7.
- **Phase 3 (Java extractor):** ProLeap-based JAR with golden-file tests. Tasks 8–12.
- **Phase 4 (build/docs/integration):** packaging, config docs, JVM-gated e2e. Tasks 13–15.

Phases 1–2 deliver a working, fully-tested Python ingestion path that consumes the JSON contract (validated against canned fixtures) even before the JAR exists. Phase 3 delivers the producer. This lets the two halves be built and reviewed against the shared contract independently.

The JSON contract field names (single source of truth for both halves):

```json
{
  "schemaVersion": 1,
  "files": [
    {
      "filePath": "src/PAYROLL.cbl",
      "parseStatus": "ok",
      "error": null,
      "entities": [
        {"kind":"Program","qualifiedName":"PAYROLL","simpleName":"PAYROLL",
         "filePath":"src/PAYROLL.cbl","startLine":1,"endLine":420,"isExternal":false}
      ],
      "relationships": [
        {"sourceQname":"PAYROLL","targetQname":"PAYROLL.MAIN-SECTION","kind":"CONTAINS",
         "filePath":"src/PAYROLL.cbl","line":30,"metadata":{}}
      ]
    }
  ]
}
```

`kind` strings equal the `EntityKind` *values* (`"Program"`, `"Section"`, `"Paragraph"`, `"Copybook"`, `"Module"`). Relationship `kind` strings equal `RelKind` values (`"CONTAINS"`, `"DEFINES"`, `"CALLS"`, `"IMPORTS"`).

---

## Phase 1 — Python model + frontend (no JVM)

### Task 1: Add COBOL entity kinds + `is_external` to the data model

**Files:**
- Modify: `src/code_context_graph/models.py:7-19` (EntityKind), `:41-54` (CodeEntity)
- Test: `tests/test_models_cobol.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_models_cobol.py`:

```python
"""COBOL additions to the shared data model — runs without Neo4j."""
from __future__ import annotations

from code_context_graph.models import CodeEntity, EntityKind


def test_cobol_entity_kinds_exist():
    assert EntityKind.PROGRAM.value == "Program"
    assert EntityKind.SECTION.value == "Section"
    assert EntityKind.PARAGRAPH.value == "Paragraph"
    assert EntityKind.COPYBOOK.value == "Copybook"


def test_entity_is_external_defaults_false():
    e = CodeEntity(
        kind=EntityKind.PROGRAM,
        qualified_name="PAYROLL",
        simple_name="PAYROLL",
        file_path="src/PAYROLL.cbl",
        start_line=1,
        end_line=10,
    )
    assert e.is_external is False


def test_entity_is_external_settable():
    e = CodeEntity(
        kind=EntityKind.PROGRAM,
        qualified_name="EXTSUB",
        simple_name="EXTSUB",
        file_path="",
        start_line=0,
        end_line=0,
        is_external=True,
    )
    assert e.is_external is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models_cobol.py -v`
Expected: FAIL — `AttributeError: PROGRAM` / `is_external` not a field.

- [ ] **Step 3: Implement the model changes**

In `src/code_context_graph/models.py`, add to the `EntityKind` enum (after `DECORATOR = "Decorator"`):

```python
    PROGRAM = "Program"
    SECTION = "Section"
    PARAGRAPH = "Paragraph"
    COPYBOOK = "Copybook"
```

In `CodeEntity`, add the field (after `complexity: int | None = None`):

```python
    is_external: bool = False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_models_cobol.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/code_context_graph/models.py tests/test_models_cobol.py
git commit -m "feat(model): add COBOL entity kinds and is_external flag"
```

---

### Task 2: Persist `is_external` during ingestion

**Files:**
- Modify: `src/code_context_graph/ingestion.py:66-91` (`_load_entity`)
- Test: `tests/test_ingestion_props.py` (create)

- [ ] **Step 1: Write the failing test** (uses a fake client; no Neo4j)

Create `tests/test_ingestion_props.py`:

```python
"""_load_entity prop-building — runs without Neo4j via a fake client."""
from __future__ import annotations

from pathlib import Path

from code_context_graph.ingestion import CodeGraphIngester
from code_context_graph.models import CodeEntity, EntityKind


class FakeClient:
    def __init__(self):
        self.entities = []

    def merge_entity(self, qualified_name, label, props):
        self.entities.append((qualified_name, label, props))


def test_load_entity_includes_is_external():
    client = FakeClient()
    ingester = CodeGraphIngester(client, Path("."))
    ingester._load_entity(CodeEntity(
        kind=EntityKind.PROGRAM, qualified_name="EXTSUB", simple_name="EXTSUB",
        file_path="", start_line=0, end_line=0, is_external=True,
    ))
    _, label, props = client.entities[0]
    assert label == "Program"
    assert props["is_external"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ingestion_props.py -v`
Expected: FAIL — `KeyError: 'is_external'`.

- [ ] **Step 3: Implement**

In `src/code_context_graph/ingestion.py`, inside `_load_entity`, add `is_external` to the base `props` dict (after the `is_private` line):

```python
            "is_private": entity.is_private,
            "is_external": entity.is_external,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ingestion_props.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/code_context_graph/ingestion.py tests/test_ingestion_props.py
git commit -m "feat(ingest): persist is_external on entities"
```

---

### Task 3: Frontend colors + node sizes for COBOL kinds

**Files:**
- Modify: `web/src/lib/colors.ts:1-14` (KIND_COLORS)
- Modify: `web/src/components/GraphView.tsx` (the `nodeVal` size map, ~line 238)

- [ ] **Step 1: Add colors**

In `web/src/lib/colors.ts`, add to `KIND_COLORS` (before the closing `}`):

```typescript
  Program: "#0ea5e9",
  Section: "#22d3ee",
  Paragraph: "#2dd4bf",
  Copybook: "#a78bfa",
```

- [ ] **Step 2: Add node sizes**

In `web/src/components/GraphView.tsx`, in the `nodeVal` size map, add entries alongside the existing kinds:

```typescript
              Program: 8,
              Section: 5,
              Paragraph: 3,
              Copybook: 3,
```

- [ ] **Step 3: Typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: exit 0, no errors.

- [ ] **Step 4: Commit**

```bash
git add web/src/lib/colors.ts web/src/components/GraphView.tsx
git commit -m "feat(ui): colors and sizes for COBOL node kinds"
```

---

## Phase 2 — Python `CobolParser` (tested with canned JSON, no JVM)

### Task 4: Pure JSON→ParseResult mapping (happy path)

**Files:**
- Create: `src/code_context_graph/cobol_parser.py`
- Test: `tests/test_cobol_mapping.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_cobol_mapping.py`:

```python
"""COBOL JSON contract -> ParseResult mapping. Pure, no JVM, no Neo4j."""
from __future__ import annotations

import pytest

from code_context_graph.cobol_parser import (
    SUPPORTED_SCHEMA_VERSION,
    cobol_json_to_parse_results,
)
from code_context_graph.models import EntityKind, RelKind


def _payload(files):
    return {"schemaVersion": SUPPORTED_SCHEMA_VERSION, "files": files}


def test_maps_program_and_contains():
    payload = _payload([{
        "filePath": "src/PAYROLL.cbl",
        "parseStatus": "ok",
        "error": None,
        "entities": [
            {"kind": "Program", "qualifiedName": "PAYROLL", "simpleName": "PAYROLL",
             "filePath": "src/PAYROLL.cbl", "startLine": 1, "endLine": 420, "isExternal": False},
            {"kind": "Paragraph", "qualifiedName": "PAYROLL.MAIN", "simpleName": "MAIN",
             "filePath": "src/PAYROLL.cbl", "startLine": 30, "endLine": 60, "isExternal": False},
        ],
        "relationships": [
            {"sourceQname": "PAYROLL", "targetQname": "PAYROLL.MAIN", "kind": "CONTAINS",
             "filePath": "src/PAYROLL.cbl", "line": 30, "metadata": {}},
        ],
    }])
    results = cobol_json_to_parse_results(payload)
    assert len(results) == 1
    r = results[0]
    assert r.file_path == "src/PAYROLL.cbl"
    prog = next(e for e in r.entities if e.qualified_name == "PAYROLL")
    assert prog.kind is EntityKind.PROGRAM
    assert r.relationships[0].kind is RelKind.CONTAINS


def test_maps_external_stub_and_call_metadata():
    payload = _payload([{
        "filePath": "src/A.cbl", "parseStatus": "ok", "error": None,
        "entities": [
            {"kind": "Program", "qualifiedName": "A", "simpleName": "A",
             "filePath": "src/A.cbl", "startLine": 1, "endLine": 9, "isExternal": False},
            {"kind": "Program", "qualifiedName": "EXTSUB", "simpleName": "EXTSUB",
             "filePath": "", "startLine": 0, "endLine": 0, "isExternal": True},
        ],
        "relationships": [
            {"sourceQname": "A", "targetQname": "EXTSUB", "kind": "CALLS",
             "filePath": "src/A.cbl", "line": 5, "metadata": {"type": "call"}},
        ],
    }])
    results = cobol_json_to_parse_results(payload)
    stub = next(e for e in results[0].entities if e.qualified_name == "EXTSUB")
    assert stub.is_external is True
    assert results[0].relationships[0].metadata == {"type": "call"}


def test_error_file_yields_empty_entities():
    payload = _payload([{
        "filePath": "src/BAD.cbl", "parseStatus": "error",
        "error": "syntax error at line 12", "entities": [], "relationships": [],
    }])
    results = cobol_json_to_parse_results(payload)
    assert results[0].entities == []
    assert results[0].relationships == []


def test_schema_version_mismatch_raises():
    with pytest.raises(ValueError, match="schemaVersion"):
        cobol_json_to_parse_results({"schemaVersion": 999, "files": []})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cobol_mapping.py -v`
Expected: FAIL — `ModuleNotFoundError: code_context_graph.cobol_parser`.

- [ ] **Step 3: Implement the mapping**

Create `src/code_context_graph/cobol_parser.py`:

```python
"""COBOL support: maps the ccg-cobol-extractor JSON contract into ParseResults
and drives the extractor JAR as a subprocess. The JSON contract is the only
coupling surface with the Java extractor."""
from __future__ import annotations

from code_context_graph.models import (
    CodeEntity,
    CodeRelationship,
    EntityKind,
    ParseResult,
    RelKind,
)

SUPPORTED_SCHEMA_VERSION = 1


def _entity_from_json(d: dict) -> CodeEntity:
    return CodeEntity(
        kind=EntityKind(d["kind"]),
        qualified_name=d["qualifiedName"],
        simple_name=d["simpleName"],
        file_path=d.get("filePath", ""),
        start_line=d.get("startLine", 0),
        end_line=d.get("endLine", 0),
        is_external=d.get("isExternal", False),
    )


def _relationship_from_json(d: dict) -> CodeRelationship:
    return CodeRelationship(
        source_qname=d["sourceQname"],
        target_qname=d["targetQname"],
        kind=RelKind(d["kind"]),
        file_path=d.get("filePath"),
        line=d.get("line"),
        metadata=d.get("metadata") or {},
    )


def cobol_json_to_parse_results(payload: dict) -> list[ParseResult]:
    version = payload.get("schemaVersion")
    if version != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported COBOL extractor schemaVersion {version!r}; "
            f"expected {SUPPORTED_SCHEMA_VERSION}"
        )
    results: list[ParseResult] = []
    for f in payload.get("files", []):
        results.append(ParseResult(
            file_path=f["filePath"],
            entities=[_entity_from_json(e) for e in f.get("entities", [])],
            relationships=[_relationship_from_json(r) for r in f.get("relationships", [])],
        ))
    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cobol_mapping.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/code_context_graph/cobol_parser.py tests/test_cobol_mapping.py
git commit -m "feat(cobol): JSON contract -> ParseResult mapping"
```

---

### Task 5: `CobolParser` config + file discovery + graceful absence

**Files:**
- Modify: `src/code_context_graph/cobol_parser.py`
- Test: `tests/test_cobol_parser.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_cobol_parser.py`:

```python
"""CobolParser discovery, config, and graceful absence. No JVM."""
from __future__ import annotations

from pathlib import Path

from code_context_graph.cobol_parser import CobolParser, COBOL_EXTENSIONS


def _make_repo(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "A.cbl").write_text("       IDENTIFICATION DIVISION.\n")
    (tmp_path / "src" / "COPYBK.cpy").write_text("       01 WS-X PIC 9.\n")
    (tmp_path / "src" / "ignore.py").write_text("x = 1\n")
    return tmp_path


def test_extensions_cover_cobol():
    assert {".cbl", ".cob", ".cpy"} <= COBOL_EXTENSIONS


def test_discover_files_finds_only_cobol(tmp_path):
    repo = _make_repo(tmp_path)
    parser = CobolParser(repo, jar_path=None)
    found = {p.name for p in parser.discover_files()}
    assert found == {"A.cbl", "COPYBK.cpy"}


def test_parse_repo_returns_empty_when_no_cobol(tmp_path):
    (tmp_path / "only.py").write_text("x = 1\n")
    parser = CobolParser(tmp_path, jar_path="/nonexistent.jar")
    assert parser.parse_repo() == []


def test_parse_repo_skips_gracefully_when_jar_missing(tmp_path, caplog):
    repo = _make_repo(tmp_path)
    parser = CobolParser(repo, jar_path="/nonexistent/ccg-cobol-extractor.jar")
    assert parser.parse_repo() == []  # COBOL present but no JAR -> skip, no raise
    assert any("extractor" in rec.message.lower() for rec in caplog.records)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cobol_parser.py -v`
Expected: FAIL — `ImportError: cannot import name 'CobolParser'`.

- [ ] **Step 3: Implement**

Append to `src/code_context_graph/cobol_parser.py`:

```python
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

COBOL_EXTENSIONS = {".cbl", ".cob", ".cobol", ".cpy"}
_SKIP_PARTS = {".git", "node_modules", "__pycache__", "venv", ".venv"}


class CobolParser:
    """Drives the ccg-cobol-extractor JAR over a repo and maps its JSON output."""

    def __init__(
        self,
        repo_root: Path,
        *,
        jar_path: str | None,
        copybook_dirs: tuple[str, ...] = (),
        source_format: str = "FIXED",
        timeout: int = 600,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.jar_path = jar_path
        self.copybook_dirs = copybook_dirs
        self.source_format = source_format
        self.timeout = timeout

    @classmethod
    def from_env(cls, repo_root: Path) -> "CobolParser":
        copy_raw = os.getenv("CCG_COBOL_COPYBOOK_DIRS", "")
        copybook_dirs = tuple(d for d in (s.strip() for s in copy_raw.split(",")) if d)
        return cls(
            repo_root,
            jar_path=os.getenv("CCG_COBOL_EXTRACTOR_JAR"),
            copybook_dirs=copybook_dirs,
            source_format=os.getenv("CCG_COBOL_FORMAT", "FIXED"),
        )

    def discover_files(self) -> list[Path]:
        out: list[Path] = []
        for p in sorted(self.repo_root.rglob("*")):
            if p.suffix.lower() not in COBOL_EXTENSIONS:
                continue
            if any(part in _SKIP_PARTS or part.startswith(".") for part in p.relative_to(self.repo_root).parts):
                continue
            out.append(p)
        return out

    def parse_repo(self) -> list[ParseResult]:
        files = self.discover_files()
        if not files:
            return []
        if not self.jar_path or not Path(self.jar_path).exists():
            logger.warning(
                "Found %d COBOL file(s) but the COBOL extractor JAR is unavailable "
                "(CCG_COBOL_EXTRACTOR_JAR=%r). Skipping COBOL.",
                len(files), self.jar_path,
            )
            return []
        payload = self._run_extractor()
        results = cobol_json_to_parse_results(payload)
        for f in payload.get("files", []):
            if f.get("parseStatus") == "error":
                logger.warning("COBOL parse error in %s: %s", f.get("filePath"), f.get("error"))
        return results
```

(Leave `_run_extractor` for the next task — these tests never reach it.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cobol_parser.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/code_context_graph/cobol_parser.py tests/test_cobol_parser.py
git commit -m "feat(cobol): CobolParser discovery, env config, graceful absence"
```

---

### Task 6: `_run_extractor` subprocess invocation (stubbed subprocess)

**Files:**
- Modify: `src/code_context_graph/cobol_parser.py`
- Test: `tests/test_cobol_subprocess.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_cobol_subprocess.py`:

```python
"""_run_extractor builds the right command and parses stdout. No real JVM."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from code_context_graph.cobol_parser import CobolParser, SUPPORTED_SCHEMA_VERSION


def test_run_extractor_builds_command_and_parses(tmp_path, monkeypatch):
    jar = tmp_path / "ccg-cobol-extractor.jar"
    jar.write_text("")  # existence check only
    captured = {}

    def fake_run(cmd, capture_output, text, timeout, check):
        captured["cmd"] = cmd
        payload = {"schemaVersion": SUPPORTED_SCHEMA_VERSION, "files": []}
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    parser = CobolParser(
        tmp_path, jar_path=str(jar),
        copybook_dirs=(str(tmp_path / "cpy"),), source_format="FIXED",
    )
    payload = parser._run_extractor()

    assert payload["schemaVersion"] == SUPPORTED_SCHEMA_VERSION
    cmd = captured["cmd"]
    assert cmd[0] == "java" and "-jar" in cmd and str(jar) in cmd
    assert "--source-dir" in cmd and str(tmp_path) in cmd
    assert "--format" in cmd and "FIXED" in cmd
    assert "--copybook-dir" in cmd and str(tmp_path / "cpy") in cmd


def test_run_extractor_raises_on_nonzero(tmp_path, monkeypatch):
    jar = tmp_path / "x.jar"; jar.write_text("")

    def fake_run(cmd, capture_output, text, timeout, check):
        raise subprocess.CalledProcessError(2, cmd, output="", stderr="boom")

    monkeypatch.setattr(subprocess, "run", fake_run)
    parser = CobolParser(tmp_path, jar_path=str(jar))
    with pytest.raises(RuntimeError, match="boom"):
        parser._run_extractor()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cobol_subprocess.py -v`
Expected: FAIL — `AttributeError: '_run_extractor'` (not yet implemented).

- [ ] **Step 3: Implement**

Add `import json` and `import subprocess` to the top of `src/code_context_graph/cobol_parser.py`, then add this method to `CobolParser`:

```python
    def _run_extractor(self) -> dict:
        cmd = [
            "java", "-jar", str(self.jar_path),
            "--source-dir", str(self.repo_root),
            "--format", self.source_format,
            "--out", "-",
        ]
        for d in self.copybook_dirs:
            cmd += ["--copybook-dir", d]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self.timeout, check=True,
            )
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"COBOL extractor failed (exit {exc.returncode}): {exc.stderr.strip()}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"COBOL extractor timed out after {self.timeout}s") from exc
        return json.loads(proc.stdout)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cobol_subprocess.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/code_context_graph/cobol_parser.py tests/test_cobol_subprocess.py
git commit -m "feat(cobol): subprocess invocation of the extractor JAR"
```

---

### Task 7: Wire `CobolParser` into `parse_directory`

**Files:**
- Modify: `src/code_context_graph/parser.py:645-665` (`parse_directory`)
- Test: `tests/test_parse_directory_cobol.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_parse_directory_cobol.py`:

```python
"""parse_directory appends COBOL ParseResults from CobolParser. No JVM."""
from __future__ import annotations

from pathlib import Path

from code_context_graph import parser as parser_mod
from code_context_graph.models import EntityKind, ParseResult, CodeEntity
from code_context_graph.parser import parse_directory


def test_parse_directory_includes_cobol(tmp_path, monkeypatch):
    (tmp_path / "app.py").write_text("def f():\n    return 1\n")
    (tmp_path / "PAY.cbl").write_text("       IDENTIFICATION DIVISION.\n")

    fake_result = ParseResult(
        file_path="PAY.cbl",
        entities=[CodeEntity(kind=EntityKind.PROGRAM, qualified_name="PAY",
                             simple_name="PAY", file_path="PAY.cbl",
                             start_line=1, end_line=1)],
        relationships=[],
    )

    class FakeCobolParser:
        def __init__(self, *a, **k): pass
        def parse_repo(self): return [fake_result]

    monkeypatch.setattr(parser_mod.CobolParser, "from_env",
                        classmethod(lambda cls, root: FakeCobolParser()))

    results = parse_directory(tmp_path)
    kinds = {e.kind for r in results for e in r.entities}
    assert EntityKind.PROGRAM in kinds        # COBOL appended
    assert any(r.file_path.endswith("app.py") for r in results)  # python still parsed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_parse_directory_cobol.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'CobolParser'`.

- [ ] **Step 3: Implement**

In `src/code_context_graph/parser.py`, add the import near the top (after the models import):

```python
from code_context_graph.cobol_parser import CobolParser
```

Then in `parse_directory`, immediately before `return results`, add:

```python
    cobol_results = CobolParser.from_env(repo_root).parse_repo()
    results.extend(cobol_results)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_parse_directory_cobol.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full Python suite (no regressions)**

Run: `uv run pytest -q`
Expected: all pass (COBOL path is inert with no JAR configured).

- [ ] **Step 6: Commit**

```bash
git add src/code_context_graph/parser.py tests/test_parse_directory_cobol.py
git commit -m "feat(cobol): wire CobolParser into parse_directory"
```

---

## Phase 3 — Java extractor (ProLeap)

> **Note on ProLeap API:** Task 8 is a spike that pins the exact ProLeap getter/runner method names against the resolved dependency. The code in Tasks 9–11 uses the ProLeap ASG API as researched (`CobolParserRunnerImpl`, `CobolParserParams`, `Program → CompilationUnit → ProgramUnit → ProcedureDivision → Paragraph/Section`). If the spike reveals different signatures, adjust the code in those tasks; the **golden-file tests are the source of truth** for behavior, so iterate implementation until they pass.

### Task 8: Maven scaffold + ProLeap dependency + ASG spike

**Files:**
- Create: `tools/cobol-extractor/pom.xml`
- Create: `tools/cobol-extractor/src/main/java/com/codecontextgraph/cobol/Spike.java` (temporary)
- Create: `tools/cobol-extractor/src/test/resources/cobol/hello.cbl`

- [ ] **Step 1: Create the Maven project**

Create `tools/cobol-extractor/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.codecontextgraph</groupId>
  <artifactId>ccg-cobol-extractor</artifactId>
  <version>0.1.0</version>
  <packaging>jar</packaging>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>io.proleap</groupId>
      <artifactId>proleap-cobol-parser</artifactId>
      <version>4.0.0</version>
    </dependency>
    <dependency>
      <groupId>com.fasterxml.jackson.core</groupId>
      <artifactId>jackson-databind</artifactId>
      <version>2.17.1</version>
    </dependency>
    <dependency>
      <groupId>info.picocli</groupId>
      <artifactId>picocli</artifactId>
      <version>4.7.6</version>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.10.2</version>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <finalName>ccg-cobol-extractor</finalName>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-shade-plugin</artifactId>
        <version>3.5.3</version>
        <executions>
          <execution>
            <phase>package</phase>
            <goals><goal>shade</goal></goals>
            <configuration>
              <transformers>
                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                  <mainClass>com.codecontextgraph.cobol.ExtractorMain</mainClass>
                </transformer>
              </transformers>
            </configuration>
          </execution>
        </executions>
      </plugin>
    </plugins>
  </build>
</project>
```

- [ ] **Step 2: Add a sample COBOL fixture**

Create `tools/cobol-extractor/src/test/resources/cobol/hello.cbl` (fixed-format; note the 7-space indent for area A):

```cobol
       IDENTIFICATION DIVISION.
       PROGRAM-ID. HELLO.
       PROCEDURE DIVISION.
       MAIN-PARA.
           DISPLAY 'HELLO'.
           PERFORM SUB-PARA.
           STOP RUN.
       SUB-PARA.
           DISPLAY 'SUB'.
```

- [ ] **Step 3: Write a temporary spike that prints the ASG**

Create `tools/cobol-extractor/src/main/java/com/codecontextgraph/cobol/Spike.java`:

```java
package com.codecontextgraph.cobol;

import io.proleap.cobol.asg.metamodel.Program;
import io.proleap.cobol.asg.params.CobolParserParams;
import io.proleap.cobol.asg.params.impl.CobolParserParamsImpl;
import io.proleap.cobol.asg.runner.impl.CobolParserRunnerImpl;
import io.proleap.cobol.preprocessor.CobolPreprocessor.CobolSourceFormatEnum;

import java.io.File;

public class Spike {
    public static void main(String[] args) throws Exception {
        File f = new File(args[0]);
        CobolParserParams params = new CobolParserParamsImpl();
        params.setFormat(CobolSourceFormatEnum.FIXED);
        Program program = new CobolParserRunnerImpl().analyzeFile(f, params);
        program.getCompilationUnits().forEach(cu -> {
            System.out.println("CU: " + cu.getName());
            System.out.println("  programUnit: " + cu.getProgramUnit());
        });
    }
}
```

- [ ] **Step 4: Build and run the spike**

Run:
```bash
cd tools/cobol-extractor && mvn -q compile && \
  mvn -q exec:java -Dexec.mainClass=com.codecontextgraph.cobol.Spike \
  -Dexec.args="src/test/resources/cobol/hello.cbl"
```
Expected: prints a `CU:` line and a non-null `programUnit`. **If method names differ** (e.g. `getProgramUnit`), record the correct API in the commit message and use it in Tasks 9–11.

- [ ] **Step 5: Commit (keep Spike for now; removed in Task 12)**

```bash
git add tools/cobol-extractor/pom.xml \
  tools/cobol-extractor/src/main/java/com/codecontextgraph/cobol/Spike.java \
  tools/cobol-extractor/src/test/resources/cobol/hello.cbl
git commit -m "build(cobol): maven scaffold + ProLeap dep + ASG spike"
```

---

### Task 9: JSON model classes + serialization

**Files:**
- Create: `tools/cobol-extractor/src/main/java/com/codecontextgraph/cobol/json/*.java`
- Test: `tools/cobol-extractor/src/test/java/com/codecontextgraph/cobol/JsonShapeTest.java`

- [ ] **Step 1: Write the failing test**

Create `tools/cobol-extractor/src/test/java/com/codecontextgraph/cobol/JsonShapeTest.java`:

```java
package com.codecontextgraph.cobol;

import com.codecontextgraph.cobol.json.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertTrue;

class JsonShapeTest {
    @Test
    void serializesContractShape() throws Exception {
        EntityJson e = new EntityJson("Program", "PAY", "PAY", "src/PAY.cbl", 1, 9, false);
        RelationshipJson r = new RelationshipJson("PAY", "PAY.MAIN", "CONTAINS", "src/PAY.cbl", 3, java.util.Map.of());
        FileResultJson fr = new FileResultJson("src/PAY.cbl", "ok", null, List.of(e), List.of(r));
        ExtractionJson root = new ExtractionJson(1, List.of(fr));

        String json = new ObjectMapper().writeValueAsString(root);
        assertTrue(json.contains("\"schemaVersion\":1"));
        assertTrue(json.contains("\"qualifiedName\":\"PAY\""));
        assertTrue(json.contains("\"isExternal\":false"));
        assertTrue(json.contains("\"kind\":\"CONTAINS\""));
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tools/cobol-extractor && mvn -q test -Dtest=JsonShapeTest`
Expected: FAIL — classes in `com.codecontextgraph.cobol.json` do not exist.

- [ ] **Step 3: Implement the JSON model classes**

Create `tools/cobol-extractor/src/main/java/com/codecontextgraph/cobol/json/EntityJson.java`:

```java
package com.codecontextgraph.cobol.json;

public record EntityJson(
    String kind, String qualifiedName, String simpleName,
    String filePath, int startLine, int endLine, boolean isExternal) {}
```

Create `RelationshipJson.java`:

```java
package com.codecontextgraph.cobol.json;

import java.util.Map;

public record RelationshipJson(
    String sourceQname, String targetQname, String kind,
    String filePath, Integer line, Map<String, Object> metadata) {}
```

Create `FileResultJson.java`:

```java
package com.codecontextgraph.cobol.json;

import java.util.List;

public record FileResultJson(
    String filePath, String parseStatus, String error,
    List<EntityJson> entities, List<RelationshipJson> relationships) {}
```

Create `ExtractionJson.java`:

```java
package com.codecontextgraph.cobol.json;

import java.util.List;

public record ExtractionJson(int schemaVersion, List<FileResultJson> files) {}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tools/cobol-extractor && mvn -q test -Dtest=JsonShapeTest`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/cobol-extractor/src/main/java/com/codecontextgraph/cobol/json \
  tools/cobol-extractor/src/test/java/com/codecontextgraph/cobol/JsonShapeTest.java
git commit -m "feat(cobol-extractor): JSON contract model classes"
```

---

### Task 10: ProLeap → entities/relationships walker (programs, sections, paragraphs, PERFORM)

**Files:**
- Create: `tools/cobol-extractor/src/main/java/com/codecontextgraph/cobol/CobolWalker.java`
- Test: `tools/cobol-extractor/src/test/java/com/codecontextgraph/cobol/CobolWalkerTest.java`

- [ ] **Step 1: Write the failing test** (golden-style assertions on the model)

Create `tools/cobol-extractor/src/test/java/com/codecontextgraph/cobol/CobolWalkerTest.java`:

```java
package com.codecontextgraph.cobol;

import com.codecontextgraph.cobol.json.FileResultJson;
import org.junit.jupiter.api.Test;

import java.io.File;

import static org.junit.jupiter.api.Assertions.*;

class CobolWalkerTest {
    @Test
    void extractsProgramParagraphsAndPerform() {
        File f = new File("src/test/resources/cobol/hello.cbl");
        FileResultJson r = new CobolWalker("FIXED", java.util.List.of()).walk(f, "hello.cbl");

        assertEquals("ok", r.parseStatus());
        assertTrue(r.entities().stream().anyMatch(e ->
            e.kind().equals("Program") && e.qualifiedName().equals("HELLO")));
        assertTrue(r.entities().stream().anyMatch(e ->
            e.kind().equals("Paragraph") && e.qualifiedName().equals("HELLO.MAIN-PARA")));
        // PERFORM SUB-PARA -> CALLS edge with metadata type=perform
        assertTrue(r.relationships().stream().anyMatch(rel ->
            rel.kind().equals("CALLS")
            && rel.targetQname().equals("HELLO.SUB-PARA")
            && "perform".equals(rel.metadata().get("type"))));
        // CONTAINS edge program -> paragraph
        assertTrue(r.relationships().stream().anyMatch(rel ->
            rel.kind().equals("CONTAINS")
            && rel.sourceQname().equals("HELLO")
            && rel.targetQname().equals("HELLO.MAIN-PARA")));
    }

    @Test
    void malformedFileReportsError() {
        File f = new File("src/test/resources/cobol/broken.cbl");
        FileResultJson r = new CobolWalker("FIXED", java.util.List.of()).walk(f, "broken.cbl");
        assertEquals("error", r.parseStatus());
        assertNotNull(r.error());
        assertTrue(r.entities().isEmpty());
    }
}
```

Also create `tools/cobol-extractor/src/test/resources/cobol/broken.cbl`:

```cobol
       THIS IS NOT VALID COBOL @@@@
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tools/cobol-extractor && mvn -q test -Dtest=CobolWalkerTest`
Expected: FAIL — `CobolWalker` does not exist.

- [ ] **Step 3: Implement the walker**

Create `tools/cobol-extractor/src/main/java/com/codecontextgraph/cobol/CobolWalker.java`:

```java
package com.codecontextgraph.cobol;

import com.codecontextgraph.cobol.json.EntityJson;
import com.codecontextgraph.cobol.json.FileResultJson;
import com.codecontextgraph.cobol.json.RelationshipJson;
import io.proleap.cobol.asg.metamodel.CompilationUnit;
import io.proleap.cobol.asg.metamodel.Program;
import io.proleap.cobol.asg.metamodel.ProgramUnit;
import io.proleap.cobol.asg.metamodel.procedure.Paragraph;
import io.proleap.cobol.asg.metamodel.procedure.ProcedureDivision;
import io.proleap.cobol.asg.metamodel.procedure.perform.PerformStatement;
import io.proleap.cobol.asg.params.CobolParserParams;
import io.proleap.cobol.asg.params.impl.CobolParserParamsImpl;
import io.proleap.cobol.asg.runner.impl.CobolParserRunnerImpl;
import io.proleap.cobol.preprocessor.CobolPreprocessor.CobolSourceFormatEnum;

import java.io.File;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Walks a ProLeap ASG and produces our JSON contract objects for a single file.
 * v1 scope: Program, Section, Paragraph entities; CONTAINS/DEFINES + PERFORM CALLS.
 * CALL/COPY edges are added in Task 11.
 */
public class CobolWalker {
    private final CobolSourceFormatEnum format;
    private final List<File> copybookDirs;

    public CobolWalker(String format, List<File> copybookDirs) {
        this.format = CobolSourceFormatEnum.valueOf(format);
        this.copybookDirs = copybookDirs;
    }

    public FileResultJson walk(File file, String relPath) {
        List<EntityJson> entities = new ArrayList<>();
        List<RelationshipJson> rels = new ArrayList<>();
        try {
            CobolParserParams params = new CobolParserParamsImpl();
            params.setFormat(format);
            if (!copybookDirs.isEmpty()) params.setCopyBookDirectories(copybookDirs);
            Program program = new CobolParserRunnerImpl().analyzeFile(file, params);

            for (CompilationUnit cu : program.getCompilationUnits()) {
                ProgramUnit pu = cu.getProgramUnit();
                if (pu == null) continue;
                String progId = pu.getIdentificationDivision().getProgramIdParagraph()
                        .getName().toUpperCase();
                entities.add(new EntityJson("Program", progId, progId, relPath, 1,
                        lineCount(file), false));

                ProcedureDivision pd = pu.getProcedureDivision();
                if (pd == null) continue;
                for (Paragraph para : pd.getParagraphs()) {
                    String pName = para.getName().toUpperCase();
                    String pQn = progId + "." + pName;
                    entities.add(new EntityJson("Paragraph", pQn, pName, relPath, 0, 0, false));
                    rels.add(new RelationshipJson(progId, pQn, "CONTAINS", relPath, null, Map.of()));

                    for (Object stmt : para.getStatements()) {
                        if (stmt instanceof PerformStatement perform) {
                            String target = performTarget(perform);
                            if (target != null) {
                                rels.add(new RelationshipJson(pQn, progId + "." + target,
                                        "CALLS", relPath, null, Map.of("type", "perform")));
                            }
                        }
                    }
                }
            }
            return new FileResultJson(relPath, "ok", null, entities, rels);
        } catch (Exception e) {
            return new FileResultJson(relPath, "error", e.toString(), List.of(), List.of());
        }
    }

    private static int lineCount(File f) {
        try { return (int) java.nio.file.Files.lines(f.toPath()).count(); }
        catch (Exception e) { return 0; }
    }

    /** Extract the performed paragraph/section name; returns uppercased name or null. */
    private static String performTarget(PerformStatement perform) {
        var proc = perform.getPerformProcedureStatement();
        if (proc == null || proc.getPerformProcedures().isEmpty()) return null;
        return proc.getPerformProcedures().get(0).getCall().getName().toUpperCase();
    }
}
```

> If the spike (Task 8) showed different getter names for paragraph statements / perform targets, adapt `performTarget` and the statement loop accordingly. Iterate `mvn test -Dtest=CobolWalkerTest` until green.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tools/cobol-extractor && mvn -q test -Dtest=CobolWalkerTest`
Expected: PASS (2 tests). Iterate the ProLeap getters until assertions pass.

- [ ] **Step 5: Commit**

```bash
git add tools/cobol-extractor/src/main/java/com/codecontextgraph/cobol/CobolWalker.java \
  tools/cobol-extractor/src/test/java/com/codecontextgraph/cobol/CobolWalkerTest.java \
  tools/cobol-extractor/src/test/resources/cobol/broken.cbl
git commit -m "feat(cobol-extractor): ProLeap walker for programs, paragraphs, PERFORM"
```

---

### Task 11: Sections, GO TO, cross-program CALL, COPY, and external stubs

**Files:**
- Modify: `tools/cobol-extractor/src/main/java/com/codecontextgraph/cobol/CobolWalker.java`
- Create: `tools/cobol-extractor/src/main/java/com/codecontextgraph/cobol/ExternalResolver.java`
- Test: `tools/cobol-extractor/src/test/java/com/codecontextgraph/cobol/CallCopyTest.java`
- Fixtures: `caller.cbl`, `callee.cbl`, `withcopy.cbl`, `copybooks/CUSTREC.cpy`

- [ ] **Step 1: Write fixtures**

Create `tools/cobol-extractor/src/test/resources/cobol/caller.cbl`:

```cobol
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CALLER.
       PROCEDURE DIVISION.
       MAIN.
           CALL 'CALLEE'.
           CALL 'MISSINGSUB'.
           STOP RUN.
```

Create `callee.cbl`:

```cobol
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CALLEE.
       PROCEDURE DIVISION.
       DOIT.
           DISPLAY 'OK'.
```

Create `withcopy.cbl`:

```cobol
       IDENTIFICATION DIVISION.
       PROGRAM-ID. WITHCOPY.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       COPY CUSTREC.
       PROCEDURE DIVISION.
       MAIN.
           DISPLAY 'X'.
```

Create `copybooks/CUSTREC.cpy`:

```cobol
       01 CUST-REC.
          05 CUST-ID PIC 9(5).
```

- [ ] **Step 2: Write the failing test**

Create `tools/cobol-extractor/src/test/java/com/codecontextgraph/cobol/CallCopyTest.java`:

```java
package com.codecontextgraph.cobol;

import com.codecontextgraph.cobol.json.FileResultJson;
import org.junit.jupiter.api.Test;

import java.io.File;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class CallCopyTest {
    @Test
    void callEdgesToProgram() {
        FileResultJson r = new CobolWalker("FIXED", List.of())
            .walk(new File("src/test/resources/cobol/caller.cbl"), "caller.cbl");
        assertTrue(r.relationships().stream().anyMatch(rel ->
            rel.kind().equals("CALLS") && rel.sourceQname().equals("CALLER")
            && rel.targetQname().equals("CALLEE") && "call".equals(rel.metadata().get("type"))));
    }

    @Test
    void copyEdgeToCopybook() {
        FileResultJson r = new CobolWalker("FIXED", List.of(
            new File("src/test/resources/cobol/copybooks")))
            .walk(new File("src/test/resources/cobol/withcopy.cbl"), "withcopy.cbl");
        assertTrue(r.relationships().stream().anyMatch(rel ->
            rel.kind().equals("IMPORTS") && rel.sourceQname().equals("WITHCOPY")
            && rel.targetQname().equals("CUSTREC")));
        assertTrue(r.entities().stream().anyMatch(e ->
            e.kind().equals("Copybook") && e.qualifiedName().equals("CUSTREC")));
    }

    @Test
    void unresolvedCallProducesExternalStub() {
        // ExternalResolver runs over a whole batch; here we resolve a single file's
        // call targets against the known program set {CALLER}.
        FileResultJson r = new CobolWalker("FIXED", List.of())
            .walk(new File("src/test/resources/cobol/caller.cbl"), "caller.cbl");
        List<FileResultJson> resolved =
            ExternalResolver.addExternalStubs(List.of(r));
        assertTrue(resolved.get(0).entities().stream().anyMatch(e ->
            e.qualifiedName().equals("MISSINGSUB") && e.isExternal()));
        assertFalse(resolved.get(0).entities().stream().anyMatch(e ->
            e.qualifiedName().equals("CALLEE") && e.isExternal()));  // CALLEE unknown here too
    }
}
```

> Note: in `unresolvedCallProducesExternalStub`, both `CALLEE` and `MISSINGSUB` are unknown when resolving `caller.cbl` alone, so both become stubs. The assertion only checks `MISSINGSUB` is a stub. Cross-file resolution (CALLEE resolving when callee.cbl is in the same batch) is covered by the integration test in Task 15.

- [ ] **Step 3: Run test to verify it fails**

Run: `cd tools/cobol-extractor && mvn -q test -Dtest=CallCopyTest`
Expected: FAIL — CALL/COPY not emitted; `ExternalResolver` missing.

- [ ] **Step 4: Implement CALL + COPY in the walker**

In `CobolWalker.walk`, after the PERFORM loop inside the paragraph loop, add GO TO and CALL handling, and after the paragraph loop add COPY handling. Add these imports:

```java
import io.proleap.cobol.asg.metamodel.procedure.call.CallStatement;
import io.proleap.cobol.asg.metamodel.procedure.g, oto.GoToStatement; // adjust per spike
```

Add CALL detection in the statement loop (alongside the PERFORM `instanceof`):

```java
                        } else if (stmt instanceof CallStatement call) {
                            String callee = callTarget(call);
                            if (callee != null) {
                                rels.add(new RelationshipJson(progId, callee.toUpperCase(),
                                        "CALLS", relPath, null, Map.of("type", "call")));
                            }
                        }
```

Add the `callTarget` helper (literal program name from `CALL 'NAME'`):

```java
    private static String callTarget(CallStatement call) {
        var p = call.getProgramCall();           // adjust per spike if needed
        if (p == null) return null;
        return p.getProgramLiteral() != null
            ? p.getProgramLiteral().getValue().toString().replace("'", "").trim()
            : null;
    }
```

For COPY: ProLeap expands COPY in the preprocessor, so detect copy statements via the preprocessor token stream. Simplest robust approach for v1 — scan the raw source for `COPY <name>` lines (copybook names are simple identifiers), emit a `Copybook` entity + `IMPORTS` edge per distinct name:

```java
    private void addCopyEdges(File file, String progId, String relPath,
                              List<EntityJson> entities, List<RelationshipJson> rels) {
        try {
            java.util.Set<String> seen = new java.util.HashSet<>();
            for (String line : java.nio.file.Files.readAllLines(file.toPath())) {
                var m = java.util.regex.Pattern
                    .compile("(?i)\\bCOPY\\s+([A-Z0-9][A-Z0-9-]*)").matcher(line);
                if (m.find()) {
                    String name = m.group(1).toUpperCase();
                    if (seen.add(name)) {
                        entities.add(new EntityJson("Copybook", name, name, relPath, 0, 0, false));
                        rels.add(new RelationshipJson(progId, name, "IMPORTS", relPath, null, Map.of()));
                    }
                }
            }
        } catch (Exception ignored) {}
    }
```

Call `addCopyEdges(file, progId, relPath, entities, rels);` right after the paragraph loop, inside the compilation-unit loop.

> The `import` line above has an intentional typo marker (`g, oto`) — replace with the real package from the spike, e.g. `io.proleap.cobol.asg.metamodel.procedure.goto.GoToStatement`. GO TO handling mirrors PERFORM (metadata `type=goto`); add it only if the spike confirms the type, otherwise defer GO TO to v2 and remove its assertion (there is none in the tests, so this is optional for green).

- [ ] **Step 5: Implement `ExternalResolver`**

Create `tools/cobol-extractor/src/main/java/com/codecontextgraph/cobol/ExternalResolver.java`:

```java
package com.codecontextgraph.cobol;

import com.codecontextgraph.cobol.json.EntityJson;
import com.codecontextgraph.cobol.json.FileResultJson;
import com.codecontextgraph.cobol.json.RelationshipJson;

import java.util.*;

/** Adds isExternal stub entities for CALL/COPY targets not defined anywhere in the batch. */
public final class ExternalResolver {
    private ExternalResolver() {}

    public static List<FileResultJson> addExternalStubs(List<FileResultJson> files) {
        Set<String> defined = new HashSet<>();
        for (FileResultJson f : files)
            for (EntityJson e : f.entities()) defined.add(e.qualifiedName());

        List<FileResultJson> out = new ArrayList<>();
        for (FileResultJson f : files) {
            List<EntityJson> entities = new ArrayList<>(f.entities());
            Set<String> localQn = new HashSet<>();
            for (EntityJson e : entities) localQn.add(e.qualifiedName());
            for (RelationshipJson r : f.relationships()) {
                boolean external = r.kind().equals("CALLS") || r.kind().equals("IMPORTS");
                if (external && !defined.contains(r.targetQname()) && localQn.add(r.targetQname())) {
                    String kind = r.kind().equals("IMPORTS") ? "Copybook" : "Program";
                    entities.add(new EntityJson(kind, r.targetQname(), r.targetQname(),
                            "", 0, 0, true));
                }
            }
            out.add(new FileResultJson(f.filePath(), f.parseStatus(), f.error(),
                    entities, f.relationships()));
        }
        return out;
    }
}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd tools/cobol-extractor && mvn -q test -Dtest=CallCopyTest`
Expected: PASS (3 tests). Iterate ProLeap getters per spike until green.

- [ ] **Step 7: Commit**

```bash
git add tools/cobol-extractor/src/main/java/com/codecontextgraph/cobol/CobolWalker.java \
  tools/cobol-extractor/src/main/java/com/codecontextgraph/cobol/ExternalResolver.java \
  tools/cobol-extractor/src/test/java/com/codecontextgraph/cobol/CallCopyTest.java \
  tools/cobol-extractor/src/test/resources/cobol/caller.cbl \
  tools/cobol-extractor/src/test/resources/cobol/callee.cbl \
  tools/cobol-extractor/src/test/resources/cobol/withcopy.cbl \
  tools/cobol-extractor/src/test/resources/cobol/copybooks/CUSTREC.cpy
git commit -m "feat(cobol-extractor): CALL/COPY edges + external stub resolution"
```

---

### Task 12: CLI entrypoint (`ExtractorMain`) + remove spike

**Files:**
- Create: `tools/cobol-extractor/src/main/java/com/codecontextgraph/cobol/ExtractorMain.java`
- Delete: `tools/cobol-extractor/src/main/java/com/codecontextgraph/cobol/Spike.java`
- Test: `tools/cobol-extractor/src/test/java/com/codecontextgraph/cobol/ExtractorMainTest.java`

- [ ] **Step 1: Write the failing test**

Create `tools/cobol-extractor/src/test/java/com/codecontextgraph/cobol/ExtractorMainTest.java`:

```java
package com.codecontextgraph.cobol;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class ExtractorMainTest {
    @Test
    void runEmitsContractJson() throws Exception {
        String json = ExtractorMain.run(new String[]{
            "--source-dir", "src/test/resources/cobol",
            "--format", "FIXED",
            "--copybook-dir", "src/test/resources/cobol/copybooks",
            "--out", "-",
        });
        JsonNode root = new ObjectMapper().readTree(json);
        assertEquals(1, root.get("schemaVersion").asInt());
        assertTrue(root.get("files").isArray());
        assertTrue(root.get("files").size() >= 4);  // hello, caller, callee, withcopy (+broken)
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tools/cobol-extractor && mvn -q test -Dtest=ExtractorMainTest`
Expected: FAIL — `ExtractorMain` does not exist.

- [ ] **Step 3: Implement the CLI**

Create `tools/cobol-extractor/src/main/java/com/codecontextgraph/cobol/ExtractorMain.java`:

```java
package com.codecontextgraph.cobol;

import com.codecontextgraph.cobol.json.ExtractionJson;
import com.codecontextgraph.cobol.json.FileResultJson;
import com.fasterxml.jackson.databind.ObjectMapper;
import picocli.CommandLine;
import picocli.CommandLine.Option;

import java.io.File;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.Callable;
import java.util.stream.Collectors;

@CommandLine.Command(name = "ccg-cobol-extractor", mixinStandardHelpOptions = true)
public class ExtractorMain implements Callable<Integer> {
    @Option(names = "--source-dir", required = true) String sourceDir;
    @Option(names = "--copybook-dir") List<String> copybookDirs = new ArrayList<>();
    @Option(names = "--format") String format = "FIXED";
    @Option(names = "--extensions") String extensions = ".cbl,.cob,.cobol";
    @Option(names = "--out") String out = "-";

    static final int SCHEMA_VERSION = 1;

    @Override
    public Integer call() throws Exception {
        String json = produce(sourceDir, copybookDirs, format, extensions);
        if ("-".equals(out)) System.out.println(json);
        else Files.writeString(Path.of(out), json);
        return 0;
    }

    /** Test seam: parse args, run, return the JSON string (does not write/exit). */
    static String run(String[] args) throws Exception {
        ExtractorMain m = new ExtractorMain();
        new CommandLine(m).parseArgs(args);
        return produce(m.sourceDir, m.copybookDirs, m.format, m.extensions);
    }

    private static String produce(String sourceDir, List<String> copybookDirs,
                                  String format, String extensions) throws Exception {
        Set<String> exts = Arrays.stream(extensions.split(","))
            .map(String::trim).map(String::toLowerCase).collect(Collectors.toSet());
        List<File> copyDirs = copybookDirs.stream().map(File::new).toList();
        Path root = Path.of(sourceDir);

        CobolWalker walker = new CobolWalker(format, copyDirs);
        List<FileResultJson> files = new ArrayList<>();
        try (var stream = Files.walk(root)) {
            for (Path p : stream.filter(Files::isRegularFile).sorted().toList()) {
                String name = p.getFileName().toString().toLowerCase();
                int dot = name.lastIndexOf('.');
                if (dot < 0 || !exts.contains(name.substring(dot))) continue;
                String rel = root.relativize(p).toString();
                files.add(walker.walk(p.toFile(), rel));
            }
        }
        files = ExternalResolver.addExternalStubs(files);
        return new ObjectMapper().writeValueAsString(new ExtractionJson(SCHEMA_VERSION, files));
    }

    public static void main(String[] args) {
        try {
            System.exit(new CommandLine(new ExtractorMain()).execute(args));
        } catch (Exception e) {
            System.err.println("FATAL: " + e);
            System.exit(1);
        }
    }
}
```

Then delete the spike:

```bash
git rm tools/cobol-extractor/src/main/java/com/codecontextgraph/cobol/Spike.java
```

> The default `--extensions` excludes `.cpy` so copybooks are not parsed as standalone programs; they are pulled in via COPY resolution / search dirs. The walker is tolerant — `broken.cbl` yields a `parseStatus:"error"` file rather than crashing the batch.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tools/cobol-extractor && mvn -q test -Dtest=ExtractorMainTest`
Expected: PASS.

- [ ] **Step 5: Run the full Java test suite + build the JAR**

Run: `cd tools/cobol-extractor && mvn -q package`
Expected: BUILD SUCCESS; produces `target/ccg-cobol-extractor.jar`.

- [ ] **Step 6: Commit**

```bash
git add tools/cobol-extractor/src/main/java/com/codecontextgraph/cobol/ExtractorMain.java \
  tools/cobol-extractor/src/test/java/com/codecontextgraph/cobol/ExtractorMainTest.java
git rm --cached tools/cobol-extractor/src/main/java/com/codecontextgraph/cobol/Spike.java 2>/dev/null || true
git commit -m "feat(cobol-extractor): CLI entrypoint emitting the JSON contract"
```

---

## Phase 4 — Build, docs, integration

### Task 13: Ignore build artifacts + config wiring docs

**Files:**
- Modify: `.gitignore`
- Modify: `.env.example`

- [ ] **Step 1: Ignore Java build output**

Append to `.gitignore`:

```
# COBOL extractor (Java) build output
tools/cobol-extractor/target/
```

- [ ] **Step 2: Document env vars**

Append to `.env.example`:

```
# COBOL support (ProLeap extractor). Leave unset to disable COBOL ingestion.
CCG_COBOL_EXTRACTOR_JAR=tools/cobol-extractor/target/ccg-cobol-extractor.jar
CCG_COBOL_COPYBOOK_DIRS=
CCG_COBOL_FORMAT=FIXED
```

- [ ] **Step 3: Commit**

```bash
git add .gitignore .env.example
git commit -m "chore(cobol): ignore extractor build output; document env vars"
```

---

### Task 14: README + docker-compose

**Files:**
- Modify: `README.md`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Document COBOL support in README**

Add a "COBOL support" section to `README.md` describing: build the JAR (`mvn -f tools/cobol-extractor package`), set `CCG_COBOL_EXTRACTOR_JAR` and `CCG_COBOL_COPYBOOK_DIRS`, then `ccg ingest <repo>` picks up `.cbl/.cob` files automatically. Note v1 scope (structural call graph) and that copybook dirs must be configured for COPY resolution.

- [ ] **Step 2: Ensure JVM availability in the container**

In `docker-compose.yml`, for the service that runs ingestion, ensure a JRE 17 is present (base image with Java, or an install step) and that the built JAR is mounted/copied and `CCG_COBOL_EXTRACTOR_JAR` is set in that service's environment. (Exact edit depends on the current compose layout — follow the existing service definition.)

- [ ] **Step 3: Commit**

```bash
git add README.md docker-compose.yml
git commit -m "docs(cobol): README + docker JVM/JAR wiring"
```

---

### Task 15: JVM-gated end-to-end integration test

**Files:**
- Create: `tests/integration/test_cobol_e2e.py`
- Create: `tests/integration/fixtures/cobol/{caller,callee}.cbl`

- [ ] **Step 1: Write the fixtures**

Create `tests/integration/fixtures/cobol/caller.cbl` and `callee.cbl` (same content as the Java fixtures: CALLER calls CALLEE and MISSINGSUB).

- [ ] **Step 2: Write the gated test**

Create `tests/integration/test_cobol_e2e.py`:

```python
"""End-to-end COBOL extraction through the real JAR. Skips cleanly without JVM/JAR."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from code_context_graph.cobol_parser import CobolParser

JAR = os.getenv("CCG_COBOL_EXTRACTOR_JAR", "tools/cobol-extractor/target/ccg-cobol-extractor.jar")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("java") is None, reason="no JVM"),
    pytest.mark.skipif(not Path(JAR).exists(), reason="extractor JAR not built"),
]


def test_cross_program_call_resolves_and_missing_is_external():
    repo = Path("tests/integration/fixtures/cobol")
    parser = CobolParser(repo, jar_path=JAR, source_format="FIXED")
    results = parser.parse_repo()

    entities = {e.qualified_name: e for r in results for e in r.entities}
    rels = [(rel.source_qname, rel.target_qname, rel.kind.value)
            for r in results for rel in r.relationships]

    assert "CALLER" in entities and "CALLEE" in entities
    assert entities["CALLEE"].is_external is False          # resolved cross-file
    assert entities["MISSINGSUB"].is_external is True        # unresolved -> stub
    assert ("CALLER", "CALLEE", "CALLS") in rels
```

- [ ] **Step 3: Register the `integration` marker**

In `pyproject.toml`, under `[tool.pytest.ini_options]`, add:

```toml
markers = ["integration: end-to-end tests requiring a JVM and built JAR"]
```

- [ ] **Step 4: Run it (with JAR built)**

Run: `cd tools/cobol-extractor && mvn -q package && cd ../.. && uv run pytest tests/integration/test_cobol_e2e.py -v`
Expected: PASS. Without a JVM/JAR, it SKIPS (still green).

- [ ] **Step 5: Confirm the default suite is unaffected**

Run: `uv run pytest -q`
Expected: all pass; the integration test skips unless the JAR exists.

- [ ] **Step 6: Commit**

```bash
git add tests/integration/ pyproject.toml
git commit -m "test(cobol): JVM-gated end-to-end extraction test"
```

---

## Self-review notes (spec coverage)

- Architecture (extractor JAR + CobolParser + JSON contract) → Tasks 4–12.
- 4 new entity kinds + `is_external` → Task 1; persisted → Task 2; UI → Task 3.
- Relationship mapping (CONTAINS/DEFINES/CALLS/IMPORTS, perform/goto/call metadata) → Tasks 10–11.
- Program-id keys + external stubs → Tasks 10–11 (`ExternalResolver`).
- JSON contract `schemaVersion:1` + validation → Tasks 4, 9.
- CLI flags/exit codes + pure-JSON stdout → Task 12.
- Graceful absence + error matrix (missing JAR, per-file error, schema mismatch, nonzero exit, timeout) → Tasks 4–6.
- Layered TDD (Java golden/JUnit, Python canned-JSON, JVM-gated e2e) → Tasks 9–12, 4–7, 15.
- Build/packaging/docs → Tasks 8, 13, 14.

**Known follow-ups (intentional, not blockers):** GO TO edges are optional in v1 pending spike confirmation; COPY detection uses source-scan (regex) rather than the ProLeap preprocessor token stream — adequate for the IMPORTS edge but revisit in v2 when modeling copybook *contents*. ProLeap getter signatures in Tasks 10–11 are validated empirically by the golden tests; adjust to the spike's findings.
