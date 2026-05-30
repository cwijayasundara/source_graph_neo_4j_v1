# Ask-the-Codebase on Claude — Implementation Plan (Plan 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the last Gemini path (`ask_codebase`) onto Claude — keep the proven "generate read-only Cypher → run → summarize" flow and the `enforce_read_only_cypher` safety gate, swap the Gemini client for a Claude text client routed through `resolve_model("ask")`, add a graph-tool agentic fallback when a single Cypher returns nothing, and fully retire `GOOGLE_API_KEY`.

**Architecture:** `ask_codebase` keeps its exact signature and two-call shape; only the default `LLMClient` changes from `GeminiClient` (httpx) to `AnthropicTextClient` (the `anthropic` SDK, sync, Haiku-tier via `resolve_model("ask")`). When the validated Cypher yields zero rows, an optional best-effort fallback runs a bounded agentic query over the existing graph tools (`AgentRunner` + `build_graph_server`) to answer by navigation. The read-only Cypher validator, prompts, and result type are unchanged.

**Tech Stack:** Python ≥3.11, `anthropic==0.105.2` (already a dep), `claude-agent-sdk==0.2.87`, FastAPI, pytest.

**Prereqs / context:** Builds on Plans 1, 1.5, 2 (all merged). Foundation provides `agent/models.py` (`resolve_model("ask")` → Haiku default), `agent/deps.py`, `agent/graph_tools.py` (`build_graph_server`, `GRAPH_TOOL_NAMES`), `agent/harness.py` (`AgentRunner`, `SdkAgentRunner`), and the `seeded`/`fake_runner` fixtures. `src/code_context_graph/llm_query.py` currently holds `GeminiClient` (the only remaining Gemini code in `src/`), `enforce_read_only_cypher`, `ask_codebase(client, repo, question, llm=None)`, `AskCodebaseResult`, and the prompt builders. `ask_codebase` is sync, called by `POST /api/ask` (`api.py:372-388`) with no `llm` passed; tests inject a `FakeLLM` (`tests/test_llm_query.py`). There is no CLI `ask` command.

**Spec:** `docs/superpowers/specs/2026-05-30-graph-navigated-brd-agent-sdk-design.md` ("Ask-the-Codebase" section).

---

## File Structure

| File | Responsibility |
|---|---|
| `src/code_context_graph/llm_query.py` | Swap default LLM to Claude; add `AnthropicTextClient`; add empty-result graph fallback; keep validator/prompts/result type |
| `src/code_context_graph/agent/ask_agent.py` | `agentic_answer(deps, runner, question, model, max_turns)` — bounded graph-navigation answer |
| `tests/test_llm_query.py` | Keep existing tests; add Claude-client + fallback tests |
| `tests/agent/test_ask_agent.py` | Unit-test `agentic_answer` with `fake_runner` |
| `.env.example` | Remove `GOOGLE_API_KEY` (now unused) |

---

## Task 1: Claude text client; swap the default; remove GeminiClient

**Files:**
- Modify: `src/code_context_graph/llm_query.py`
- Modify: `tests/test_llm_query.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_llm_query.py`:

```python
def test_anthropic_text_client_satisfies_protocol_and_resolves_model(monkeypatch):
    from code_context_graph.llm_query import AnthropicTextClient

    for v in ["ASK_MODEL", "CODE_GRAPH_LLM_MODEL"]:
        monkeypatch.delenv(v, raising=False)
    c = AnthropicTextClient()
    # duck-typed LLMClient conformance (LLMClient is a plain Protocol, not
    # runtime_checkable, so isinstance() can't be used here)
    assert callable(getattr(c, "generate_text", None))
    assert c.model == "claude-haiku-4-5-20251001"   # resolve_model("ask") default
    monkeypatch.setenv("ASK_MODEL", "claude-sonnet-4-6")
    assert AnthropicTextClient().model == "claude-sonnet-4-6"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_llm_query.py::test_anthropic_text_client_satisfies_protocol_and_resolves_model -v`
Expected: FAIL — `AnthropicTextClient` not defined.

- [ ] **Step 3: Replace GeminiClient with AnthropicTextClient**

In `src/code_context_graph/llm_query.py`:

(a) Remove the `DEFAULT_MODEL = "gemini-3.5-flash"` line and the entire `class GeminiClient:` (the httpx-based client). Keep `DEFAULT_LIMIT`, `BLOCKED_CYPHER_RE`, `READ_PREFIX_RE`, `CypherValidationError`, `LLMClient` (Protocol), `AskCodebaseResult`, `enforce_read_only_cypher`, `_parse_generation_response`, `_build_cypher_prompt`, `_build_summary_prompt`. Remove the now-unused `import httpx` and `from dotenv import load_dotenv` IF they are not used elsewhere in the file (the file no longer needs them once GeminiClient is gone — verify with a grep and remove only if unused).

(b) Add the Claude client (place it where `GeminiClient` was):

```python
class AnthropicTextClient:
    """LLMClient backed by Claude (Anthropic Messages API), used for the two text
    steps of ask_codebase: Cypher generation and answer summarization. Synchronous,
    Haiku-tier by default via resolve_model('ask')."""

    def __init__(self, model: str | None = None, max_tokens: int = 1024) -> None:
        from code_context_graph.agent.models import resolve_model
        self.model = model or resolve_model("ask")
        self.max_tokens = max_tokens

    def generate_text(self, prompt: str) -> str:
        from anthropic import Anthropic
        client = Anthropic()
        resp = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(getattr(b, "text", "") for b in resp.content)
```

(c) In `ask_codebase`, change the default-client line from `model = llm or GeminiClient()` to:

```python
    model = llm or AnthropicTextClient()
```

(Leave the rest of `ask_codebase` unchanged for now — Cypher gen → enforce → run → summarize.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_llm_query.py -v`
Expected: PASS — the new client test passes AND the 3 existing tests still pass (they inject `FakeLLM`, so the default-client swap doesn't affect them).

- [ ] **Step 5: Commit**

```bash
git add src/code_context_graph/llm_query.py tests/test_llm_query.py
git commit -m "feat(ask): Claude text client for ask_codebase; drop Gemini client"
```

---

## Task 2: Graph-navigation fallback for empty Cypher results

**Files:**
- Create: `src/code_context_graph/agent/ask_agent.py`
- Create: `tests/agent/test_ask_agent.py`
- Modify: `src/code_context_graph/llm_query.py` (`ask_codebase` fallback)
- Modify: `tests/test_llm_query.py` (fallback test)

- [ ] **Step 1: Write the failing test for the agentic answer helper**

Create `tests/agent/test_ask_agent.py`:

```python
from __future__ import annotations

import pytest

from code_context_graph.agent.deps import GraphDeps
from code_context_graph.agent.ask_agent import agentic_answer


@pytest.mark.asyncio
async def test_agentic_answer_returns_model_answer(seeded, tmp_path, fake_runner):
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=tmp_path)
    fake_runner.script({"answer": "It validates the account then posts the transaction."})
    out = await agentic_answer(deps, runner=fake_runner, question="what does X do?",
                               model="m", max_turns=4)
    assert out == "It validates the account then posts the transaction."
    # the agent was offered the graph tools
    from code_context_graph.agent.graph_tools import GRAPH_TOOL_NAMES
    assert fake_runner.calls[0]["allowed_tools"] == GRAPH_TOOL_NAMES


@pytest.mark.asyncio
async def test_agentic_answer_empty_returns_none(seeded, tmp_path, fake_runner):
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=tmp_path)
    fake_runner.script({})  # SDK error / empty
    out = await agentic_answer(deps, runner=fake_runner, question="q", model="m", max_turns=4)
    assert out is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/agent/test_ask_agent.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the agentic answer helper**

Create `src/code_context_graph/agent/ask_agent.py`:

```python
from __future__ import annotations

from code_context_graph.agent.deps import GraphDeps
from code_context_graph.agent.graph_tools import GRAPH_TOOL_NAMES, build_graph_server
from code_context_graph.agent.harness import AgentRunner

ASK_AGENT_SYSTEM = """You answer a question about ONE repository's code using the
graph-navigation tools: list_subsystems, find_entities, get_entity, neighbors
(CALLS/IMPORTS/CONTAINS/INHERITS), get_source_slice (reads only an entity's lines),
entry_points, integration_points. Inspect only what you need, then answer concisely
and ground the answer in real entity ids / file paths. Emit JSON {"answer": "..."}.
If the graph does not contain enough to answer, say so in the answer."""

_ANSWER_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
}


async def agentic_answer(deps: GraphDeps, *, runner: AgentRunner, question: str,
                         model: str, max_turns: int = 4) -> str | None:
    """Answer a question by navigating the graph (fallback when a single Cypher query
    returns nothing). Returns the answer text, or None if the agent produced nothing."""
    server = build_graph_server(deps)
    raw = await runner.run_structured(
        system=ASK_AGENT_SYSTEM, prompt=question, server=server,
        allowed_tools=GRAPH_TOOL_NAMES, model=model, max_turns=max_turns,
        schema=_ANSWER_SCHEMA,
    )
    answer = (raw or {}).get("answer")
    return answer or None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/agent/test_ask_agent.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Write the failing fallback test for ask_codebase**

Add to `tests/test_llm_query.py`:

```python
def test_ask_codebase_falls_back_to_graph_when_no_rows(tmp_path):
    from code_context_graph.llm_query import ask_codebase

    class EmptyGraphClient:
        def __init__(self):
            self.calls = []

        def run(self, query, **params):
            self.calls.append((query, params))
            return []  # the generated Cypher matches nothing

    class CypherOnlyLLM:
        def generate_text(self, prompt):
            return ('{"cypher":"MATCH (e:CodeEntity) WHERE e.repo = $repo '
                    'RETURN e.qualified_name AS name","explanation":"x"}')

    class FakeRunner:
        async def run_structured(self, **kw):
            return {"answer": "Found via graph navigation."}

    result = ask_codebase(
        client=EmptyGraphClient(), repo="r", question="q",
        llm=CypherOnlyLLM(), runner=FakeRunner(), repo_path=str(tmp_path),
    )
    assert result.rows == []
    assert result.answer == "Found via graph navigation."
    assert "navigation" in result.explanation.lower()
```

- [ ] **Step 6: Run test to verify it fails**

Run: `uv run pytest tests/test_llm_query.py::test_ask_codebase_falls_back_to_graph_when_no_rows -v`
Expected: FAIL — `ask_codebase` has no `runner`/`repo_path` params / no fallback.

- [ ] **Step 7: Wire the fallback into ask_codebase**

In `src/code_context_graph/llm_query.py`, change the `ask_codebase` signature and the post-run logic. The function currently is roughly:

```python
def ask_codebase(client, repo, question, llm=None):
    if not question.strip():
        raise ValueError("Question is required")
    model = llm or AnthropicTextClient()
    generation = _parse_generation_response(
        model.generate_text(_build_cypher_prompt(repo=repo, question=question)))
    cypher = enforce_read_only_cypher(generation["cypher"])
    rows = client.run(cypher, repo=repo)
    answer = model.generate_text(_build_summary_prompt(question=question, cypher=cypher, rows=rows))
    return AskCodebaseResult(answer=answer, cypher=cypher, rows=rows,
                             explanation=generation.get("explanation", ""))
```

Replace it with (add `runner=None, repo_path=None`; on empty rows, try the graph fallback before summarizing):

```python
def ask_codebase(client, repo, question, llm=None, runner=None, repo_path=None):
    if not question.strip():
        raise ValueError("Question is required")
    model = llm or AnthropicTextClient()
    generation = _parse_generation_response(
        model.generate_text(_build_cypher_prompt(repo=repo, question=question)))
    cypher = enforce_read_only_cypher(generation["cypher"])
    rows = client.run(cypher, repo=repo)
    explanation = generation.get("explanation", "")

    if not rows:
        fallback = _graph_fallback(client, repo, question, runner=runner,
                                   repo_path=repo_path)
        if fallback:
            return AskCodebaseResult(
                answer=fallback, cypher=cypher, rows=rows,
                explanation=(explanation + " (answered via graph navigation)").strip())

    answer = model.generate_text(
        _build_summary_prompt(question=question, cypher=cypher, rows=rows))
    return AskCodebaseResult(answer=answer, cypher=cypher, rows=rows,
                             explanation=explanation)
```

And add the `_graph_fallback` helper (best-effort: returns None if the repo path can't be resolved or the agent answers nothing — so the caller falls back to the normal empty-row summary):

```python
def _graph_fallback(client, repo, question, *, runner=None, repo_path=None):
    """Answer via graph navigation when a single Cypher query returned no rows.
    Best-effort: returns None (so the caller summarizes the empty result) if the repo
    has no local path or the agent produced nothing."""
    import asyncio
    from pathlib import Path

    if repo_path is None:
        from code_context_graph.repo_manager import RepoManager
        meta = RepoManager(client).get(repo)
        if not meta or not meta.get("local_path"):
            return None
        repo_path = meta["local_path"]

    from code_context_graph.agent.deps import GraphDeps
    from code_context_graph.agent.ask_agent import agentic_answer
    from code_context_graph.agent.models import resolve_model

    if runner is None:
        from code_context_graph.agent.harness import SdkAgentRunner
        runner = SdkAgentRunner()
    deps = GraphDeps(client=client, repo_id=repo, repo_path=Path(repo_path))
    try:
        return asyncio.run(agentic_answer(
            deps, runner=runner, question=question,
            model=resolve_model("ask"), max_turns=4))
    except Exception:
        return None
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest tests/test_llm_query.py tests/agent/test_ask_agent.py -v`
Expected: PASS — the fallback test passes; the 3 original `ask_codebase`/validator tests still pass (their `FakeGraphClient` returns a non-empty row, so the fallback branch is skipped).

- [ ] **Step 9: Commit**

```bash
git add src/code_context_graph/agent/ask_agent.py tests/agent/test_ask_agent.py src/code_context_graph/llm_query.py tests/test_llm_query.py
git commit -m "feat(ask): graph-navigation fallback when Cypher returns no rows"
```

---

## Task 3: Retire GOOGLE_API_KEY; final sweep

**Files:**
- Modify: `.env.example`
- Modify: `README.md` (only if it references `GOOGLE_API_KEY`)

- [ ] **Step 1: Confirm Gemini is fully gone from `src/`**

Run: `rg -n "gemini|GOOGLE_API_KEY|GeminiClient|httpx" src/code_context_graph`
Expected: NO hits for `gemini`/`GOOGLE_API_KEY`/`GeminiClient`. If `httpx` still appears, confirm it's used by a non-Gemini module (e.g. github_client) and leave it. If `GOOGLE_API_KEY` appears anywhere in `src/`, remove that usage — it must be zero.

- [ ] **Step 2: Remove GOOGLE_API_KEY from `.env.example`**

READ `.env.example`. Delete the `GOOGLE_API_KEY=...` line and its preceding comment (the one updated in Plan 2 to "Only needed for the legacy Ask-the-Codebase path..."). Ask-the-Codebase is now on Claude (`ANTHROPIC_API_KEY` + `CODE_GRAPH_LLM_MODEL`/`ASK_MODEL`), so the Google key is fully unused. Leave all Claude/Neo4j/COBOL vars intact.

- [ ] **Step 3: Update README if needed**

Run: `rg -n "GOOGLE_API_KEY|gemini" README.md`
If there are hits describing setup, update them to reflect Claude (`ANTHROPIC_API_KEY`, `CODE_GRAPH_LLM_MODEL`). If no hits, skip this step.

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS — all green (130 passed + the 1 pre-existing skip; counts may differ slightly with the new tests).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: retire GOOGLE_API_KEY; ask-the-codebase fully on Claude"
```

---

## Manual verification (needs ANTHROPIC_API_KEY + a real graph)

1. Ensure `ANTHROPIC_API_KEY` set; `GOOGLE_API_KEY` NOT needed.
2. `POST /api/ask` with `{repo, question}` for a question answerable by one Cypher (e.g. "which functions are most complex?") — confirm a grounded answer + the generated read-only Cypher in the response.
3. Try a multi-hop question that a single Cypher can't answer (returns no rows) — confirm the graph-navigation fallback produces an answer and the `explanation` notes "(answered via graph navigation)".
4. Confirm `enforce_read_only_cypher` still rejects a write (the model cannot produce a DELETE/SET that runs).
5. Confirm the ask path used a Haiku-tier model (via `ASK_MODEL`/global) in cost/logs.

---

## Outcome

After this plan, **all three LLM paths (BRD, enrichment, ask) run on Claude via the Agent SDK foundation**, model selection is unified through `resolve_model`, prompt-cache/cost is tracked, the advisor is available to BRD, and `GOOGLE_API_KEY` is fully retired. The Gemini integration is gone.
