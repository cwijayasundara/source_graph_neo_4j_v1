# COBOL Package Isolation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move COBOL Python support into an isolated `code_context_graph/cobol/` sub-package and route it through a small language-extractor registry, so the core pipeline (`parser.py`) has zero COBOL-specific imports.

**Architecture:** A new `language_registry.py` holds repo-level extractors (`Path → list[ParseResult]`). `parse_directory` calls `run_repo_extractors(repo_root)` instead of importing `CobolParser`. The COBOL module is split into `cobol/mapping.py` (JSON→model) and `cobol/parser.py` (subprocess driver); `cobol/__init__.py` registers the extractor and is imported once from the package `__init__.py`. Pure refactor — no behavior change.

**Tech Stack:** Python 3.11 (pydantic, pytest, `uv`). No Java/frontend behavior changes.

**Reference spec:** `docs/superpowers/specs/2026-05-29-cobol-package-isolation-design.md`

**Baseline:** before starting, `uv run pytest -q` reports **92 passed, 1 skipped**. Every task must keep that exact outcome (the integration test stays skipped unless a JVM is on PATH).

---

## Task 1: Language-extractor registry

**Files:**
- Create: `src/code_context_graph/language_registry.py`
- Test: `tests/test_language_registry.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_language_registry.py`:

```python
"""Repo-level language extractor registry. Pure, no Neo4j/JVM."""
from __future__ import annotations

from pathlib import Path

import pytest

from code_context_graph import language_registry as reg
from code_context_graph.language_registry import (
    register_repo_extractor,
    run_repo_extractors,
)
from code_context_graph.models import CodeEntity, EntityKind, ParseResult


@pytest.fixture
def isolated_registry():
    """Save/restore the global registry so these tests don't disturb the
    COBOL extractor that gets registered on package import."""
    saved = list(reg._extractors)
    reg._extractors.clear()
    yield
    reg._extractors[:] = saved


def test_register_and_run(isolated_registry):
    pr = ParseResult(file_path="X", entities=[], relationships=[])
    register_repo_extractor(lambda root: [pr])
    out = run_repo_extractors(Path("."))
    assert out == [pr]


def test_runs_extractors_in_registration_order(isolated_registry):
    register_repo_extractor(lambda r: [ParseResult(file_path="a", entities=[], relationships=[])])
    register_repo_extractor(lambda r: [ParseResult(file_path="b", entities=[], relationships=[])])
    out = run_repo_extractors(Path("."))
    assert [p.file_path for p in out] == ["a", "b"]


def test_run_with_no_extractors_returns_empty(isolated_registry):
    assert run_repo_extractors(Path(".")) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_language_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'code_context_graph.language_registry'`.

- [ ] **Step 3: Implement the registry**

Create `src/code_context_graph/language_registry.py`:

```python
"""Registry of repo-level source extractors.

Lets the core pipeline run language extractors (e.g. COBOL) without importing
them directly. An extractor is any callable that takes a repo root and returns
a list of ParseResult. Extractors register themselves at import time."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from code_context_graph.models import ParseResult

RepoExtractor = Callable[[Path], list[ParseResult]]

_extractors: list[RepoExtractor] = []


def register_repo_extractor(fn: RepoExtractor) -> None:
    _extractors.append(fn)


def run_repo_extractors(repo_root: Path) -> list[ParseResult]:
    results: list[ParseResult] = []
    for fn in _extractors:
        results.extend(fn(repo_root))
    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_language_registry.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/code_context_graph/language_registry.py tests/test_language_registry.py
git commit -m "feat(core): add repo-level language extractor registry"
```

---

## Task 2: Move COBOL into a `cobol/` sub-package and rewire the pipeline

This is the core move. It splits `cobol_parser.py` into two modules under a new package,
registers the extractor, removes the direct import from `parser.py`, deletes the old module,
and updates references in the existing test files (which still live in `tests/` at this point —
they are relocated in Task 3). The whole suite must be green at the end.

**Files:**
- Create: `src/code_context_graph/cobol/__init__.py`
- Create: `src/code_context_graph/cobol/mapping.py`
- Create: `src/code_context_graph/cobol/parser.py`
- Delete: `src/code_context_graph/cobol_parser.py`
- Modify: `src/code_context_graph/parser.py` (drop COBOL import; use registry)
- Modify: `src/code_context_graph/__init__.py` (register COBOL on import)
- Modify: `tests/test_cobol_mapping.py`, `tests/test_cobol_parser.py`, `tests/test_cobol_subprocess.py`, `tests/test_parse_directory_cobol.py`, `tests/integration/test_cobol_e2e.py` (import paths; one test rewritten)

- [ ] **Step 1: Create `cobol/mapping.py`**

Create `src/code_context_graph/cobol/mapping.py` (moved verbatim from the mapping half of `cobol_parser.py`):

```python
"""COBOL JSON contract -> ParseResult mapping. The JSON contract is the only
coupling surface with the Java extractor."""
from __future__ import annotations

from code_context_graph.models import (
    CodeEntity,
    CodeRelationship,
    EntityKind,
    ParseResult,
    RelKind,
)

SUPPORTED_SCHEMA_VERSION: int = 1


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

- [ ] **Step 2: Create `cobol/parser.py`**

Create `src/code_context_graph/cobol/parser.py` (moved verbatim from the driver half of `cobol_parser.py`, importing the mapping from its new location):

```python
"""COBOL subprocess driver: discovers COBOL source files, runs the
ccg-cobol-extractor JAR, and maps its JSON output into ParseResults via
cobol.mapping."""
from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path

from code_context_graph.cobol.mapping import cobol_json_to_parse_results
from code_context_graph.models import ParseResult

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
        java_home: str | None = None,
        timeout: int = 600,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.jar_path = jar_path
        self.copybook_dirs = copybook_dirs
        self.source_format = source_format
        self.java_home = java_home
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
            java_home=os.getenv("JAVA_HOME"),
        )

    def _java_executable(self) -> str:
        """Resolve the java binary: prefer ``$JAVA_HOME/bin/java`` (so JAVA_HOME can
        be set in .env without putting Java on PATH), else fall back to ``java``."""
        if self.java_home:
            candidate = Path(self.java_home) / "bin" / "java"
            if candidate.exists():
                return str(candidate)
        return "java"

    @staticmethod
    def _java_works(java: str) -> bool:
        """True only if the java binary can actually run (handles macOS's stub
        ``/usr/bin/java`` that exists even with no JDK installed)."""
        try:
            return subprocess.run(
                [java, "-version"], capture_output=True, timeout=30
            ).returncode == 0
        except Exception:
            return False

    def discover_files(self) -> list[Path]:
        out: list[Path] = []
        for p in sorted(self.repo_root.rglob("*")):
            if p.suffix.lower() not in COBOL_EXTENSIONS:
                continue
            dir_parts = p.relative_to(self.repo_root).parts[:-1]  # exclude filename
            if any(part in _SKIP_PARTS or part.startswith(".") for part in dir_parts):
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
        java = self._java_executable()
        if not self._java_works(java):
            logger.warning(
                "Found %d COBOL file(s) but no working Java runtime "
                "(JAVA_HOME=%r, resolved java=%r). Skipping COBOL.",
                len(files), self.java_home, java,
            )
            return []
        payload = self._run_extractor(java)
        results = cobol_json_to_parse_results(payload)
        for f in payload.get("files", []):
            if f.get("parseStatus") == "error":
                logger.warning("COBOL parse error in %s: %s", f.get("filePath"), f.get("error"))
        return results

    def _run_extractor(self, java: str = "java") -> dict:
        cmd = [
            java, "-jar", str(self.jar_path),
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
        except FileNotFoundError as exc:
            raise RuntimeError(f"Java executable not found: {java}") from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"COBOL extractor failed (exit {exc.returncode}): {exc.stderr.strip()}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            stderr = (exc.stderr or "").strip()
            msg = f"COBOL extractor timed out after {self.timeout}s"
            if stderr:
                msg += f": {stderr[:200]}"
            raise RuntimeError(msg) from exc
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"COBOL extractor produced invalid JSON: {exc}") from exc
```

- [ ] **Step 3: Create `cobol/__init__.py`**

Create `src/code_context_graph/cobol/__init__.py`:

```python
"""COBOL language support (isolated sub-package).

Importing this package registers the COBOL repo-level extractor with the
language registry. Re-exports the public API so callers can do
``from code_context_graph.cobol import CobolParser``."""
from __future__ import annotations

from pathlib import Path

from code_context_graph.cobol.mapping import (
    SUPPORTED_SCHEMA_VERSION,
    cobol_json_to_parse_results,
)
from code_context_graph.cobol.parser import COBOL_EXTENSIONS, CobolParser
from code_context_graph.language_registry import register_repo_extractor
from code_context_graph.models import ParseResult

__all__ = [
    "CobolParser",
    "COBOL_EXTENSIONS",
    "cobol_json_to_parse_results",
    "SUPPORTED_SCHEMA_VERSION",
]


def _cobol_repo_extractor(repo_root: Path) -> list[ParseResult]:
    return CobolParser.from_env(repo_root).parse_repo()


register_repo_extractor(_cobol_repo_extractor)
```

- [ ] **Step 4: Delete the old module**

```bash
git rm src/code_context_graph/cobol_parser.py
```

- [ ] **Step 5: Rewire `parser.py` to use the registry**

In `src/code_context_graph/parser.py`:
(a) Delete the line: `from code_context_graph.cobol_parser import CobolParser`
(b) After the `from code_context_graph.models import (...)` block (around line 14), add:
```python
from code_context_graph.language_registry import run_repo_extractors
```
(c) In `parse_directory`, replace these two lines:
```python
    cobol_results = CobolParser.from_env(repo_root).parse_repo()
    results.extend(cobol_results)
```
with:
```python
    results.extend(run_repo_extractors(repo_root))
```

- [ ] **Step 6: Register COBOL on package import**

`src/code_context_graph/__init__.py` is currently empty. Set its entire contents to:
```python
"""Code Context Graph package.

Importing the package wires up optional language extractors (e.g. COBOL) into the
language registry so the core pipeline stays language-agnostic."""
from __future__ import annotations

from code_context_graph import cobol as _cobol  # noqa: F401  registers COBOL extractor
```

- [ ] **Step 7: Update imports in the existing COBOL tests (still in `tests/`)**

These files currently import from `code_context_graph.cobol_parser`. Update each import line to `code_context_graph.cobol`:
- `tests/test_cobol_mapping.py`: change `from code_context_graph.cobol_parser import (SUPPORTED_SCHEMA_VERSION, cobol_json_to_parse_results)` → `from code_context_graph.cobol import (SUPPORTED_SCHEMA_VERSION, cobol_json_to_parse_results)`
- `tests/test_cobol_parser.py`: change `from code_context_graph.cobol_parser import CobolParser, COBOL_EXTENSIONS` → `from code_context_graph.cobol import CobolParser, COBOL_EXTENSIONS`
- `tests/test_cobol_subprocess.py`: change `from code_context_graph.cobol_parser import CobolParser, SUPPORTED_SCHEMA_VERSION` → `from code_context_graph.cobol import CobolParser, SUPPORTED_SCHEMA_VERSION`
- `tests/integration/test_cobol_e2e.py`: change `from code_context_graph.cobol_parser import CobolParser` → `from code_context_graph.cobol import CobolParser`

(`tests/test_models_cobol.py` imports only `code_context_graph.models` — no change.)

- [ ] **Step 8: Rewrite `tests/test_parse_directory_cobol.py` to exercise the registry seam**

Replace the entire contents of `tests/test_parse_directory_cobol.py` with:

```python
"""parse_directory appends repo-extractor (e.g. COBOL) results. No JVM."""
from __future__ import annotations

from pathlib import Path

import code_context_graph.parser as parser_mod
from code_context_graph.models import CodeEntity, EntityKind, ParseResult
from code_context_graph.parser import parse_directory


def test_parse_directory_includes_repo_extractor_results(tmp_path, monkeypatch):
    (tmp_path / "app.py").write_text("def f():\n    return 1\n")

    fake = ParseResult(
        file_path="PAY.cbl",
        entities=[CodeEntity(kind=EntityKind.PROGRAM, qualified_name="PAY",
                             simple_name="PAY", file_path="PAY.cbl",
                             start_line=1, end_line=1)],
        relationships=[],
    )
    # parser.py calls run_repo_extractors(repo_root); stub it at that seam.
    monkeypatch.setattr(parser_mod, "run_repo_extractors", lambda root: [fake])

    results = parse_directory(tmp_path)
    kinds = {e.kind for r in results for e in r.entities}
    assert EntityKind.PROGRAM in kinds                  # repo-extractor results appended
    assert any(r.file_path.endswith("app.py") for r in results)  # python still parsed
```

- [ ] **Step 9: Run the full suite — must match baseline**

Run: `uv run pytest -q`
Expected: **92 passed, 1 skipped** (same as baseline; the integration test still skips). If anything errors with `ModuleNotFoundError: code_context_graph.cobol_parser`, a reference was missed in Step 7/8.

- [ ] **Step 10: Confirm the core pipeline is COBOL-agnostic**

Run: `grep -rni "cobol" src/code_context_graph/parser.py`
Expected: **no output** (zero matches).

Run: `uv run python -c "import sys; sys.path.insert(0,'src'); import code_context_graph; from code_context_graph.language_registry import _extractors; print('registered extractors:', len(_extractors))"`
Expected: prints `registered extractors: 1` (COBOL registered via package import; confirms no import cycle).

- [ ] **Step 11: Commit**

```bash
git add src/code_context_graph/cobol/ src/code_context_graph/parser.py src/code_context_graph/__init__.py \
        tests/test_cobol_mapping.py tests/test_cobol_parser.py tests/test_cobol_subprocess.py \
        tests/test_parse_directory_cobol.py tests/integration/test_cobol_e2e.py
git rm --cached src/code_context_graph/cobol_parser.py 2>/dev/null || true
git commit -m "refactor(cobol): isolate COBOL into cobol/ sub-package behind a registry"
```
(The `git rm` in Step 4 already staged the deletion; this just ensures it's included.)

---

## Task 3: Relocate COBOL unit tests under `tests/cobol/`

Pure file moves (imports were fixed in Task 2). Keeps the test tree mirroring the package.

**Files:**
- Move: `tests/test_cobol_mapping.py` → `tests/cobol/test_mapping.py`
- Move: `tests/test_cobol_parser.py` → `tests/cobol/test_parser.py`
- Move: `tests/test_cobol_subprocess.py` → `tests/cobol/test_subprocess.py`
- Move: `tests/test_parse_directory_cobol.py` → `tests/cobol/test_parse_directory.py`
- Move: `tests/test_models_cobol.py` → `tests/cobol/test_models.py`

- [ ] **Step 1: Move the files with git**

```bash
mkdir -p tests/cobol
git mv tests/test_cobol_mapping.py tests/cobol/test_mapping.py
git mv tests/test_cobol_parser.py tests/cobol/test_parser.py
git mv tests/test_cobol_subprocess.py tests/cobol/test_subprocess.py
git mv tests/test_parse_directory_cobol.py tests/cobol/test_parse_directory.py
git mv tests/test_models_cobol.py tests/cobol/test_models.py
```

- [ ] **Step 2: Run the suite — must still match baseline**

Run: `uv run pytest -q`
Expected: **92 passed, 1 skipped**. (No `__init__.py` is added under `tests/cobol/`, matching the existing top-level test convention; pytest discovers them via rootdir.)

Also confirm the COBOL tests are collected from the new location:
Run: `uv run pytest tests/cobol -q`
Expected: the COBOL unit tests run and pass (no collection errors).

- [ ] **Step 3: Commit**

```bash
git add tests/cobol/
git commit -m "test(cobol): relocate COBOL unit tests under tests/cobol/"
```

---

## Task 4: Grouping comments + final verification

Label the shared-by-design COBOL bits (kept in core) and run the full acceptance checks.

**Files:**
- Modify: `src/code_context_graph/models.py` (comment only)
- Modify: `web/src/lib/colors.ts` (comment only)
- Modify: `web/src/components/GraphView.tsx` (comment only)

- [ ] **Step 1: Comment the COBOL kinds in `models.py`**

In `src/code_context_graph/models.py`, the `EntityKind` enum has these four members appended after `DECORATOR = "Decorator"`:
```python
    PROGRAM = "Program"
    SECTION = "Section"
    PARAGRAPH = "Paragraph"
    COPYBOOK = "Copybook"
```
Add a comment line immediately above `PROGRAM = "Program"`:
```python
    # COBOL (shared graph vocabulary; see code_context_graph/cobol/)
```

- [ ] **Step 2: Comment the COBOL colors in `colors.ts`**

In `web/src/lib/colors.ts`, immediately above the line `  Program: "#0ea5e9",` add:
```typescript
  // COBOL kinds
```

- [ ] **Step 3: Comment the COBOL sizes in `GraphView.tsx`**

In `web/src/components/GraphView.tsx`, immediately above the line `              Program: 8,` add:
```typescript
              // COBOL kinds
```

- [ ] **Step 4: Typecheck the frontend**

Run: `cd web && npx tsc --noEmit`
Expected: exit 0, no errors.

- [ ] **Step 5: Final acceptance checks (from the spec)**

Run each and confirm:
```bash
uv run pytest -q                                    # 92 passed, 1 skipped
grep -rni cobol src/code_context_graph/parser.py    # (no output)
uv run python -c "import sys; sys.path.insert(0,'src'); import code_context_graph; print('import ok')"
```
Then the COBOL end-to-end check (only meaningful with the JAR built; skips harm nothing):
```bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@17 && export PATH="$JAVA_HOME/bin:$PATH"
SAMPLE="$PWD/source_code_to_analyse/sample_cobol"
PYTHONPATH=src CCG_COBOL_EXTRACTOR_JAR="$PWD/tools/cobol-extractor/target/ccg-cobol-extractor.jar" \
CCG_COBOL_COPYBOOK_DIRS="$SAMPLE" CCG_COBOL_FORMAT=FIXED \
uv run python -c "
from pathlib import Path
from code_context_graph.cobol import CobolParser
rs = CobolParser.from_env(Path('source_code_to_analyse/sample_cobol')).parse_repo()
print('files:', len(rs), 'entities:', sum(len(r.entities) for r in rs))
"
```
Expected: `files: 2 entities: 11` (unchanged from before the refactor). If `source_code_to_analyse/sample_cobol` is absent, skip this sub-check and note it.

- [ ] **Step 6: Commit**

```bash
git add src/code_context_graph/models.py web/src/lib/colors.ts web/src/components/GraphView.tsx
git commit -m "chore(cobol): label shared graph-vocabulary COBOL entries"
```

---

## Self-review notes (spec coverage)

- §2 target structure → Tasks 1–3 create exactly that layout.
- §3 module responsibilities (registry / mapping / parser / `__init__`) → Task 1 + Task 2 Steps 1–3.
- §4 wiring & dependency direction (parser.py uses registry; `__init__` registers; no cycle) → Task 2 Steps 5–6, verified Step 10.
- §5 shared-by-design kept in core with comments → Task 4 Steps 1–3.
- §6 tests relocated + imports updated + `test_parse_directory` rewritten → Task 2 Steps 7–8, Task 3.
- §7 acceptance criteria (92/1, import check, grep clean, e2e, ruff) → Task 2 Steps 9–10, Task 4 Steps 4–5. (Run `ruff check` on changed files if `ruff` is available; it is configured in `pyproject.toml`.)
- §8 risks (cycle, stale refs, discovery) → covered by the verification steps in Tasks 2–3.

**Note:** This is a pure refactor; "tests" are the existing suite staying green rather than new behavior. The only genuinely new tests are for the registry (Task 1), which is new code.
