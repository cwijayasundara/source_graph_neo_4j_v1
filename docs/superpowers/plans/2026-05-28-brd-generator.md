# BRD Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a comprehensive, grounded BRD (HTML) from an ingested repo using Claude Opus 4.7 with a dimension-scored LLM-as-judge retry loop, exposed via CLI, API, and the Web UI.

**Architecture:** New `code_context_graph.brd` subpackage with isolated units (`schema`, `context_builder`, `generator`, `judge`, `pipeline`, `renderer`, `storage`). A pipeline orchestrator drives `generator → judge → (retry|finalize)` up to `max_retries+1` times. Context strategy is single-shot when the repo fits in the 1M-token budget; otherwise map-reduce by directory clusters with recursive splitting.

**Tech Stack:** Python 3.11+, Anthropic SDK (`claude-opus-4-7[1m]`), Neo4j, FastAPI, Typer/Rich, Next.js/React.

**Design spec:** `docs/superpowers/specs/2026-05-28-brd-generator-design.md`

---

## File Map

**Create**
- `src/code_context_graph/brd/__init__.py` — exports `generate_brd`, `BRDResult`
- `src/code_context_graph/brd/schema.py` — Pydantic types
- `src/code_context_graph/brd/storage.py` — Neo4j `:BRD` node + disk I/O
- `src/code_context_graph/brd/renderer.py` — internal markdown → self-contained HTML
- `src/code_context_graph/brd/context_builder.py` — graph + source → prompt context, strategy decision, chunking
- `src/code_context_graph/brd/generator.py` — single-shot + map + reduce Claude calls
- `src/code_context_graph/brd/judge.py` — hard groundedness check + rubric scoring
- `src/code_context_graph/brd/pipeline.py` — generate → judge → retry orchestrator
- `tests/brd/__init__.py`
- `tests/brd/conftest.py` — shared fixtures (fake Neo4j client, fake Anthropic, sample BRD)
- `tests/brd/test_schema.py`
- `tests/brd/test_storage.py`
- `tests/brd/test_renderer.py`
- `tests/brd/test_context_builder.py`
- `tests/brd/test_generator.py`
- `tests/brd/test_judge.py`
- `tests/brd/test_pipeline.py`
- `tests/brd/test_api.py`
- `tests/brd/test_e2e.py`
- `tests/brd/cassettes/sample_repo_run.json` — recorded Claude responses
- `web/src/components/BRDPanel.tsx` — UI panel
- `web/src/components/BRDPanel.module.css` — styles (or inline Tailwind, matching existing patterns)

**Modify**
- `src/code_context_graph/cli.py` — add `brd` command
- `src/code_context_graph/api.py` — add 4 endpoints + background-task store
- `src/code_context_graph/schema.py` — add `:BRD` constraint
- `.env.example` — add `BRD_*` vars
- `pyproject.toml` — promote `anthropic` from optional `llm` extra to a base dep (BRD always uses it)
- `web/src/app/repo/[slug]/page.tsx` — mount `<BRDPanel>` (locate exact path during Task 14)

---

## Task 1: Project setup — config, deps, package skeleton

**Files:**
- Modify: `pyproject.toml`
- Modify: `.env.example`
- Create: `src/code_context_graph/brd/__init__.py`
- Create: `tests/brd/__init__.py`

- [ ] **Step 1: Add config to `.env.example`**

Append to `.env.example`:

```
# BRD Generator
BRD_MODEL=claude-opus-4-7
BRD_OUTPUT_DIR=./brd_output
BRD_MAX_RETRIES=2
BRD_SINGLE_SHOT_TOKEN_BUDGET=800000
BRD_MAX_CLUSTER_DEPTH=4
```

- [ ] **Step 2: Promote `anthropic` to base dep**

In `pyproject.toml`, move `anthropic>=0.40` from `[project.optional-dependencies].llm` into `[project].dependencies`. Remove the `llm` extra (or leave it empty for backwards-compat — but per spec, remove it).

- [ ] **Step 3: Run `uv sync`**

```bash
uv sync
```

Expected: anthropic installed in base env, no errors.

- [ ] **Step 4: Create empty package files**

```python
# src/code_context_graph/brd/__init__.py
"""BRD (Business Requirements Document) generator.

Public entrypoint: `generate_brd(repo_id, *, max_retries=2, force_map_reduce=False)`.
"""
```

```python
# tests/brd/__init__.py
```

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .env.example src/code_context_graph/brd tests/brd uv.lock
git commit -m "brd: add config, deps, and package skeleton"
```

---

## Task 2: Pydantic schema and Neo4j constraint

**Files:**
- Create: `src/code_context_graph/brd/schema.py`
- Modify: `src/code_context_graph/schema.py`
- Test: `tests/brd/test_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/brd/test_schema.py
from code_context_graph.brd.schema import (
    BRD,
    BRDSection,
    EvidenceMap,
    Dimension,
    DimensionScore,
    JudgeReport,
    FeedbackItem,
    Rating,
    Strategy,
    AttemptRecord,
    BRDResult,
)


def test_brd_with_evidence_map():
    brd = BRD(
        sections=[
            BRDSection(
                title="Executive Summary",
                body_markdown="A summary.",
                requirements=[],
            ),
        ],
        evidence_map={"FR-1": ["Function:src/x.py:foo"]},
        repo_id="my-repo",
        model="claude-opus-4-7[1m]",
        strategy=Strategy.single_shot,
    )
    assert brd.evidence_map["FR-1"] == ["Function:src/x.py:foo"]


def test_judge_report_rating_computed_from_weighted_score():
    scores = {
        Dimension.completeness: DimensionScore(score=5, rationale="ok"),
        Dimension.accuracy: DimensionScore(score=5, rationale="ok"),
        Dimension.clarity: DimensionScore(score=4, rationale="ok"),
        Dimension.consistency: DimensionScore(score=4, rationale="ok"),
        Dimension.actionability: DimensionScore(score=4, rationale="ok"),
    }
    report = JudgeReport(
        dimensions=scores,
        weighted_score=4.55,
        rating=Rating.high,
        feedback=[],
        groundedness_failures=[],
    )
    assert report.rating == Rating.high


def test_feedback_item_required_fields():
    item = FeedbackItem(
        dimension=Dimension.clarity,
        severity="high",
        suggestion="Define 'tenant' in the glossary.",
        target_section="Scope",
    )
    assert item.dimension == Dimension.clarity
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/brd/test_schema.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement the schema**

```python
# src/code_context_graph/brd/schema.py
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


EvidenceMap = dict[str, list[str]]
"""requirement_id -> list of graph entity ids and/or source file paths."""


class Rating(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class Strategy(str, Enum):
    single_shot = "single_shot"
    map_reduce = "map_reduce"


class Dimension(str, Enum):
    completeness = "completeness"
    accuracy = "accuracy"
    clarity = "clarity"
    consistency = "consistency"
    actionability = "actionability"


class DimensionScore(BaseModel):
    score: int = Field(ge=1, le=5)
    rationale: str


class FeedbackItem(BaseModel):
    dimension: Dimension
    severity: str  # "low" | "medium" | "high"
    suggestion: str
    target_section: str


class JudgeReport(BaseModel):
    dimensions: dict[Dimension, DimensionScore]
    weighted_score: float
    rating: Rating
    feedback: list[FeedbackItem]
    groundedness_failures: list[str]  # entity names not present in the graph


class Requirement(BaseModel):
    id: str  # e.g. "FR-1", "NFR-3"
    text: str


class BRDSection(BaseModel):
    title: str
    body_markdown: str
    requirements: list[Requirement] = Field(default_factory=list)


class BRD(BaseModel):
    sections: list[BRDSection]
    evidence_map: EvidenceMap
    repo_id: str
    model: str
    strategy: Strategy


class AttemptRecord(BaseModel):
    attempt: int  # 1-indexed
    rating: Rating
    weighted_score: float
    feedback: list[FeedbackItem]


class BRDResult(BaseModel):
    brd_id: str
    repo_id: str
    version: int
    rating: Rating
    weighted_score: float
    attempts: int
    attempt_history: list[AttemptRecord]
    model: str
    strategy: Strategy
    html_path: str
    created_at: datetime
    token_usage: dict[str, int] = Field(default_factory=dict)
```

- [ ] **Step 4: Add Neo4j `:BRD` constraint**

In `src/code_context_graph/schema.py`, append to `CONSTRAINTS`:

```python
CONSTRAINTS = [
    "CREATE CONSTRAINT entity_qname IF NOT EXISTS FOR (e:CodeEntity) REQUIRE e.qualified_name IS UNIQUE",
    "CREATE CONSTRAINT file_path IF NOT EXISTS FOR (f:File) REQUIRE f.path IS UNIQUE",
    "CREATE CONSTRAINT author_email IF NOT EXISTS FOR (a:Author) REQUIRE a.email IS UNIQUE",
    "CREATE CONSTRAINT brd_id IF NOT EXISTS FOR (b:BRD) REQUIRE b.id IS UNIQUE",
]
```

- [ ] **Step 5: Run test to verify it passes**

```bash
uv run pytest tests/brd/test_schema.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add src/code_context_graph/brd/schema.py src/code_context_graph/schema.py tests/brd/test_schema.py
git commit -m "brd: add pydantic schema and :BRD constraint"
```

---

## Task 3: Storage — Neo4j `:BRD` node + on-disk HTML

**Files:**
- Create: `src/code_context_graph/brd/storage.py`
- Test: `tests/brd/test_storage.py`
- Create: `tests/brd/conftest.py`

- [ ] **Step 1: Add a fake Neo4j client fixture**

```python
# tests/brd/conftest.py
from __future__ import annotations

from typing import Any

import pytest


class FakeNeo4jClient:
    """Records run() calls and returns scripted results."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._scripted: list[list[dict]] = []

    def script(self, *results: list[dict]) -> None:
        self._scripted = list(results)

    def run(self, query: str, **params: Any) -> list[dict]:
        self.calls.append((query, params))
        if self._scripted:
            return self._scripted.pop(0)
        return []


@pytest.fixture
def fake_client() -> FakeNeo4jClient:
    return FakeNeo4jClient()
```

- [ ] **Step 2: Write the failing test**

```python
# tests/brd/test_storage.py
from datetime import datetime, timezone
from pathlib import Path

from code_context_graph.brd.schema import (
    AttemptRecord, BRDResult, Dimension, DimensionScore, FeedbackItem,
    JudgeReport, Rating, Strategy,
)
from code_context_graph.brd.storage import BRDStorage


def _sample_judge_report() -> JudgeReport:
    return JudgeReport(
        dimensions={
            d: DimensionScore(score=5, rationale="ok") for d in Dimension
        },
        weighted_score=5.0,
        rating=Rating.high,
        feedback=[],
        groundedness_failures=[],
    )


def test_save_writes_html_file_and_returns_path(tmp_path, fake_client):
    storage = BRDStorage(fake_client, output_dir=tmp_path)
    fake_client.script([{"max_version": None}])  # no prior versions

    result = storage.save(
        repo_id="acme-app",
        html="<html><body>hello</body></html>",
        judge_report=_sample_judge_report(),
        attempt_history=[
            AttemptRecord(attempt=1, rating=Rating.high, weighted_score=5.0, feedback=[]),
        ],
        model="claude-opus-4-7[1m]",
        strategy=Strategy.single_shot,
        token_usage={"input": 10, "output": 5},
    )

    assert isinstance(result, BRDResult)
    assert result.version == 1
    path = Path(result.html_path)
    assert path.exists()
    assert path.read_text() == "<html><body>hello</body></html>"
    assert path.parent.name == "acme-app"


def test_save_increments_version(tmp_path, fake_client):
    storage = BRDStorage(fake_client, output_dir=tmp_path)
    fake_client.script([{"max_version": 3}])

    result = storage.save(
        repo_id="acme-app",
        html="<p>v4</p>",
        judge_report=_sample_judge_report(),
        attempt_history=[],
        model="claude-opus-4-7[1m]",
        strategy=Strategy.single_shot,
        token_usage={},
    )
    assert result.version == 4
```

- [ ] **Step 3: Run test to verify it fails**

```bash
uv run pytest tests/brd/test_storage.py -v
```

Expected: ImportError.

- [ ] **Step 4: Implement storage**

```python
# src/code_context_graph/brd/storage.py
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from code_context_graph.brd.schema import (
    AttemptRecord, BRDResult, JudgeReport, Rating, Strategy,
)


_SLUG_SAFE = re.compile(r"[^a-zA-Z0-9._-]+")


def _slugify(value: str) -> str:
    return _SLUG_SAFE.sub("-", value).strip("-") or "repo"


class BRDStorage:
    """Persist BRDs to Neo4j (versioned :BRD nodes) and disk (self-contained HTML files)."""

    def __init__(self, client, output_dir: Path | str | None = None) -> None:
        self.client = client
        out = output_dir or os.getenv("BRD_OUTPUT_DIR", "./brd_output")
        self.output_dir = Path(out).resolve()

    def _next_version(self, repo_id: str) -> int:
        rows = self.client.run(
            "MATCH (r:Repository {slug: $repo_id})-[:HAS_BRD]->(b:BRD) "
            "RETURN max(b.version) AS max_version",
            repo_id=repo_id,
        )
        prev = rows[0].get("max_version") if rows else None
        return (prev or 0) + 1

    def _write_html(self, repo_id: str, version: int, html: str) -> Path:
        repo_dir = self.output_dir / "brd" / _slugify(repo_id)
        repo_dir.mkdir(parents=True, exist_ok=True)
        path = repo_dir / f"v{version}.html"
        path.write_text(html, encoding="utf-8")
        return path

    def save(
        self,
        *,
        repo_id: str,
        html: str,
        judge_report: JudgeReport,
        attempt_history: list[AttemptRecord],
        model: str,
        strategy: Strategy,
        token_usage: dict[str, int],
    ) -> BRDResult:
        version = self._next_version(repo_id)
        path = self._write_html(repo_id, version, html)
        brd_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)

        self.client.run(
            """
            MATCH (r:Repository {slug: $repo_id})
            CREATE (b:BRD {
                id: $id,
                repo_id: $repo_id,
                version: $version,
                html: $html,
                rating: $rating,
                weighted_score: $weighted_score,
                dimensions: $dimensions,
                attempts: $attempts,
                attempt_history: $attempt_history,
                model: $model,
                strategy: $strategy,
                token_usage: $token_usage,
                created_at: $created_at
            })
            CREATE (r)-[:HAS_BRD]->(b)
            """,
            id=brd_id,
            repo_id=repo_id,
            version=version,
            html=html,
            rating=judge_report.rating.value,
            weighted_score=judge_report.weighted_score,
            dimensions=json.dumps({d.value: s.model_dump() for d, s in judge_report.dimensions.items()}),
            attempts=len(attempt_history),
            attempt_history=json.dumps([a.model_dump() for a in attempt_history]),
            model=model,
            strategy=strategy.value,
            token_usage=json.dumps(token_usage),
            created_at=created_at.isoformat(),
        )

        return BRDResult(
            brd_id=brd_id,
            repo_id=repo_id,
            version=version,
            rating=judge_report.rating,
            weighted_score=judge_report.weighted_score,
            attempts=len(attempt_history),
            attempt_history=attempt_history,
            model=model,
            strategy=strategy,
            html_path=str(path),
            created_at=created_at,
            token_usage=token_usage,
        )

    def get_latest(self, repo_id: str) -> dict | None:
        rows = self.client.run(
            """
            MATCH (r:Repository {slug: $repo_id})-[:HAS_BRD]->(b:BRD)
            RETURN b ORDER BY b.version DESC LIMIT 1
            """,
            repo_id=repo_id,
        )
        return rows[0]["b"] if rows else None

    def list_versions(self, repo_id: str) -> list[dict]:
        return self.client.run(
            """
            MATCH (r:Repository {slug: $repo_id})-[:HAS_BRD]->(b:BRD)
            RETURN b.id AS id, b.version AS version, b.rating AS rating,
                   b.attempts AS attempts, b.created_at AS created_at
            ORDER BY b.version DESC
            """,
            repo_id=repo_id,
        )

    def get_html(self, brd_id: str) -> str | None:
        rows = self.client.run(
            "MATCH (b:BRD {id: $id}) RETURN b.html AS html",
            id=brd_id,
        )
        return rows[0]["html"] if rows else None
```

- [ ] **Step 5: Run tests to verify pass**

```bash
uv run pytest tests/brd/test_storage.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add src/code_context_graph/brd/storage.py tests/brd/test_storage.py tests/brd/conftest.py
git commit -m "brd: add storage layer for versioned :BRD nodes and HTML files"
```

---

## Task 4: Renderer — Markdown to self-contained HTML

**Files:**
- Create: `src/code_context_graph/brd/renderer.py`
- Test: `tests/brd/test_renderer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/brd/test_renderer.py
import re

from code_context_graph.brd.schema import (
    BRD, BRDSection, Requirement, Strategy,
)
from code_context_graph.brd.renderer import render_html


def _sample_brd() -> BRD:
    return BRD(
        sections=[
            BRDSection(
                title="Executive Summary",
                body_markdown="A **bold** summary.\n\n- bullet 1\n- bullet 2",
                requirements=[],
            ),
            BRDSection(
                title="Functional Requirements",
                body_markdown="Core features:",
                requirements=[
                    Requirement(id="FR-1", text="System SHALL authenticate users."),
                    Requirement(id="FR-2", text="System SHALL log all auth events."),
                ],
            ),
        ],
        evidence_map={"FR-1": ["Function:src/auth.py:login"]},
        repo_id="acme-app",
        model="claude-opus-4-7[1m]",
        strategy=Strategy.single_shot,
    )


def test_render_produces_self_contained_html():
    html = render_html(_sample_brd())
    assert html.startswith("<!DOCTYPE html>")
    # no external assets
    assert 'src="http' not in html
    assert 'href="http' not in html or 'href="https://' in html  # only allow anchors in content if any
    assert "<link " not in html
    assert "<script" not in html
    # inline style block present
    assert "<style>" in html


def test_render_includes_all_sections_and_requirements():
    html = render_html(_sample_brd())
    assert "Executive Summary" in html
    assert "Functional Requirements" in html
    assert "<strong>bold</strong>" in html  # markdown converted
    assert "FR-1" in html and "FR-2" in html
    assert "System SHALL authenticate users." in html


def test_render_escapes_html_in_user_content():
    brd = _sample_brd()
    brd.sections[0].body_markdown = "Watch out for <script>alert(1)</script>"
    html = render_html(brd)
    assert "<script>alert(1)</script>" not in html  # raw script must not survive
    assert "&lt;script&gt;" in html or "&lt;script&gt;alert" in html


def test_render_evidence_map_section():
    html = render_html(_sample_brd())
    assert "Evidence" in html
    assert "Function:src/auth.py:login" in html
```

- [ ] **Step 2: Run to verify fail**

```bash
uv run pytest tests/brd/test_renderer.py -v
```

Expected: ImportError.

- [ ] **Step 3: Add markdown deps**

In `pyproject.toml` `[project].dependencies`, add:

```
"markdown-it-py>=3.0",
"mdit-py-plugins>=0.4",
"bleach>=6.1",
```

Then:

```bash
uv sync
```

- [ ] **Step 4: Implement renderer**

```python
# src/code_context_graph/brd/renderer.py
from __future__ import annotations

import html as html_lib

import bleach
from markdown_it import MarkdownIt

from code_context_graph.brd.schema import BRD, BRDSection


_MD = MarkdownIt("commonmark", {"breaks": True, "html": False})

_ALLOWED_TAGS = [
    "p", "strong", "em", "code", "pre", "ul", "ol", "li",
    "h1", "h2", "h3", "h4", "blockquote", "hr", "br", "table",
    "thead", "tbody", "tr", "td", "th", "a",
]
_ALLOWED_ATTRS = {"a": ["href", "title"]}

_INLINE_CSS = """
:root { color-scheme: light dark; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
       max-width: 880px; margin: 2rem auto; padding: 0 1rem;
       line-height: 1.55; color: #1f2328; background: #fff; }
h1, h2 { border-bottom: 1px solid #d0d7de; padding-bottom: .3em; }
h1 { font-size: 2rem; } h2 { font-size: 1.5rem; margin-top: 2.5rem; }
h3 { font-size: 1.2rem; margin-top: 2rem; }
code { background: #f6f8fa; padding: 0.2em 0.4em; border-radius: 4px; }
.requirement { background: #f6f8fa; border-left: 3px solid #0969da;
              padding: 0.6em 0.9em; margin: 0.5em 0; border-radius: 4px; }
.requirement .id { font-weight: 600; color: #0969da; margin-right: 0.5em; }
.evidence-table { width: 100%; border-collapse: collapse; margin-top: 1em; }
.evidence-table th, .evidence-table td {
    border: 1px solid #d0d7de; padding: 0.4em 0.6em; text-align: left;
}
"""


def _section_to_html(section: BRDSection) -> str:
    body_md = section.body_markdown or ""
    rendered = _MD.render(body_md)
    safe_body = bleach.clean(rendered, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS, strip=False)
    parts = [f"<h2>{html_lib.escape(section.title)}</h2>", safe_body]
    for req in section.requirements:
        parts.append(
            f'<div class="requirement"><span class="id">{html_lib.escape(req.id)}</span>'
            f"{html_lib.escape(req.text)}</div>"
        )
    return "\n".join(parts)


def _evidence_to_html(evidence_map: dict[str, list[str]]) -> str:
    if not evidence_map:
        return ""
    rows = []
    for req_id, refs in evidence_map.items():
        joined = ", ".join(html_lib.escape(r) for r in refs)
        rows.append(f"<tr><td>{html_lib.escape(req_id)}</td><td>{joined}</td></tr>")
    return (
        "<h2>Evidence</h2>"
        '<table class="evidence-table">'
        "<thead><tr><th>Requirement</th><th>Grounded in</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def render_html(brd: BRD, *, title: str | None = None) -> str:
    doc_title = title or f"BRD — {brd.repo_id}"
    sections_html = "\n".join(_section_to_html(s) for s in brd.sections)
    evidence_html = _evidence_to_html(brd.evidence_map)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        f"<title>{html_lib.escape(doc_title)}</title>"
        f"<style>{_INLINE_CSS}</style></head><body>"
        f"<h1>{html_lib.escape(doc_title)}</h1>"
        f"{sections_html}{evidence_html}"
        "</body></html>"
    )
```

- [ ] **Step 5: Run to verify pass**

```bash
uv run pytest tests/brd/test_renderer.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add src/code_context_graph/brd/renderer.py tests/brd/test_renderer.py pyproject.toml uv.lock
git commit -m "brd: add markdown->HTML renderer with content sanitization"
```

---

## Task 5: ContextBuilder — graph summary + centrality ranking

**Files:**
- Create: `src/code_context_graph/brd/context_builder.py`
- Test: `tests/brd/test_context_builder.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/brd/test_context_builder.py
from pathlib import Path

from code_context_graph.brd.context_builder import (
    ContextBuilder, GraphSummary, RankedFile,
)


def test_build_graph_summary_pulls_entities_and_top_relationships(fake_client):
    fake_client.script(
        # entities query
        [
            {"qualified_name": "src/a.py:foo", "kind": "Function",
             "file_path": "src/a.py", "signature": "foo()", "docstring": "Does foo.",
             "semantic_layer": "domain_model", "semantic_summary": "Foo handler"},
            {"qualified_name": "src/b.py:Bar", "kind": "Class",
             "file_path": "src/b.py", "signature": "class Bar", "docstring": None,
             "semantic_layer": "data_access", "semantic_summary": None},
        ],
        # relationship counts
        [
            {"rel_type": "CALLS", "count": 42},
            {"rel_type": "IMPORTS", "count": 17},
        ],
        # repo metadata
        [
            {"slug": "acme-app", "files_parsed": 25, "entities": 80,
             "relationships": 200, "url": "git@x/acme", "ingested_at": "2026-05-01"},
        ],
    )
    builder = ContextBuilder(fake_client)
    summary = builder.build_graph_summary("acme-app")
    assert isinstance(summary, GraphSummary)
    assert summary.repo_id == "acme-app"
    assert summary.files_parsed == 25
    assert len(summary.top_entities) == 2
    assert summary.relationship_counts["CALLS"] == 42


def test_rank_files_by_centrality(fake_client):
    fake_client.script(
        [
            {"file_path": "src/a.py", "centrality": 30},
            {"file_path": "src/b.py", "centrality": 12},
            {"file_path": "src/c.py", "centrality": 1},
        ],
    )
    builder = ContextBuilder(fake_client)
    ranked = builder.rank_files("acme-app")
    assert [r.file_path for r in ranked] == ["src/a.py", "src/b.py", "src/c.py"]
    assert isinstance(ranked[0], RankedFile)
    assert ranked[0].centrality == 30
```

- [ ] **Step 2: Run to verify fail**

```bash
uv run pytest tests/brd/test_context_builder.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement first slice of ContextBuilder**

```python
# src/code_context_graph/brd/context_builder.py
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RankedFile:
    file_path: str
    centrality: int


@dataclass
class GraphSummary:
    repo_id: str
    files_parsed: int
    entities: int
    relationships: int
    url: str | None
    ingested_at: str | None
    top_entities: list[dict]
    relationship_counts: dict[str, int]


@dataclass
class PromptContext:
    repo_id: str
    summary_text: str   # rendered string for the prompt
    files: list[tuple[str, str]]  # (relative_path, source)
    strategy: str       # "single_shot" | "map_reduce"
    clusters: list[list[str]] | None  # for map_reduce, list of clusters (each = list of file paths)
    estimated_tokens: int


class ContextBuilder:
    """Build the prompt context for the BRD generator from the Neo4j graph + source on disk."""

    def __init__(self, client, *, single_shot_budget: int | None = None,
                 max_cluster_depth: int | None = None) -> None:
        self.client = client
        self.single_shot_budget = single_shot_budget or int(
            os.getenv("BRD_SINGLE_SHOT_TOKEN_BUDGET", "800000")
        )
        self.max_cluster_depth = max_cluster_depth or int(
            os.getenv("BRD_MAX_CLUSTER_DEPTH", "4")
        )

    def build_graph_summary(self, repo_id: str) -> GraphSummary:
        entities = self.client.run(
            """
            MATCH (e:CodeEntity {repo: $repo_id})
            WHERE e.kind IN ['Class','Function','Method','Module']
            OPTIONAL MATCH (e)-[r]-()
            WITH e, count(r) AS degree
            RETURN e.qualified_name AS qualified_name,
                   e.kind AS kind,
                   e.file_path AS file_path,
                   e.signature AS signature,
                   e.docstring AS docstring,
                   e.semantic_layer AS semantic_layer,
                   e.semantic_summary AS semantic_summary
            ORDER BY degree DESC
            LIMIT 200
            """,
            repo_id=repo_id,
        )
        rel_counts = self.client.run(
            """
            MATCH (s:CodeEntity {repo: $repo_id})-[r]->(t)
            RETURN type(r) AS rel_type, count(r) AS count
            ORDER BY count DESC
            """,
            repo_id=repo_id,
        )
        repo_meta = self.client.run(
            """
            MATCH (r:Repository {slug: $repo_id})
            RETURN r.slug AS slug, r.files_parsed AS files_parsed,
                   r.entities AS entities, r.relationships AS relationships,
                   r.url AS url, r.ingested_at AS ingested_at
            """,
            repo_id=repo_id,
        )
        meta = repo_meta[0] if repo_meta else {}
        return GraphSummary(
            repo_id=repo_id,
            files_parsed=int(meta.get("files_parsed") or 0),
            entities=int(meta.get("entities") or 0),
            relationships=int(meta.get("relationships") or 0),
            url=meta.get("url"),
            ingested_at=meta.get("ingested_at"),
            top_entities=entities,
            relationship_counts={row["rel_type"]: row["count"] for row in rel_counts},
        )

    def rank_files(self, repo_id: str) -> list[RankedFile]:
        rows = self.client.run(
            """
            MATCH (e:CodeEntity {repo: $repo_id})
            WHERE e.file_path IS NOT NULL
            OPTIONAL MATCH (e)-[r]-()
            WITH e.file_path AS file_path, sum(case when r is null then 0 else 1 end) AS centrality
            RETURN file_path, centrality
            ORDER BY centrality DESC
            """,
            repo_id=repo_id,
        )
        return [RankedFile(file_path=row["file_path"], centrality=int(row["centrality"])) for row in rows]
```

- [ ] **Step 4: Run tests to verify pass**

```bash
uv run pytest tests/brd/test_context_builder.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/code_context_graph/brd/context_builder.py tests/brd/test_context_builder.py
git commit -m "brd: add graph summary and centrality ranking in ContextBuilder"
```

---

## Task 6: ContextBuilder — source loading, token estimation, strategy decision

**Files:**
- Modify: `src/code_context_graph/brd/context_builder.py`
- Modify: `tests/brd/test_context_builder.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/brd/test_context_builder.py`:

```python
def test_single_shot_when_under_budget(fake_client, tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("def foo(): pass\n")
    fake_client.script(
        # build_graph_summary entities
        [{"qualified_name": "src/a.py:foo", "kind": "Function",
          "file_path": "src/a.py", "signature": "foo()", "docstring": "",
          "semantic_layer": None, "semantic_summary": None}],
        # build_graph_summary rel_counts
        [],
        # build_graph_summary repo_meta
        [{"slug": "acme", "files_parsed": 1, "entities": 1,
          "relationships": 0, "url": None, "ingested_at": None}],
        # rank_files
        [{"file_path": "src/a.py", "centrality": 1}],
    )
    builder = ContextBuilder(fake_client, single_shot_budget=10_000_000)
    ctx = builder.build("acme", repo_path=tmp_path)
    assert ctx.strategy == "single_shot"
    assert ctx.files == [("src/a.py", "def foo(): pass\n")]
    assert ctx.clusters is None
    assert "src/a.py:foo" in ctx.summary_text


def test_map_reduce_when_over_budget(fake_client, tmp_path):
    big = "x = '" + "y" * 100_000 + "'\n"
    for sub in ("auth", "billing", "analytics"):
        d = tmp_path / "src" / sub
        d.mkdir(parents=True)
        (d / "mod.py").write_text(big)
    fake_client.script(
        # build_graph_summary entities
        [],
        # build_graph_summary rel_counts
        [],
        # build_graph_summary repo_meta
        [{"slug": "acme", "files_parsed": 3, "entities": 3,
          "relationships": 0, "url": None, "ingested_at": None}],
        # rank_files
        [{"file_path": f"src/{s}/mod.py", "centrality": 1} for s in ("auth","billing","analytics")],
    )
    # tiny budget forces map-reduce
    builder = ContextBuilder(fake_client, single_shot_budget=1000)
    ctx = builder.build("acme", repo_path=tmp_path)
    assert ctx.strategy == "map_reduce"
    assert ctx.clusters is not None
    assert len(ctx.clusters) >= 2
    # each cluster has at least one file
    assert all(len(c) > 0 for c in ctx.clusters)


def test_estimate_tokens_chars_over_four():
    # 4 chars ~= 1 token heuristic
    from code_context_graph.brd.context_builder import estimate_tokens
    assert estimate_tokens("a" * 400) == 100
    assert estimate_tokens("") == 0
```

- [ ] **Step 2: Run to verify fail**

```bash
uv run pytest tests/brd/test_context_builder.py -v
```

Expected: 3 new tests fail with AttributeError / missing `build` method.

- [ ] **Step 3: Extend ContextBuilder**

Append to `src/code_context_graph/brd/context_builder.py`:

```python
def estimate_tokens(text: str) -> int:
    """Char-over-4 heuristic; cheap and good enough for budget gating."""
    return len(text) // 4


def _format_summary_text(summary: GraphSummary) -> str:
    lines: list[str] = []
    lines.append(f"# Repository: {summary.repo_id}")
    if summary.url:
        lines.append(f"Source: {summary.url}")
    lines.append(
        f"Files parsed: {summary.files_parsed} | "
        f"Entities: {summary.entities} | Relationships: {summary.relationships}"
    )
    lines.append("\n## Relationship distribution")
    for rel, count in summary.relationship_counts.items():
        lines.append(f"- {rel}: {count}")
    lines.append("\n## Top entities (by graph centrality)")
    for e in summary.top_entities:
        sig = e.get("signature") or ""
        layer = e.get("semantic_layer") or ""
        summary_str = e.get("semantic_summary") or ""
        lines.append(
            f"- [{e['kind']}] {e['qualified_name']}"
            + (f" — {layer}" if layer else "")
            + (f" — {summary_str}" if summary_str else "")
        )
    return "\n".join(lines)


class ContextBuilder(ContextBuilder):  # type: ignore[no-redef]
    pass


def _load_source(repo_path: Path, file_path: str) -> str | None:
    full = (repo_path / file_path)
    try:
        return full.read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, IsADirectoryError, PermissionError):
        return None


def _cluster_by_top_dir(file_paths: list[str], depth: int = 1) -> dict[str, list[str]]:
    clusters: dict[str, list[str]] = {}
    for fp in file_paths:
        parts = fp.split("/")
        key = "/".join(parts[:depth]) if len(parts) > depth else parts[0]
        clusters.setdefault(key, []).append(fp)
    return clusters


def _split_oversized_cluster(
    files: list[tuple[str, str]],
    budget: int,
    current_depth: int,
    max_depth: int,
) -> list[list[tuple[str, str]]]:
    """If a cluster overruns the budget, recursively split by deeper directory."""
    total = sum(estimate_tokens(src) for _, src in files)
    if total <= budget or current_depth >= max_depth:
        return [files]
    paths = [fp for fp, _ in files]
    sub = _cluster_by_top_dir(paths, depth=current_depth + 1)
    result: list[list[tuple[str, str]]] = []
    source_by_path = dict(files)
    for cluster_files in sub.values():
        sub_pairs = [(p, source_by_path[p]) for p in cluster_files]
        result.extend(_split_oversized_cluster(sub_pairs, budget, current_depth + 1, max_depth))
    return result


def _attach_build_method() -> None:
    def build(self, repo_id: str, *, repo_path: Path, force_map_reduce: bool = False) -> PromptContext:
        summary = self.build_graph_summary(repo_id)
        summary_text = _format_summary_text(summary)
        ranked = self.rank_files(repo_id)
        files: list[tuple[str, str]] = []
        for rf in ranked:
            src = _load_source(repo_path, rf.file_path)
            if src is not None:
                files.append((rf.file_path, src))
        source_tokens = sum(estimate_tokens(src) for _, src in files)
        total = estimate_tokens(summary_text) + source_tokens
        if not force_map_reduce and total <= self.single_shot_budget:
            return PromptContext(
                repo_id=repo_id, summary_text=summary_text, files=files,
                strategy="single_shot", clusters=None, estimated_tokens=total,
            )
        # map-reduce
        clusters_map = _cluster_by_top_dir([fp for fp, _ in files], depth=1)
        source_by_path = dict(files)
        all_clusters: list[list[str]] = []
        for cluster_files in clusters_map.values():
            sub_pairs = [(p, source_by_path[p]) for p in cluster_files]
            for split in _split_oversized_cluster(
                sub_pairs, self.single_shot_budget, current_depth=1, max_depth=self.max_cluster_depth
            ):
                all_clusters.append([p for p, _ in split])
        return PromptContext(
            repo_id=repo_id, summary_text=summary_text, files=files,
            strategy="map_reduce", clusters=all_clusters, estimated_tokens=total,
        )

    ContextBuilder.build = build  # type: ignore[attr-defined]


_attach_build_method()
```

Note: the redefinition trick keeps the diff additive. If preferred, integrate `build` directly into the class body in the same edit.

- [ ] **Step 4: Run tests to verify pass**

```bash
uv run pytest tests/brd/test_context_builder.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/code_context_graph/brd/context_builder.py tests/brd/test_context_builder.py
git commit -m "brd: add source loading, token estimation, and map-reduce strategy"
```

---

## Task 7: Generator — single-shot Claude call

**Files:**
- Create: `src/code_context_graph/brd/generator.py`
- Test: `tests/brd/test_generator.py`

- [ ] **Step 1: Add fake Anthropic fixture**

Append to `tests/brd/conftest.py`:

```python
class FakeAnthropic:
    """Records messages.create() calls and returns scripted text responses."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._responses: list[str] = []
        self.messages = self

    def script(self, *texts: str) -> None:
        self._responses = list(texts)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        text = self._responses.pop(0) if self._responses else "{}"

        class _Block:
            def __init__(self, t: str) -> None:
                self.text = t

        class _Response:
            def __init__(self, t: str) -> None:
                self.content = [_Block(t)]
                self.usage = type("U", (), {"input_tokens": 10, "output_tokens": 5,
                                            "cache_read_input_tokens": 0,
                                            "cache_creation_input_tokens": 0})()

        return _Response(text)


@pytest.fixture
def fake_anthropic() -> FakeAnthropic:
    return FakeAnthropic()
```

- [ ] **Step 2: Write the failing test**

```python
# tests/brd/test_generator.py
import json
from pathlib import Path

from code_context_graph.brd.context_builder import PromptContext
from code_context_graph.brd.generator import Generator
from code_context_graph.brd.schema import BRD, Strategy


def _ctx() -> PromptContext:
    return PromptContext(
        repo_id="acme",
        summary_text="# acme\n- top entity",
        files=[("src/a.py", "def foo(): pass\n")],
        strategy="single_shot",
        clusters=None,
        estimated_tokens=100,
    )


def _scripted_brd_json() -> str:
    return json.dumps({
        "sections": [
            {"title": "Executive Summary", "body_markdown": "Summary text.", "requirements": []},
            {"title": "Functional Requirements", "body_markdown": "Features:",
             "requirements": [{"id": "FR-1", "text": "Authenticate users."}]},
        ],
        "evidence_map": {"FR-1": ["src/a.py"]},
    })


def test_single_shot_returns_brd(fake_anthropic):
    fake_anthropic.script(_scripted_brd_json())
    gen = Generator(anthropic=fake_anthropic, model="claude-opus-4-7[1m]")
    brd = gen.generate(_ctx())
    assert isinstance(brd, BRD)
    assert brd.strategy == Strategy.single_shot
    assert any(s.title == "Functional Requirements" for s in brd.sections)
    assert brd.evidence_map["FR-1"] == ["src/a.py"]


def test_single_shot_passes_revision_guidance(fake_anthropic):
    fake_anthropic.script(_scripted_brd_json())
    gen = Generator(anthropic=fake_anthropic, model="claude-opus-4-7[1m]")
    gen.generate(_ctx(), revision_guidance="Address FR-2 missing.")
    sent = fake_anthropic.calls[-1]
    # The user message should mention prior judge feedback
    user_text = sent["messages"][-1]["content"]
    assert "Address FR-2 missing." in user_text
```

- [ ] **Step 3: Run to verify fail**

```bash
uv run pytest tests/brd/test_generator.py -v
```

Expected: ImportError.

- [ ] **Step 4: Implement generator (single-shot path)**

```python
# src/code_context_graph/brd/generator.py
from __future__ import annotations

import json
import os
from typing import Any

from code_context_graph.brd.context_builder import PromptContext
from code_context_graph.brd.schema import BRD, BRDSection, Requirement, Strategy


SYSTEM_PROMPT = """You are a senior business analyst writing a Business Requirements
Document (BRD) for an engineering team. You will be given:
1. A graph summary of the codebase (entities, layers, relationships).
2. The full source tree of the repository, file by file.
3. Optionally, judge feedback from a prior attempt that you must address.

Produce a comprehensive BRD with these 11 sections (use exactly these titles):
- Executive Summary
- Business Objectives
- Scope
- Stakeholders
- Functional Requirements
- Non-functional Requirements
- Data & Integrations
- Assumptions
- Constraints
- Risks
- Success Metrics

Rules:
- Every functional requirement MUST be grounded in real entities or files from the
  provided context. Use IDs of the form FR-1, FR-2, ... and NFR-1, NFR-2, ...
- Provide an `evidence_map` linking each requirement ID to the graph entities or
  file paths that justified it. Use real entity qualified_names or paths from the input.
- Do NOT invent classes, functions, or files that aren't in the input.
- Return ONLY valid JSON, no markdown fences, matching this schema:
  {"sections":[{"title": str, "body_markdown": str,
                 "requirements":[{"id": str, "text": str}, ...]}, ...],
   "evidence_map": {req_id: [entity_or_path, ...], ...}}
"""


def _build_user_message(ctx: PromptContext, revision_guidance: str | None) -> str:
    parts: list[str] = []
    parts.append("## Graph summary\n")
    parts.append(ctx.summary_text)
    parts.append("\n\n## Source files\n")
    for path, src in ctx.files:
        parts.append(f"\n### {path}\n```\n{src}\n```\n")
    if revision_guidance:
        parts.append("\n\n## Judge feedback to address in this revision\n")
        parts.append(revision_guidance)
    return "".join(parts)


def _parse_brd(json_text: str, *, repo_id: str, model: str, strategy: Strategy) -> BRD:
    data = json.loads(json_text)
    sections = [
        BRDSection(
            title=s["title"],
            body_markdown=s.get("body_markdown", ""),
            requirements=[Requirement(**r) for r in s.get("requirements", [])],
        )
        for s in data["sections"]
    ]
    return BRD(
        sections=sections,
        evidence_map=data.get("evidence_map", {}),
        repo_id=repo_id,
        model=model,
        strategy=strategy,
    )


class Generator:
    def __init__(self, anthropic, model: str | None = None,
                 max_tokens: int = 16_000) -> None:
        self.anthropic = anthropic
        self.model = model or os.getenv("BRD_MODEL", "claude-opus-4-7") + "[1m]"
        self.max_tokens = max_tokens
        self.token_usage = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}

    def _call(self, user_message: str) -> str:
        response = self.anthropic.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        usage = getattr(response, "usage", None)
        if usage is not None:
            self.token_usage["input"] += getattr(usage, "input_tokens", 0) or 0
            self.token_usage["output"] += getattr(usage, "output_tokens", 0) or 0
            self.token_usage["cache_read"] += getattr(usage, "cache_read_input_tokens", 0) or 0
            self.token_usage["cache_write"] += getattr(usage, "cache_creation_input_tokens", 0) or 0
        return response.content[0].text

    def generate(self, ctx: PromptContext, *, revision_guidance: str | None = None) -> BRD:
        if ctx.strategy == "single_shot":
            text = self._call(_build_user_message(ctx, revision_guidance))
            return _parse_brd(text, repo_id=ctx.repo_id, model=self.model,
                              strategy=Strategy.single_shot)
        # map_reduce path implemented in Task 8
        raise NotImplementedError("map_reduce path added in Task 8")
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/brd/test_generator.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add src/code_context_graph/brd/generator.py tests/brd/test_generator.py tests/brd/conftest.py
git commit -m "brd: add single-shot BRD generator"
```

---

## Task 8: Generator — map-reduce path

**Files:**
- Modify: `src/code_context_graph/brd/generator.py`
- Modify: `tests/brd/test_generator.py`

- [ ] **Step 1: Add failing test**

Append to `tests/brd/test_generator.py`:

```python
def _scripted_sub_brd_json(cluster_id: str) -> str:
    import json as _j
    return _j.dumps({
        "sections": [
            {"title": "Executive Summary", "body_markdown": f"Cluster {cluster_id}", "requirements": []},
            {"title": "Functional Requirements", "body_markdown": "",
             "requirements": [{"id": f"FR-{cluster_id}", "text": f"Feature {cluster_id}."}]},
        ],
        "evidence_map": {f"FR-{cluster_id}": [f"src/{cluster_id}/mod.py"]},
    })


def test_map_reduce_runs_one_call_per_cluster_then_reduce(fake_anthropic):
    map_a = _scripted_sub_brd_json("a")
    map_b = _scripted_sub_brd_json("b")
    # reduce returns merged BRD
    reduce_out = _scripted_brd_json().replace(
        '"FR-1"', '"FR-a"'
    )
    fake_anthropic.script(map_a, map_b, reduce_out)
    ctx = PromptContext(
        repo_id="acme",
        summary_text="summary",
        files=[("src/a/mod.py", "code a"), ("src/b/mod.py", "code b")],
        strategy="map_reduce",
        clusters=[["src/a/mod.py"], ["src/b/mod.py"]],
        estimated_tokens=10,
    )
    gen = Generator(anthropic=fake_anthropic, model="claude-opus-4-7[1m]")
    brd = gen.generate(ctx)
    assert brd.strategy == Strategy.map_reduce
    assert len(fake_anthropic.calls) == 3  # 2 maps + 1 reduce
```

- [ ] **Step 2: Run to verify fail**

```bash
uv run pytest tests/brd/test_generator.py::test_map_reduce_runs_one_call_per_cluster_then_reduce -v
```

Expected: NotImplementedError.

- [ ] **Step 3: Implement map and reduce**

Replace the `generate` body and add helpers in `generator.py`:

```python
REDUCE_SYSTEM = """You are merging multiple cluster-scoped BRDs into a single
unified BRD for the whole repository. Deduplicate requirements, reconcile
contradictions, prefer the more specific wording, and keep the 11-section
structure exactly. Preserve every entity reference (do not drop evidence pointers).
Return JSON in the same schema as a single BRD."""


def _build_cluster_message(ctx: PromptContext, cluster_files: list[str],
                           revision_guidance: str | None) -> str:
    source_by_path = dict(ctx.files)
    parts: list[str] = ["## Graph summary\n", ctx.summary_text,
                        f"\n\n## Cluster files ({len(cluster_files)} files)\n"]
    for path in cluster_files:
        src = source_by_path.get(path, "")
        parts.append(f"\n### {path}\n```\n{src}\n```\n")
    if revision_guidance:
        parts.append("\n\n## Judge feedback to address\n")
        parts.append(revision_guidance)
    return "".join(parts)


def _build_reduce_message(sub_brds: list[BRD], revision_guidance: str | None) -> str:
    payload = [b.model_dump(mode="json") for b in sub_brds]
    text = "## Sub-BRDs to merge\n```json\n" + json.dumps(payload) + "\n```"
    if revision_guidance:
        text += "\n\n## Judge feedback to address\n" + revision_guidance
    return text
```

Then change `Generator.generate`:

```python
def generate(self, ctx: PromptContext, *, revision_guidance: str | None = None) -> BRD:
    if ctx.strategy == "single_shot":
        text = self._call(_build_user_message(ctx, revision_guidance))
        return _parse_brd(text, repo_id=ctx.repo_id, model=self.model,
                          strategy=Strategy.single_shot)
    if not ctx.clusters:
        raise ValueError("map_reduce strategy requires clusters")
    # map
    sub_brds: list[BRD] = []
    for cluster_files in ctx.clusters:
        try:
            cluster_text = self._call(_build_cluster_message(ctx, cluster_files, revision_guidance))
            sub_brds.append(_parse_brd(cluster_text, repo_id=ctx.repo_id, model=self.model,
                                        strategy=Strategy.map_reduce))
        except Exception:
            # one failed cluster becomes a partial; reduce sees the gap
            sub_brds.append(BRD(
                sections=[BRDSection(title="Executive Summary",
                                     body_markdown="<cluster failed to generate; partial>",
                                     requirements=[])],
                evidence_map={}, repo_id=ctx.repo_id, model=self.model,
                strategy=Strategy.map_reduce,
            ))
    # reduce
    response = self.anthropic.messages.create(
        model=self.model,
        max_tokens=self.max_tokens,
        system=REDUCE_SYSTEM,
        messages=[{"role": "user", "content": _build_reduce_message(sub_brds, revision_guidance)}],
    )
    usage = getattr(response, "usage", None)
    if usage is not None:
        self.token_usage["input"] += getattr(usage, "input_tokens", 0) or 0
        self.token_usage["output"] += getattr(usage, "output_tokens", 0) or 0
    return _parse_brd(response.content[0].text, repo_id=ctx.repo_id,
                      model=self.model, strategy=Strategy.map_reduce)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/brd/test_generator.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/code_context_graph/brd/generator.py tests/brd/test_generator.py
git commit -m "brd: add map-reduce path with cluster failure transparency"
```

---

## Task 9: Judge — hard groundedness check

**Files:**
- Create: `src/code_context_graph/brd/judge.py`
- Test: `tests/brd/test_judge.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/brd/test_judge.py
from code_context_graph.brd.context_builder import PromptContext
from code_context_graph.brd.schema import BRD, BRDSection, Requirement, Strategy


def _ctx_with_entities(entities: list[str]) -> PromptContext:
    summary = "Top entities:\n" + "\n".join(f"- {e}" for e in entities)
    return PromptContext(
        repo_id="acme", summary_text=summary,
        files=[("src/a.py", "def foo(): pass")],
        strategy="single_shot", clusters=None, estimated_tokens=10,
    )


def _brd_with_evidence(evidence: dict[str, list[str]]) -> BRD:
    return BRD(
        sections=[BRDSection(title="Executive Summary", body_markdown="", requirements=[])],
        evidence_map=evidence,
        repo_id="acme", model="m", strategy=Strategy.single_shot,
    )


def test_groundedness_passes_when_all_entities_in_context():
    from code_context_graph.brd.judge import groundedness_failures
    ctx = _ctx_with_entities(["src/a.py:foo"])
    brd = _brd_with_evidence({"FR-1": ["src/a.py:foo", "src/a.py"]})
    assert groundedness_failures(brd, ctx) == []


def test_groundedness_flags_unknown_entity():
    from code_context_graph.brd.judge import groundedness_failures
    ctx = _ctx_with_entities(["src/a.py:foo"])
    brd = _brd_with_evidence({"FR-1": ["src/a.py:foo", "src/ghost.py:made_up"]})
    failures = groundedness_failures(brd, ctx)
    assert "src/ghost.py:made_up" in failures
    assert "src/a.py:foo" not in failures
```

- [ ] **Step 2: Run to verify fail**

```bash
uv run pytest tests/brd/test_judge.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement groundedness**

```python
# src/code_context_graph/brd/judge.py
from __future__ import annotations

from code_context_graph.brd.context_builder import PromptContext
from code_context_graph.brd.schema import BRD


def _known_references(ctx: PromptContext) -> set[str]:
    known: set[str] = set()
    known.update(path for path, _ in ctx.files)
    # also extract qualified_name-looking tokens from summary_text
    for line in ctx.summary_text.splitlines():
        for token in line.split():
            token = token.strip("`-•,()[]")
            if ":" in token or "/" in token:
                known.add(token)
    return known


def groundedness_failures(brd: BRD, ctx: PromptContext) -> list[str]:
    """Return any references in the evidence_map that do not appear in the context."""
    known = _known_references(ctx)
    failures: list[str] = []
    for refs in brd.evidence_map.values():
        for ref in refs:
            if ref not in known:
                failures.append(ref)
    return failures
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/brd/test_judge.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/code_context_graph/brd/judge.py tests/brd/test_judge.py
git commit -m "brd: add hard groundedness check for evidence references"
```

---

## Task 10: Judge — rubric scoring and rating

**Files:**
- Modify: `src/code_context_graph/brd/judge.py`
- Modify: `tests/brd/test_judge.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/brd/test_judge.py`:

```python
import json as _json

from code_context_graph.brd.schema import Dimension, JudgeReport, Rating


def _judge_payload(c=5, a=5, cl=5, co=5, ac=5, feedback=None):
    return _json.dumps({
        "dimensions": {
            "completeness":  {"score": c,  "rationale": "ok"},
            "accuracy":      {"score": a,  "rationale": "ok"},
            "clarity":       {"score": cl, "rationale": "ok"},
            "consistency":   {"score": co, "rationale": "ok"},
            "actionability": {"score": ac, "rationale": "ok"},
        },
        "feedback": feedback or [],
    })


def test_judge_high_rating(fake_anthropic):
    fake_anthropic.script(_judge_payload(5, 5, 4, 4, 4))
    from code_context_graph.brd.judge import Judge
    j = Judge(anthropic=fake_anthropic, model="claude-opus-4-7[1m]")
    report = j.evaluate(_brd_with_evidence({"FR-1": ["src/a.py:foo"]}),
                        _ctx_with_entities(["src/a.py:foo"]))
    assert report.rating == Rating.high
    assert abs(report.weighted_score - (5*0.25 + 5*0.30 + 4*0.15 + 4*0.15 + 4*0.15)) < 0.001


def test_judge_medium_rating(fake_anthropic):
    fake_anthropic.script(_judge_payload(4, 3, 3, 3, 3))
    from code_context_graph.brd.judge import Judge
    j = Judge(anthropic=fake_anthropic, model="claude-opus-4-7[1m]")
    report = j.evaluate(_brd_with_evidence({"FR-1": ["src/a.py:foo"]}),
                        _ctx_with_entities(["src/a.py:foo"]))
    assert report.rating == Rating.medium


def test_judge_low_when_dimension_below_two(fake_anthropic):
    fake_anthropic.script(_judge_payload(5, 5, 1, 5, 5))
    from code_context_graph.brd.judge import Judge
    j = Judge(anthropic=fake_anthropic, model="claude-opus-4-7[1m]")
    report = j.evaluate(_brd_with_evidence({"FR-1": ["src/a.py:foo"]}),
                        _ctx_with_entities(["src/a.py:foo"]))
    assert report.rating == Rating.low


def test_groundedness_failure_forces_accuracy_le_two(fake_anthropic):
    fake_anthropic.script(_judge_payload(5, 5, 5, 5, 5))
    from code_context_graph.brd.judge import Judge
    j = Judge(anthropic=fake_anthropic, model="claude-opus-4-7[1m]")
    brd = _brd_with_evidence({"FR-1": ["src/ghost.py:nope"]})
    report = j.evaluate(brd, _ctx_with_entities(["src/a.py:foo"]))
    assert report.dimensions[Dimension.accuracy].score <= 2
    assert "src/ghost.py:nope" in report.groundedness_failures
    assert report.rating in (Rating.medium, Rating.low)
```

- [ ] **Step 2: Run to verify fail**

```bash
uv run pytest tests/brd/test_judge.py -v
```

Expected: 4 new tests fail with ImportError.

- [ ] **Step 3: Add Judge class**

Append to `src/code_context_graph/brd/judge.py`:

```python
import json
import os
from typing import Any

from code_context_graph.brd.schema import (
    Dimension, DimensionScore, FeedbackItem, JudgeReport, Rating,
)


WEIGHTS = {
    Dimension.completeness:  0.25,
    Dimension.accuracy:      0.30,
    Dimension.clarity:       0.15,
    Dimension.consistency:   0.15,
    Dimension.actionability: 0.15,
}


JUDGE_SYSTEM = """You are evaluating a Business Requirements Document (BRD) generated
from a codebase. Score it on five dimensions, each 1-5, with a brief rationale:
- completeness: are all 11 BRD sections present and substantive?
- accuracy: does every claim tie to real entities/code from the context? No hallucinations.
- clarity: readable, unambiguous, no undefined jargon
- consistency: no contradictions across sections; scope matches requirements
- actionability: requirements are testable; success metrics concrete

Also return a `feedback` list of items the next attempt should address. Each item:
{"dimension": one of the five names, "severity": "low"|"medium"|"high",
 "suggestion": string, "target_section": string}

Return ONLY JSON, no markdown fences:
{"dimensions": {"<name>": {"score": int, "rationale": str}, ...},
 "feedback": [...]}
"""


def _rate(weighted: float, dims: dict[Dimension, DimensionScore]) -> Rating:
    if weighted >= 4.2 and all(d.score >= 3 for d in dims.values()):
        return Rating.high
    if weighted >= 3.2 and all(d.score >= 2 for d in dims.values()):
        return Rating.medium
    return Rating.low


class Judge:
    def __init__(self, anthropic, model: str | None = None,
                 max_tokens: int = 4000) -> None:
        self.anthropic = anthropic
        self.model = model or os.getenv("BRD_MODEL", "claude-opus-4-7") + "[1m]"
        self.max_tokens = max_tokens

    def _call_judge(self, brd, ctx) -> dict[str, Any]:
        user = (
            "## Context (graph summary)\n" + ctx.summary_text +
            "\n\n## BRD under review\n```json\n" + brd.model_dump_json() + "\n```"
        )
        response = self.anthropic.messages.create(
            model=self.model, max_tokens=self.max_tokens,
            system=JUDGE_SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        return json.loads(response.content[0].text)

    def evaluate(self, brd, ctx) -> JudgeReport:
        # 1. hard groundedness pre-check
        failures = groundedness_failures(brd, ctx)
        # 2. LLM rubric
        raw = self._call_judge(brd, ctx)
        dims: dict[Dimension, DimensionScore] = {}
        for name, item in raw["dimensions"].items():
            dim = Dimension(name)
            dims[dim] = DimensionScore(score=int(item["score"]), rationale=item.get("rationale", ""))
        # 3. apply groundedness floor
        if failures:
            current = dims[Dimension.accuracy]
            if current.score > 2:
                dims[Dimension.accuracy] = DimensionScore(
                    score=2,
                    rationale=current.rationale + f" [forced to 2 by hallucinated refs: {failures}]",
                )
        # 4. weighted score + rating
        weighted = sum(dims[d].score * w for d, w in WEIGHTS.items())
        rating = _rate(weighted, dims)
        feedback = [FeedbackItem(**item) for item in raw.get("feedback", [])]
        return JudgeReport(
            dimensions=dims, weighted_score=weighted, rating=rating,
            feedback=feedback, groundedness_failures=failures,
        )
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/brd/test_judge.py -v
```

Expected: 6 passed total (2 from Task 9 + 4 new).

- [ ] **Step 5: Commit**

```bash
git add src/code_context_graph/brd/judge.py tests/brd/test_judge.py
git commit -m "brd: add rubric judge with weighted score and groundedness floor"
```

---

## Task 11: Pipeline — orchestrator with retry loop

**Files:**
- Create: `src/code_context_graph/brd/pipeline.py`
- Test: `tests/brd/test_pipeline.py`
- Modify: `src/code_context_graph/brd/__init__.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/brd/test_pipeline.py
from pathlib import Path

from code_context_graph.brd.context_builder import PromptContext
from code_context_graph.brd.pipeline import generate_brd
from code_context_graph.brd.schema import (
    BRD, BRDSection, Dimension, DimensionScore, JudgeReport, Rating, Strategy,
)


class _StubGenerator:
    def __init__(self, brds: list[BRD]) -> None:
        self.brds = brds
        self.calls: list[str | None] = []
        self.token_usage = {"input": 1, "output": 1, "cache_read": 0, "cache_write": 0}

    def generate(self, ctx, *, revision_guidance=None):
        self.calls.append(revision_guidance)
        return self.brds.pop(0)


class _StubJudge:
    def __init__(self, reports: list[JudgeReport]) -> None:
        self.reports = reports

    def evaluate(self, brd, ctx):
        return self.reports.pop(0)


def _brd() -> BRD:
    return BRD(
        sections=[BRDSection(title="Executive Summary", body_markdown="", requirements=[])],
        evidence_map={}, repo_id="acme", model="m", strategy=Strategy.single_shot,
    )


def _report(rating: Rating, score: float = 3.0) -> JudgeReport:
    return JudgeReport(
        dimensions={d: DimensionScore(score=3, rationale="") for d in Dimension},
        weighted_score=score, rating=rating, feedback=[], groundedness_failures=[],
    )


def test_pipeline_short_circuits_on_high(fake_client, tmp_path):
    # context_builder.build is stubbed via dependency injection below
    ctx = PromptContext(repo_id="acme", summary_text="s", files=[],
                        strategy="single_shot", clusters=None, estimated_tokens=10)
    gen = _StubGenerator([_brd()])
    judge = _StubJudge([_report(Rating.high, 4.5)])
    result = generate_brd(
        repo_id="acme", repo_path=tmp_path,
        client=fake_client, context=ctx, generator=gen, judge=judge,
        max_retries=2,
    )
    assert result.rating == Rating.high
    assert result.attempts == 1
    assert gen.calls == [None]


def test_pipeline_retries_with_feedback_then_succeeds(fake_client, tmp_path):
    ctx = PromptContext(repo_id="acme", summary_text="s", files=[],
                        strategy="single_shot", clusters=None, estimated_tokens=10)
    gen = _StubGenerator([_brd(), _brd(), _brd()])
    judge = _StubJudge([_report(Rating.low, 2.0), _report(Rating.medium, 3.5),
                        _report(Rating.high, 4.5)])
    result = generate_brd(
        repo_id="acme", repo_path=tmp_path,
        client=fake_client, context=ctx, generator=gen, judge=judge,
        max_retries=2,
    )
    assert result.attempts == 3
    assert result.rating == Rating.high
    assert gen.calls[0] is None
    assert gen.calls[1] is not None and gen.calls[2] is not None


def test_pipeline_returns_best_attempt_after_max_retries(fake_client, tmp_path):
    ctx = PromptContext(repo_id="acme", summary_text="s", files=[],
                        strategy="single_shot", clusters=None, estimated_tokens=10)
    gen = _StubGenerator([_brd(), _brd(), _brd()])
    judge = _StubJudge([_report(Rating.low, 2.0), _report(Rating.medium, 3.5),
                        _report(Rating.low, 2.5)])
    result = generate_brd(
        repo_id="acme", repo_path=tmp_path,
        client=fake_client, context=ctx, generator=gen, judge=judge,
        max_retries=2,
    )
    assert result.attempts == 3
    # best attempt is #2 (medium, 3.5)
    assert result.rating == Rating.medium
    assert result.weighted_score == 3.5
```

- [ ] **Step 2: Run to verify fail**

```bash
uv run pytest tests/brd/test_pipeline.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement pipeline**

```python
# src/code_context_graph/brd/pipeline.py
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from code_context_graph.brd.context_builder import ContextBuilder, PromptContext
from code_context_graph.brd.generator import Generator
from code_context_graph.brd.judge import Judge
from code_context_graph.brd.renderer import render_html
from code_context_graph.brd.storage import BRDStorage
from code_context_graph.brd.schema import (
    AttemptRecord, BRD, BRDResult, JudgeReport, Rating, Strategy,
)


def _feedback_to_text(report: JudgeReport) -> str:
    lines = [f"Prior rating: {report.rating.value} (weighted score {report.weighted_score:.2f})."]
    if report.groundedness_failures:
        lines.append("Hallucinated references to remove: " + ", ".join(report.groundedness_failures))
    for item in report.feedback:
        lines.append(
            f"[{item.dimension.value}/{item.severity}] {item.target_section}: {item.suggestion}"
        )
    return "\n".join(lines)


def generate_brd(
    repo_id: str,
    *,
    repo_path: Path | str | None = None,
    max_retries: Optional[int] = None,
    force_map_reduce: bool = False,
    client=None,
    context: PromptContext | None = None,
    generator: Generator | None = None,
    judge: Judge | None = None,
    storage: BRDStorage | None = None,
) -> BRDResult:
    if max_retries is None:
        max_retries = int(os.getenv("BRD_MAX_RETRIES", "2"))

    if context is None:
        if client is None:
            from code_context_graph.neo4j_client import Neo4jClient
            client = Neo4jClient()
        if repo_path is None:
            from code_context_graph.repo_manager import RepoManager
            repo = RepoManager(client).get(repo_id)
            if repo is None or not repo.get("local_path"):
                raise ValueError(f"Repo {repo_id} not registered or missing local_path")
            repo_path = Path(repo["local_path"])
        builder = ContextBuilder(client)
        context = builder.build(repo_id, repo_path=Path(repo_path),
                                force_map_reduce=force_map_reduce)

    if generator is None:
        from anthropic import Anthropic
        generator = Generator(anthropic=Anthropic())
    if judge is None:
        from anthropic import Anthropic
        judge = Judge(anthropic=Anthropic())
    if storage is None and client is not None:
        storage = BRDStorage(client)

    attempts: list[AttemptRecord] = []
    best: tuple[BRD, JudgeReport] | None = None
    feedback_text: str | None = None

    for attempt_no in range(1, max_retries + 2):
        brd = generator.generate(context, revision_guidance=feedback_text)
        report = judge.evaluate(brd, context)
        attempts.append(AttemptRecord(
            attempt=attempt_no, rating=report.rating,
            weighted_score=report.weighted_score, feedback=report.feedback,
        ))
        if best is None or report.weighted_score > best[1].weighted_score:
            best = (brd, report)
        if report.rating == Rating.high:
            break
        feedback_text = _feedback_to_text(report)

    final_brd, final_report = best
    html = render_html(final_brd)

    if storage is not None:
        return storage.save(
            repo_id=repo_id, html=html, judge_report=final_report,
            attempt_history=attempts, model=generator.model,
            strategy=Strategy(context.strategy),
            token_usage=generator.token_usage,
        )

    # storage-less path (tests)
    from datetime import datetime, timezone
    import uuid
    return BRDResult(
        brd_id=str(uuid.uuid4()), repo_id=repo_id, version=1,
        rating=final_report.rating, weighted_score=final_report.weighted_score,
        attempts=len(attempts), attempt_history=attempts,
        model=generator.model, strategy=Strategy(context.strategy),
        html_path="(not saved)", created_at=datetime.now(timezone.utc),
        token_usage=generator.token_usage,
    )
```

- [ ] **Step 4: Update package exports**

Replace `src/code_context_graph/brd/__init__.py`:

```python
"""BRD (Business Requirements Document) generator.

Public entrypoint: `generate_brd(repo_id, *, max_retries=2, force_map_reduce=False)`.
"""
from code_context_graph.brd.pipeline import generate_brd
from code_context_graph.brd.schema import BRDResult, Rating, Strategy

__all__ = ["generate_brd", "BRDResult", "Rating", "Strategy"]
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/brd/test_pipeline.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add src/code_context_graph/brd/pipeline.py src/code_context_graph/brd/__init__.py tests/brd/test_pipeline.py
git commit -m "brd: add pipeline orchestrator with feedback-driven retry loop"
```

---

## Task 12: CLI — `ccg brd` command

**Files:**
- Modify: `src/code_context_graph/cli.py`

- [ ] **Step 1: Add the command**

Append to `src/code_context_graph/cli.py`:

```python
@app.command()
def brd(
    repo: str = typer.Argument(..., help="Repo slug (or local path) to generate a BRD for."),
    max_retries: int = typer.Option(None, "--max-retries", help="Override BRD_MAX_RETRIES."),
    force_map_reduce: bool = typer.Option(False, "--force-map-reduce",
                                          help="Use map-reduce even if repo fits in context."),
    output_dir: str = typer.Option(None, "--output-dir", help="Override BRD_OUTPUT_DIR."),
    open_browser: bool = typer.Option(False, "--open", help="Open the BRD in the default browser."),
) -> None:
    """Generate a Business Requirements Document for an ingested repo."""
    import os
    import webbrowser
    from code_context_graph.brd import generate_brd
    from code_context_graph.brd.schema import Rating

    if output_dir:
        os.environ["BRD_OUTPUT_DIR"] = output_dir

    console.print(f"[cyan]Generating BRD for {repo}...[/cyan]")
    result = generate_brd(
        repo_id=repo,
        max_retries=max_retries,
        force_map_reduce=force_map_reduce,
    )
    badge = {"high": "green", "medium": "yellow", "low": "red"}[result.rating.value]
    console.print(
        f"[{badge}]Rating: {result.rating.value}[/{badge}] "
        f"(weighted score {result.weighted_score:.2f}, "
        f"{result.attempts} attempt(s), strategy {result.strategy.value})"
    )
    console.print(f"HTML written to: {result.html_path}")
    if open_browser:
        webbrowser.open(f"file://{result.html_path}")
    if result.rating == Rating.high:
        raise typer.Exit(0)
    if result.rating == Rating.medium:
        raise typer.Exit(1)
    raise typer.Exit(2)
```

- [ ] **Step 2: Smoke test the CLI parses**

```bash
uv run ccg brd --help
```

Expected: help text shown; no traceback.

- [ ] **Step 3: Commit**

```bash
git add src/code_context_graph/cli.py
git commit -m "brd: add 'ccg brd' CLI command"
```

---

## Task 13: API — endpoints with background task

**Files:**
- Modify: `src/code_context_graph/api.py`
- Test: `tests/brd/test_api.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/brd/test_api.py
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def test_post_brd_starts_background_task():
    from code_context_graph.api import app

    with patch("code_context_graph.api.generate_brd") as gen_mock:
        gen_mock.return_value = MagicMock(
            brd_id="abc", rating=MagicMock(value="high"), attempts=1,
            weighted_score=4.5, version=1, html_path="/tmp/x.html",
            created_at=MagicMock(isoformat=lambda: "2026-01-01T00:00:00Z"),
            strategy=MagicMock(value="single_shot"),
        )
        client = TestClient(app)
        resp = client.post("/api/repos/acme-app/brd")
        assert resp.status_code in (200, 202)
        data = resp.json()
        assert "status" in data


def test_get_brd_returns_latest_summary():
    from code_context_graph.api import app, get_client

    with patch.object(get_client(), "run") as run_mock:
        run_mock.return_value = [{
            "b": {
                "id": "abc", "version": 2, "rating": "high",
                "attempts": 1, "weighted_score": 4.5,
                "created_at": "2026-01-01T00:00:00Z",
                "model": "claude-opus-4-7[1m]", "strategy": "single_shot",
                "attempt_history": "[]",
            }
        }]
        client = TestClient(app)
        resp = client.get("/api/repos/acme-app/brd")
        assert resp.status_code == 200
        assert resp.json()["rating"] == "high"


def test_get_brd_html_returns_html_content_type():
    from code_context_graph.api import app, get_client

    with patch.object(get_client(), "run") as run_mock:
        run_mock.return_value = [{"html": "<html><body>ok</body></html>"}]
        client = TestClient(app)
        resp = client.get("/api/repos/acme-app/brd/abc-123/html")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/html")
        assert "<body>ok</body>" in resp.text
```

- [ ] **Step 2: Run to verify fail**

```bash
uv run pytest tests/brd/test_api.py -v
```

Expected: 404 or ImportError-style failures.

- [ ] **Step 3: Add endpoints**

Append imports near the top of `src/code_context_graph/api.py`:

```python
import json as _json
from datetime import datetime
from fastapi import BackgroundTasks
from fastapi.responses import HTMLResponse
from code_context_graph.brd import generate_brd
from code_context_graph.brd.storage import BRDStorage
```

Append in-memory job tracker (module level, near `_client`):

```python
_brd_jobs: dict[str, dict] = {}  # repo_id -> latest job status
```

Append endpoints:

```python
def _run_brd_job(repo_id: str, max_retries: int | None, force_map_reduce: bool) -> None:
    try:
        result = generate_brd(
            repo_id=repo_id,
            max_retries=max_retries,
            force_map_reduce=force_map_reduce,
            client=get_client(),
        )
        _brd_jobs[repo_id] = {
            "status": "done", "brd_id": result.brd_id, "rating": result.rating.value,
            "weighted_score": result.weighted_score, "attempts": result.attempts,
            "version": result.version, "html_path": result.html_path,
            "created_at": result.created_at.isoformat(),
            "strategy": result.strategy.value,
        }
    except Exception as exc:
        _brd_jobs[repo_id] = {"status": "error", "error": str(exc)}


@app.post("/api/repos/{repo_id}/brd")
def start_brd(
    repo_id: str,
    background: BackgroundTasks,
    max_retries: int | None = Query(None),
    force_map_reduce: bool = Query(False),
) -> dict:
    _brd_jobs[repo_id] = {"status": "running"}
    background.add_task(_run_brd_job, repo_id, max_retries, force_map_reduce)
    return {"status": "running", "repo_id": repo_id}


@app.get("/api/repos/{repo_id}/brd")
def get_brd(repo_id: str, all: bool = Query(False)) -> dict | list:
    client = get_client()
    storage = BRDStorage(client)
    if all:
        return storage.list_versions(repo_id)
    rows = client.run(
        "MATCH (r:Repository {slug: $repo_id})-[:HAS_BRD]->(b:BRD) "
        "RETURN b ORDER BY b.version DESC LIMIT 1",
        repo_id=repo_id,
    )
    if not rows:
        # surface in-flight job status if no BRD persisted yet
        job = _brd_jobs.get(repo_id)
        if job:
            return job
        raise HTTPException(404, f"No BRD for {repo_id}")
    b = rows[0]["b"]
    attempt_history = b.get("attempt_history")
    if isinstance(attempt_history, str):
        attempt_history = _json.loads(attempt_history)
    return {
        "id": b.get("id"), "version": b.get("version"),
        "rating": b.get("rating"), "weighted_score": b.get("weighted_score"),
        "attempts": b.get("attempts"), "model": b.get("model"),
        "strategy": b.get("strategy"), "created_at": b.get("created_at"),
        "attempt_history": attempt_history,
    }


@app.get("/api/repos/{repo_id}/brd/{brd_id}/html", response_class=HTMLResponse)
def get_brd_html(repo_id: str, brd_id: str) -> HTMLResponse:
    client = get_client()
    rows = client.run("MATCH (b:BRD {id: $id}) RETURN b.html AS html", id=brd_id)
    if not rows:
        raise HTTPException(404, f"BRD not found: {brd_id}")
    return HTMLResponse(rows[0]["html"])
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/brd/test_api.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/code_context_graph/api.py tests/brd/test_api.py
git commit -m "brd: add API endpoints (POST/GET BRD, GET HTML)"
```

---

## Task 14: Web UI — BRDPanel with sandboxed iframe

**Files:**
- Create: `web/src/components/BRDPanel.tsx`
- Modify: the repo detail page (locate during this task — likely `web/src/app/repo/[slug]/page.tsx` or `web/src/app/repo/[...slug]/page.tsx`)

- [ ] **Step 1: Identify the repo detail page**

```bash
grep -l "EntityPanel\|AskCodebasePanel\|GraphView" /Users/chamindawijayasundara/Documents/applying_agents_2026/source_graphs_v1.0/web/src/app/repo
```

Pick the file that imports the existing panels and renders the repo detail layout. Note its path.

- [ ] **Step 2: Create `BRDPanel.tsx`**

```tsx
// web/src/components/BRDPanel.tsx
"use client";

import { useEffect, useState } from "react";

type AttemptRecord = {
  attempt: number;
  rating: "high" | "medium" | "low";
  weighted_score: number;
  feedback: Array<{
    dimension: string;
    severity: string;
    suggestion: string;
    target_section: string;
  }>;
};

type BRDSummary = {
  id: string;
  version: number;
  rating: "high" | "medium" | "low";
  weighted_score: number;
  attempts: number;
  strategy: string;
  created_at: string;
  attempt_history: AttemptRecord[];
};

type JobStatus =
  | { status: "running" }
  | { status: "error"; error: string }
  | { status: "done"; brd_id: string; rating: string; version: number };

const ratingColor: Record<string, string> = {
  high: "bg-green-100 text-green-800 border-green-300",
  medium: "bg-yellow-100 text-yellow-800 border-yellow-300",
  low: "bg-red-100 text-red-800 border-red-300",
};

export default function BRDPanel({ repoId }: { repoId: string }) {
  const [latest, setLatest] = useState<BRDSummary | JobStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [showFeedback, setShowFeedback] = useState(false);

  const fetchLatest = async () => {
    const res = await fetch(`/api/repos/${encodeURIComponent(repoId)}/brd`);
    if (res.status === 404) {
      setLatest(null);
      return;
    }
    setLatest(await res.json());
  };

  useEffect(() => {
    fetchLatest();
  }, [repoId]);

  // poll while running
  useEffect(() => {
    if (latest && (latest as any).status === "running") {
      const t = setInterval(fetchLatest, 3000);
      return () => clearInterval(t);
    }
  }, [latest]);

  const onGenerate = async () => {
    setLoading(true);
    await fetch(`/api/repos/${encodeURIComponent(repoId)}/brd`, { method: "POST" });
    await fetchLatest();
    setLoading(false);
  };

  const isJob = latest && "status" in (latest as any);
  const summary = !isJob ? (latest as BRDSummary | null) : null;

  return (
    <div className="border rounded-lg p-4 bg-white">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold">Business Requirements Document</h2>
        <button
          onClick={onGenerate}
          disabled={loading || (isJob && (latest as any).status === "running")}
          className="px-3 py-1.5 rounded bg-blue-600 text-white text-sm disabled:opacity-50"
        >
          {summary ? "Re-generate" : "Generate BRD"}
        </button>
      </div>

      {!latest && <p className="text-sm text-gray-500">No BRD yet. Click "Generate BRD" to create one.</p>}

      {isJob && (latest as any).status === "running" && (
        <p className="text-sm text-gray-600">Generating BRD… this can take a minute or two.</p>
      )}
      {isJob && (latest as any).status === "error" && (
        <p className="text-sm text-red-600">Error: {(latest as any).error}</p>
      )}

      {summary && (
        <>
          <div className="flex gap-3 items-center text-sm mb-3">
            <span className={`px-2 py-0.5 rounded border ${ratingColor[summary.rating]}`}>
              {summary.rating.toUpperCase()}
            </span>
            <span className="text-gray-600">v{summary.version}</span>
            <span className="text-gray-600">{summary.attempts} attempt(s)</span>
            <span className="text-gray-600">strategy: {summary.strategy}</span>
            <span className="text-gray-600">score: {summary.weighted_score.toFixed(2)}</span>
          </div>

          <iframe
            title="BRD"
            srcDoc={undefined /* loaded via src below */}
            src={`/api/repos/${encodeURIComponent(repoId)}/brd/${summary.id}/html`}
            sandbox="allow-same-origin"
            className="w-full h-[70vh] border rounded"
          />

          <button
            onClick={() => setShowFeedback((v) => !v)}
            className="mt-3 text-sm text-blue-600 underline"
          >
            {showFeedback ? "Hide" : "Show"} judge report ({summary.attempts} attempt(s))
          </button>
          {showFeedback && (
            <div className="mt-2 text-sm space-y-3">
              {summary.attempt_history.map((a) => (
                <div key={a.attempt} className="border rounded p-2">
                  <div className="font-medium">
                    Attempt {a.attempt} — {a.rating} (score {a.weighted_score.toFixed(2)})
                  </div>
                  {a.feedback.length === 0 ? (
                    <div className="text-gray-500">No feedback.</div>
                  ) : (
                    <ul className="list-disc pl-5">
                      {a.feedback.map((f, i) => (
                        <li key={i}>
                          <strong>[{f.dimension}/{f.severity}]</strong> {f.target_section}: {f.suggestion}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Mount `BRDPanel` on the repo detail page**

In the page identified in Step 1, import and render:

```tsx
import BRDPanel from "@/components/BRDPanel";
// ... and inside the layout, alongside other panels:
<BRDPanel repoId={slug} />
```

(Use whichever variable holds the repo slug in that file.)

- [ ] **Step 4: Verify the frontend builds**

```bash
cd web && npm run build && cd ..
```

Expected: build succeeds, no TS errors.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/BRDPanel.tsx web/src/app/repo
git commit -m "brd: add BRDPanel UI with sandboxed iframe and judge report"
```

---

## Task 15: End-to-end cassette test

**Files:**
- Create: `tests/brd/test_e2e.py`
- Create: `tests/brd/cassettes/sample_repo_run.json`

- [ ] **Step 1: Write the cassette**

Record one good generation + judge pair as JSON. Use the existing `demo/` or `source_code_to_analyse/` repo (whichever is smaller). Manually craft a realistic response (do not hit the real API in CI).

```json
// tests/brd/cassettes/sample_repo_run.json
{
  "generator_responses": [
    "{\"sections\":[{\"title\":\"Executive Summary\",\"body_markdown\":\"...\",\"requirements\":[]},{\"title\":\"Business Objectives\",\"body_markdown\":\"...\",\"requirements\":[]},{\"title\":\"Scope\",\"body_markdown\":\"...\",\"requirements\":[]},{\"title\":\"Stakeholders\",\"body_markdown\":\"...\",\"requirements\":[]},{\"title\":\"Functional Requirements\",\"body_markdown\":\"\",\"requirements\":[{\"id\":\"FR-1\",\"text\":\"...\"}]},{\"title\":\"Non-functional Requirements\",\"body_markdown\":\"\",\"requirements\":[]},{\"title\":\"Data & Integrations\",\"body_markdown\":\"\",\"requirements\":[]},{\"title\":\"Assumptions\",\"body_markdown\":\"\",\"requirements\":[]},{\"title\":\"Constraints\",\"body_markdown\":\"\",\"requirements\":[]},{\"title\":\"Risks\",\"body_markdown\":\"\",\"requirements\":[]},{\"title\":\"Success Metrics\",\"body_markdown\":\"\",\"requirements\":[]}],\"evidence_map\":{\"FR-1\":[\"src/code_context_graph/parser.py\"]}}"
  ],
  "judge_responses": [
    "{\"dimensions\":{\"completeness\":{\"score\":5,\"rationale\":\"all 11\"},\"accuracy\":{\"score\":5,\"rationale\":\"grounded\"},\"clarity\":{\"score\":4,\"rationale\":\"ok\"},\"consistency\":{\"score\":4,\"rationale\":\"ok\"},\"actionability\":{\"score\":4,\"rationale\":\"ok\"}},\"feedback\":[]}"
  ]
}
```

- [ ] **Step 2: Write the e2e test**

```python
# tests/brd/test_e2e.py
import json
from pathlib import Path

import pytest

from code_context_graph.brd.context_builder import PromptContext
from code_context_graph.brd.generator import Generator
from code_context_graph.brd.judge import Judge
from code_context_graph.brd.pipeline import generate_brd
from code_context_graph.brd.schema import Rating, Strategy


CASSETTE = Path(__file__).parent / "cassettes" / "sample_repo_run.json"


class _Cassette:
    def __init__(self, payload: dict) -> None:
        self._gen = list(payload["generator_responses"])
        self._jud = list(payload["judge_responses"])
        self.messages = self
        self._mode = "gen"

    def create(self, **kwargs):
        text = self._gen.pop(0) if self._mode == "gen" else self._jud.pop(0)
        self._mode = "jud" if self._mode == "gen" else "gen"

        class B:  # block
            def __init__(self, t): self.text = t
        class U:
            input_tokens = 1; output_tokens = 1
            cache_read_input_tokens = 0; cache_creation_input_tokens = 0
        class R:
            def __init__(self, t): self.content = [B(t)]; self.usage = U()
        return R(text)


@pytest.mark.skipif(not CASSETTE.exists(), reason="cassette missing")
def test_end_to_end_with_cassette(fake_client, tmp_path):
    payload = json.loads(CASSETTE.read_text())
    cassette = _Cassette(payload)

    # Hand-built context bypassing the graph queries
    ctx = PromptContext(
        repo_id="sample", summary_text="Top entities:\n- src/code_context_graph/parser.py",
        files=[("src/code_context_graph/parser.py", "x = 1")],
        strategy="single_shot", clusters=None, estimated_tokens=10,
    )
    gen = Generator(anthropic=cassette, model="claude-opus-4-7[1m]")
    judge = Judge(anthropic=cassette, model="claude-opus-4-7[1m]")

    fake_client.script([{"max_version": None}])
    result = generate_brd(
        repo_id="sample", client=fake_client, context=ctx,
        generator=gen, judge=judge, max_retries=2,
    )
    assert result.rating == Rating.high
    assert result.strategy == Strategy.single_shot
    assert Path(result.html_path).exists()
```

Note: the in-memory storage in tests writes to `BRD_OUTPUT_DIR`; set it via fixture or env in conftest if needed. If `BRDStorage` is using cwd's `./brd_output`, override by passing a `storage=BRDStorage(fake_client, output_dir=tmp_path)` into `generate_brd`.

- [ ] **Step 3: Run the test**

```bash
uv run pytest tests/brd/test_e2e.py -v
```

Expected: 1 passed.

- [ ] **Step 4: Run the full suite**

```bash
uv run pytest tests/brd -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/brd/test_e2e.py tests/brd/cassettes
git commit -m "brd: add end-to-end cassette test"
```

---

## Task 16: Manual verification

- [ ] **Step 1: Start Neo4j and the backend**

```bash
docker compose up -d neo4j
uv run ccg serve --port 8000 &
```

- [ ] **Step 2: Ingest the demo repo**

```bash
uv run ccg ingest source_code_to_analyse --clear
```

- [ ] **Step 3: Generate a BRD via CLI**

```bash
uv run ccg brd <slug> --open
```

Expected: a BRD is generated, a rating is shown, and the HTML opens in the default browser. The file under `./brd_output/brd/<slug>/v1.html` is self-contained (open in browser without a server).

- [ ] **Step 4: Generate a BRD via Web UI**

Start the frontend:

```bash
cd web && npm run dev
```

Open the repo detail page in the browser. Click "Generate BRD". Verify:
- Spinner / running state appears.
- After completion, the rating badge, version, attempts, and strategy are shown.
- The HTML renders in the sandboxed iframe.
- "Show judge report" expands to show per-attempt dimension scores and feedback.

- [ ] **Step 5: Trim memory file / commit any small fixups**

```bash
git status
```

Expected: clean working tree (no uncommitted changes). If any fixups were needed, commit them with descriptive messages.

---

## Self-Review

**Spec coverage check:**
- Standard BRD with 11 sections — Task 2 (schema), Task 7 (system prompt enumerates titles).
- Single-shot vs map-reduce strategy — Tasks 5, 6, 8.
- Hierarchical map-reduce with recursive cluster splitting — Task 6 (`_split_oversized_cluster`).
- Claude Opus 4.7 1M context — `BRD_MODEL` + `[1m]` suffix in Generator/Judge.
- LLM-as-judge with 5-dimension weighted rubric — Task 10.
- Hard groundedness check forcing Accuracy ≤ 2 — Tasks 9 & 10.
- Max 2 retries with feedback — Task 11 (`max_retries+1` total attempts, feedback rendered to text).
- Best-attempt return after max retries — Task 11 test.
- HTML output self-contained with inlined CSS — Task 4.
- Stored in Neo4j as versioned `:BRD` node — Task 3.
- HAS_BRD relationship to Repository — Task 3.
- CLI surface (`ccg brd`) — Task 12.
- API endpoints (POST, GET, GET ?all=true, GET HTML) — Task 13.
- Background-task pattern — Task 13.
- Web UI button + sandboxed iframe + judge report panel — Task 14.
- Error handling: cluster failure transparency — Task 8 (try/except per cluster).
- Configuration via env — Task 1.
- E2E cassette test — Task 15.

No gaps identified.

**Placeholder scan:** No "TBD", "TODO", "implement later", or generic "add error handling" instructions present. Every step contains either real code, an exact command with expected output, or a precise file/line action.

**Type consistency:** `BRD`, `BRDSection`, `Requirement`, `JudgeReport`, `Dimension`, `DimensionScore`, `FeedbackItem`, `Rating`, `Strategy`, `AttemptRecord`, `BRDResult`, `PromptContext`, `GraphSummary`, `RankedFile` — all defined once and referenced consistently across tasks. Method names (`generate`, `evaluate`, `build`, `save`, `get_latest`, `list_versions`, `get_html`) are used consistently throughout.

---
