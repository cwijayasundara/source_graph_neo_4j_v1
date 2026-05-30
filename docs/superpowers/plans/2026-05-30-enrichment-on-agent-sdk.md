# Enrichment on the Agent SDK + Model Selection — Implementation Plan (Plan 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate Claude model selection into one `.env`-driven resolver (no hardcoded model strings), then migrate semantic enrichment off Gemini onto the graph-navigating Agent SDK foundation (centrality-ordered, fan-out, loop-until-exhausted), and delete the now-unused Gemini client.

**Architecture:** A tiny `agent/models.py` resolver (`resolve_model(role)`: per-role env override → global `CODE_GRAPH_LLM_MODEL` → hardcoded Claude default) becomes the single source of truth for which Claude model each path uses. Enrichment becomes an `agent/enricher.py` that, per repo, pulls untagged entities by graph centrality and runs one `AgentRunner` call per entity (with the graph tools, so tags are grounded in usage), writing tags back and looping until none remain. The old `enrichment.py` and `gemini_llm.py` are removed.

**Tech Stack:** Python ≥3.11, `claude-agent-sdk==0.2.87`, Pydantic, pytest (+ `pytest-asyncio`, already configured).

**Prereqs / context:** This builds on Plan 1 (merged). The foundation already provides `agent/deps.py` (`GraphDeps`), `agent/graph_ops.py`, `agent/graph_tools.py` (`build_graph_server`, `GRAPH_TOOL_NAMES`), `agent/harness.py` (`AgentRunner`, `SdkAgentRunner`, and the `fake_runner` fixture in `tests/agent/conftest.py`). The BRD path currently hardcodes its model default at `brd/pipeline.py:86`. Enrichment today is `enrichment.py` (Gemini, capped at 50, serial) invoked only by the CLI `enrich` command (`cli.py:73-84`); `gemini_llm.GeminiMessagesClient` is used ONLY by `enrichment.py`.

**Spec:** `docs/superpowers/specs/2026-05-30-graph-navigated-brd-agent-sdk-design.md` (the "Enrichment" + "Cost & determinism" sections).

> **IMPORTANT runtime note for whoever runs this:** the live `.env` currently has `CODE_GRAPH_LLM_MODEL=gemini-3.5-flash`. After Task 1, that variable is the *global Claude model default* for all paths, so it MUST be changed to a Claude id (e.g. `claude-sonnet-4-6`) or those paths will try to call a Gemini model through the Claude SDK. Task 1 Step 6 updates it. `.env` is gitignored — never commit it.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/code_context_graph/agent/models.py` | `resolve_model(role)` — the single model selector |
| `src/code_context_graph/agent/enrich_schema.py` | `EnrichmentTags` Pydantic model + JSON schema for structured output |
| `src/code_context_graph/agent/enricher.py` | `aenrich()` loop + `enrich_repo_sync()` entry point |
| `src/code_context_graph/brd/pipeline.py` | Route BRD model through `resolve_model("brd")` |
| `src/code_context_graph/cli.py` | `enrich` command → per-repo, agent-based |
| `tests/agent/test_models.py` | resolver precedence tests |
| `tests/agent/test_enricher.py` | enrichment loop tests (fake runner) |
| Deleted | `src/code_context_graph/enrichment.py`, `src/code_context_graph/gemini_llm.py` |

---

## Task 1: (moved to Plan 1.5)

The shared `resolve_model()` selector, the `.env`/`.env.example` model updates, and routing the BRD path through it are now implemented in **Plan 1.5** (`docs/superpowers/plans/2026-05-30-token-economics-advisor.md`, Task 1). This plan **assumes `src/code_context_graph/agent/models.py` already exists** with `resolve_model(role)` supporting the `"enrichment"` role (default `claude-haiku-4-5-20251001`). Execute Plan 1.5 before this plan. No work in this task.

---

## Task 2: Agent-based semantic enricher

**Files:**
- Create: `src/code_context_graph/agent/enrich_schema.py`
- Create: `src/code_context_graph/agent/enricher.py`
- Create: `tests/agent/test_enricher.py`

- [ ] **Step 1: Create the structured-output schema**

Create `src/code_context_graph/agent/enrich_schema.py`:

```python
from __future__ import annotations

from pydantic import BaseModel, Field


class EnrichmentTags(BaseModel):
    """Architectural tags for one entity. Defaults let a sparse/empty model response
    degrade gracefully instead of raising."""
    patterns: list[str] = Field(default_factory=list)
    layer: str = "unknown"
    concepts: list[str] = Field(default_factory=list)
    summary: str = ""


def enrichment_tags_schema() -> dict:
    return EnrichmentTags.model_json_schema()
```

- [ ] **Step 2: Write the failing tests**

Create `tests/agent/test_enricher.py`:

```python
from __future__ import annotations

import pytest

from code_context_graph.agent.deps import GraphDeps
from code_context_graph.agent.enricher import aenrich


@pytest.mark.asyncio
async def test_enriches_one_entity_and_writes_back_then_terminates(seeded, tmp_path, fake_runner):
    # The untagged-entity query returns the same single entity each call; the
    # enricher must enrich it once and terminate (seen-tracking), not loop forever.
    seeded.when(lambda q, p: "semantic_layer IS NULL" in q,
                [{"qualified_name": "pkg.a", "kind": "Function",
                  "signature": "def a()", "file_path": "src/a.py"}])
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=tmp_path)
    fake_runner.script(
        {"patterns": ["Repository"], "layer": "data_access",
         "concepts": ["persistence"], "summary": "Reads records."},
    )
    n = await aenrich(deps, runner=fake_runner, model="m",
                      batch_size=10, max_concurrency=4, max_turns=4)
    assert n == 1
    assert len(fake_runner.calls) == 1
    # a write-back SET was issued for the entity, with the layer set
    writes = [(q, p) for q, p in seeded.calls if "SET e.semantic_layer" in q]
    assert writes and writes[0][1]["layer"] == "data_access"
    assert writes[0][1]["qname"] == "pkg.a"


@pytest.mark.asyncio
async def test_no_untagged_entities_is_zero(seeded, tmp_path, fake_runner):
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=tmp_path)  # no rules -> []
    n = await aenrich(deps, runner=fake_runner, model="m",
                      batch_size=10, max_concurrency=4, max_turns=4)
    assert n == 0
    assert len(fake_runner.calls) == 0


@pytest.mark.asyncio
async def test_empty_model_result_is_a_failure_not_a_write(seeded, tmp_path, fake_runner):
    # runner returns {} (e.g. SDK error path) -> entity NOT counted, NOT written back,
    # so it stays NULL and is retried on a future run.
    seeded.when(lambda q, p: "semantic_layer IS NULL" in q,
                [{"qualified_name": "pkg.b", "kind": "Method",
                  "signature": "", "file_path": "src/b.py"}])
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=tmp_path)
    fake_runner.script({})  # empty result
    n = await aenrich(deps, runner=fake_runner, model="m",
                      batch_size=10, max_concurrency=4, max_turns=4)
    assert n == 0
    assert not any("SET e.semantic_layer" in q for q, _ in seeded.calls)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/agent/test_enricher.py -v`
Expected: FAIL — module not found.

- [ ] **Step 4: Implement the enricher**

Create `src/code_context_graph/agent/enricher.py`:

```python
from __future__ import annotations

import asyncio
import logging

from code_context_graph.agent.deps import GraphDeps
from code_context_graph.agent.enrich_schema import EnrichmentTags, enrichment_tags_schema
from code_context_graph.agent.graph_tools import GRAPH_TOOL_NAMES, build_graph_server
from code_context_graph.agent.harness import AgentRunner

logger = logging.getLogger(__name__)

ENRICH_SYSTEM = """You tag ONE code entity with its architectural role. You have
graph-navigation tools: get_entity, neighbors (CALLS/IMPORTS/CONTAINS/INHERITS),
get_source_slice (reads just this entity's lines). Inspect how the entity is USED —
not just its signature — then emit EnrichmentTags JSON:
- patterns: design patterns it participates in (e.g. Repository, Factory, State Machine)
- layer: one of presentation | business_logic | data_access | infrastructure | orchestration | domain_model
- concepts: domain concepts it represents
- summary: one plain-English sentence of what it does."""

_FETCH_UNTAGGED = """
MATCH (e:CodeEntity {repo: $repo})
WHERE e.kind IN ['Class', 'Function', 'Method', 'Module']
  AND e.semantic_layer IS NULL
OPTIONAL MATCH (e)-[r]-()
WITH e, count(r) AS degree
RETURN e.qualified_name AS qualified_name, e.kind AS kind,
       e.signature AS signature, e.file_path AS file_path
ORDER BY degree DESC
LIMIT $limit
"""

_WRITE_BACK = """
MATCH (e:CodeEntity {repo: $repo, qualified_name: $qname})
SET e.semantic_patterns = $patterns,
    e.semantic_layer = $layer,
    e.semantic_concepts = $concepts,
    e.semantic_summary = $summary
"""


def _enrich_prompt(entity: dict) -> str:
    return (f"Entity: {entity.get('qualified_name')}\n"
            f"Kind: {entity.get('kind')}\n"
            f"File: {entity.get('file_path')}\n"
            f"Signature: {entity.get('signature') or 'N/A'}\n\n"
            "Inspect it via the tools and emit its EnrichmentTags.")


def _fetch_untagged(deps: GraphDeps, limit: int) -> list[dict]:
    return deps.client.run(_FETCH_UNTAGGED, repo=deps.repo_id, limit=limit)


async def _enrich_one(deps, runner, server, model, max_turns, entity, sem) -> bool:
    try:
        async with sem:
            raw = await runner.run_structured(
                system=ENRICH_SYSTEM, prompt=_enrich_prompt(entity),
                server=server, allowed_tools=GRAPH_TOOL_NAMES, model=model,
                max_turns=max_turns, schema=enrichment_tags_schema(),
            )
        if not raw:                       # SDK error path returns {} -> retry next run
            return False
        tags = EnrichmentTags.model_validate(raw)
        deps.client.run(
            _WRITE_BACK, repo=deps.repo_id, qname=entity["qualified_name"],
            patterns=tags.patterns, layer=tags.layer,
            concepts=tags.concepts, summary=tags.summary,
        )
        return True
    except Exception:
        logger.exception("enrichment failed for %s", entity.get("qualified_name"))
        return False


async def aenrich(deps: GraphDeps, *, runner: AgentRunner, model: str,
                  batch_size: int = 20, max_concurrency: int = 6,
                  max_turns: int = 4) -> int:
    """Enrich every untagged entity in the repo, highest graph-centrality first,
    fanning out within each batch and looping until none remain. Returns the count
    successfully tagged."""
    server = build_graph_server(deps)
    sem = asyncio.Semaphore(max_concurrency)
    seen: set[str] = set()
    total = 0
    while True:
        batch = _fetch_untagged(deps, batch_size)
        fresh = [e for e in batch if e.get("qualified_name")
                 and e["qualified_name"] not in seen]
        if not fresh:
            break
        for e in fresh:
            seen.add(e["qualified_name"])
        results = await asyncio.gather(*[
            _enrich_one(deps, runner, server, model, max_turns, e, sem) for e in fresh
        ])
        total += sum(1 for ok in results if ok)
    return total


def enrich_repo_sync(repo_id: str, *, client=None, repo_path=None,
                     model: str | None = None, batch_size: int = 20,
                     max_concurrency: int = 6, max_turns: int = 4) -> int:
    """Sync entry point for the CLI. Resolves deps + model, runs the async loop."""
    from pathlib import Path
    from code_context_graph.agent.harness import SdkAgentRunner
    from code_context_graph.agent.models import resolve_model

    if client is None:
        from code_context_graph.neo4j_client import Neo4jClient
        client = Neo4jClient()
    if repo_path is None:
        from code_context_graph.repo_manager import RepoManager
        repo = RepoManager(client).get(repo_id)
        if repo is None or not repo.get("local_path"):
            raise ValueError(f"Repo {repo_id} not registered or missing local_path")
        repo_path = repo["local_path"]
    model = model or resolve_model("enrichment")
    deps = GraphDeps(client=client, repo_id=repo_id, repo_path=Path(repo_path))
    runner = SdkAgentRunner()
    return asyncio.run(aenrich(deps, runner=runner, model=model,
                               batch_size=batch_size, max_concurrency=max_concurrency,
                               max_turns=max_turns))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/agent/test_enricher.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Run full agent suite**

Run: `uv run pytest tests/agent/ -q`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add src/code_context_graph/agent/enrich_schema.py src/code_context_graph/agent/enricher.py tests/agent/test_enricher.py
git commit -m "feat(agent): graph-navigating semantic enricher (centrality-ordered, fan-out)"
```

---

## Task 3: Wire CLI enrich to the agent enricher; remove the Gemini client

**Files:**
- Modify: `src/code_context_graph/cli.py:73-84` (the `enrich` command)
- Delete: `src/code_context_graph/enrichment.py`, `src/code_context_graph/gemini_llm.py`

- [ ] **Step 1: Update the CLI `enrich` command**

In `src/code_context_graph/cli.py`, the current command is:

```python
@app.command()
def enrich(
    limit: int = typer.Option(50, "--limit", help="Max entities to enrich per run."),
) -> None:
    """Run LLM semantic enrichment on un-tagged entities."""
    from code_context_graph.enrichment import SemanticEnricher
    from code_context_graph.neo4j_client import Neo4jClient

    with Neo4jClient() as client:
        enricher = SemanticEnricher(client)
        count = enricher.enrich_all(limit=limit)
        console.print(f"[green]Enriched {count} entities[/green]")
```

Replace the whole command with (enrichment is now per-repo, using graph context, with no 50-cap — it loops until done):

```python
@app.command()
def enrich(
    repo: str = typer.Argument(..., help="Repo slug to enrich (must be ingested)."),
    batch_size: int = typer.Option(20, "--batch-size",
                                    help="Entities fetched per round (highest centrality first)."),
    max_concurrency: int = typer.Option(6, "--concurrency",
                                        help="Max concurrent enrichment agents."),
) -> None:
    """Tag a repo's entities with architectural roles using the graph-navigating agent."""
    from code_context_graph.agent.enricher import enrich_repo_sync
    from code_context_graph.neo4j_client import Neo4jClient

    with Neo4jClient() as client:
        console.print(f"[cyan]Enriching {repo}...[/cyan]")
        count = enrich_repo_sync(repo, client=client, batch_size=batch_size,
                                 max_concurrency=max_concurrency)
        console.print(f"[green]Enriched {count} entities[/green]")
```

- [ ] **Step 2: Delete the old Gemini enrichment + client**

```bash
git rm src/code_context_graph/enrichment.py src/code_context_graph/gemini_llm.py
```

- [ ] **Step 3: Confirm nothing else references the deleted modules**

Run: `rg -n "enrichment import|SemanticEnricher|gemini_llm|GeminiMessagesClient" src tests`
Expected: NO hits in `src/`. In `tests/`, only `tests/brd/conftest.py:33` may mention `GeminiMessagesClient` in a docstring comment for the unused `FakeLLM` — that is harmless (a comment, no import). If any real import of a deleted symbol remains, remove or fix it.

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS — no import errors; `tests/agent/` green; surviving `tests/brd/` green; integration unaffected.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: cut CLI enrich over to the agent enricher; remove Gemini client"
```

---

## Manual verification (post-implementation; needs a real graph + ANTHROPIC_API_KEY)

1. Ensure `ANTHROPIC_API_KEY` is set and `CODE_GRAPH_LLM_MODEL` is a Claude id in `.env`.
2. Ingest a repo (e.g. carddemo) and confirm entities exist with `semantic_layer` NULL.
3. Run: `uv run ccg enrich <slug>`.
4. Confirm: entities now have `semantic_layer`/`semantic_summary`/`semantic_patterns` set, that high-centrality entities were processed first, and the command terminated (did not loop). Re-running should enrich 0 (all tagged) or only newly-ingested ones.
5. Sanity-check that `ENRICHMENT_MODEL` (or the global) selected a Haiku-tier model in the logs/cost.

---

## Follow-on

- **Plan 3 — Ask-the-Codebase** is the last Gemini path. It will route through `resolve_model("ask")`, keep `enforce_read_only_cypher`, and add graph-tool fallback. After Plan 3, `llm_query.py`'s Gemini client and the `GOOGLE_API_KEY` requirement are fully gone.
