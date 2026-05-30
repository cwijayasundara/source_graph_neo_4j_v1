# Token Economics: Model Resolver, Prompt-Cache Tracking, Advisor Tool — Implementation Plan (Plan 1.5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make this token-heavy app cheaper and more steerable: one `.env`-driven Claude model resolver, full prompt-cache + cost tracking in the harness (caching is already automatic — we just need to exploit and measure it), and an in-process **advisor tool** (cheap Sonnet worker can escalate a hard decision to an Opus advisor mid-task), wired into the BRD subsystem workers while keeping the existing judge.

**Architecture:** `agent/models.py` (`resolve_model(role)`) centralizes model choice with per-role Claude defaults. The `SdkAgentRunner` already gets automatic prompt caching from the Agent SDK; we extend it to capture `cache_read`/`cache_creation` tokens + `total_cost_usd`, and optionally request a 1-hour cache TTL. The advisor is implemented as our own in-process MCP tool `consult_advisor` (no dependency on the beta `advisor_20260301` API tool): its handler makes one short Opus call and returns ≤700 tokens of guidance, capped by a per-run budget. It is added to the same `graph` MCP server and offered only to the BRD *map* workers — the judge (post-hoc groundedness gate) is unchanged. Advisor and judge are complementary: the advisor steers generation in-flight (fewer bad drafts → fewer expensive judge-retry loops), the judge validates the finished BRD against the full graph reference set.

**Tech Stack:** Python ≥3.11, `claude-agent-sdk==0.2.87`, `anthropic` SDK (re-added for the single-shot advisor call), Pydantic, pytest (+ `pytest-asyncio`).

**Prereqs / context:** Builds on Plan 1 (merged). Foundation already provides `agent/{deps,graph_ops,graph_tools,harness,brd_orchestrator,brd_judge,brd_schema}.py` and the `fake_runner`/`seeded` fixtures. This plan runs **before** Plan 2; Plan 2's "model resolver" task is removed (it lives here now).

**Spec:** `docs/superpowers/specs/2026-05-30-graph-navigated-brd-agent-sdk-design.md` (Cost & determinism). **Reference:** the advisor strategy (worker+advisor) and Agent SDK cost-tracking/prompt-caching docs.

> **Live `.env` note:** after Task 1, `CODE_GRAPH_LLM_MODEL` becomes the global Claude model default for all paths. The live `.env` currently has `CODE_GRAPH_LLM_MODEL=gemini-3.5-flash` — Task 1 Step 6 changes it to a Claude id. `.env` is gitignored; never commit it.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/code_context_graph/agent/models.py` | `resolve_model(role)` selector (roles: brd, enrichment, ask, advisor) |
| `src/code_context_graph/agent/advisor.py` | `AdvisorBackend` protocol, `AnthropicAdvisor`, advisor tool handler + `build_advisor_tool` |
| `src/code_context_graph/agent/graph_tools.py` | `build_graph_server(deps, *, advisor=None, advisor_max_uses=…)` adds the advisor tool |
| `src/code_context_graph/agent/harness.py` | capture cache + cost tokens; optional 1h TTL |
| `src/code_context_graph/agent/brd_orchestrator.py` | offer the advisor tool to map workers when enabled |
| `src/code_context_graph/brd/pipeline.py` | route BRD model through `resolve_model`; build advisor from env in the sync wrapper |
| `tests/agent/conftest.py` | `FakeAgentRunner` also records `allowed_tools` |
| Tests | `test_models.py`, `test_harness_usage.py`, `test_advisor.py`, additions to `test_brd_orchestrator.py` |

---

## Task 1: Model resolver

**Files:**
- Create: `src/code_context_graph/agent/models.py`
- Create: `tests/agent/test_models.py`
- Modify: `src/code_context_graph/brd/pipeline.py` (the one model-default line)
- Modify: `.env.example` and the live `.env`

- [ ] **Step 1: Write the failing tests**

Create `tests/agent/test_models.py`:

```python
from __future__ import annotations

from code_context_graph.agent.models import resolve_model

_ALL = ["BRD_AGENT_MODEL", "ENRICHMENT_MODEL", "ASK_MODEL", "ADVISOR_MODEL",
        "CODE_GRAPH_LLM_MODEL"]


def _clear(monkeypatch):
    for v in _ALL:
        monkeypatch.delenv(v, raising=False)


def test_role_override_wins(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("BRD_AGENT_MODEL", "claude-opus-4-8")
    monkeypatch.setenv("CODE_GRAPH_LLM_MODEL", "claude-sonnet-4-6")
    assert resolve_model("brd") == "claude-opus-4-8"


def test_global_default_used_when_no_role_override(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("CODE_GRAPH_LLM_MODEL", "claude-sonnet-4-6")
    assert resolve_model("enrichment") == "claude-sonnet-4-6"


def test_hardcoded_fallback_per_role(monkeypatch):
    _clear(monkeypatch)
    assert resolve_model("brd") == "claude-sonnet-4-6"
    assert resolve_model("enrichment") == "claude-haiku-4-5-20251001"
    assert resolve_model("ask") == "claude-haiku-4-5-20251001"
    assert resolve_model("advisor") == "claude-opus-4-8"


def test_unknown_role_falls_back_to_sonnet(monkeypatch):
    _clear(monkeypatch)
    assert resolve_model("something_else") == "claude-sonnet-4-6"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/agent/test_models.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the resolver**

Create `src/code_context_graph/agent/models.py`:

```python
from __future__ import annotations

import os

# Single global model var (override per-role below). Must be a Claude model id.
GLOBAL_ENV = "CODE_GRAPH_LLM_MODEL"

_ROLE_ENV = {
    "brd": "BRD_AGENT_MODEL",
    "enrichment": "ENRICHMENT_MODEL",
    "ask": "ASK_MODEL",
    "advisor": "ADVISOR_MODEL",
}

# Hardcoded Claude fallbacks (tiers): cheap Haiku for high-volume roles, Sonnet for
# BRD synthesis/judge, Opus for the advisor (capable guidance, used sparingly).
_DEFAULTS = {
    "brd": "claude-sonnet-4-6",
    "enrichment": "claude-haiku-4-5-20251001",
    "ask": "claude-haiku-4-5-20251001",
    "advisor": "claude-opus-4-8",
}


def resolve_model(role: str) -> str:
    """Resolve the Claude model for a role.

    Precedence: per-role override env var -> global CODE_GRAPH_LLM_MODEL ->
    hardcoded Claude default for the role (Sonnet if role unknown).
    """
    role_env = _ROLE_ENV.get(role)
    if role_env and os.getenv(role_env):
        return os.environ[role_env]
    if os.getenv(GLOBAL_ENV):
        return os.environ[GLOBAL_ENV]
    return _DEFAULTS.get(role, "claude-sonnet-4-6")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/agent/test_models.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Route the BRD path through the resolver**

In `src/code_context_graph/brd/pipeline.py`, find (currently ~86):

```python
    model = model or os.getenv("BRD_AGENT_MODEL", "claude-sonnet-4-6")
```

Replace with:

```python
    model = model or resolve_model("brd")
```

`agent.models` imports only `os`, so a top-of-file `from code_context_graph.agent.models import resolve_model` does NOT reintroduce the circular import — add it at the top of `pipeline.py`. Verify:

Run: `uv run pytest tests/agent/test_pipeline_graph.py -v`
Expected: PASS (1 passed)

- [ ] **Step 6: Update `.env.example` and the live `.env`**

In `.env.example`, replace the existing `CODE_GRAPH_LLM_MODEL` and `BRD_AGENT_MODEL` lines with:

```bash
# Claude model selection (single source of truth). Per-role overrides win over the
# global; leave overrides blank to use the global. All must be Claude model ids.
CODE_GRAPH_LLM_MODEL=claude-sonnet-4-6     # global default for every LLM path
BRD_AGENT_MODEL=                            # optional: BRD synthesis/judge
ENRICHMENT_MODEL=                           # optional: enrichment (else Haiku)
ASK_MODEL=                                  # optional: ask-the-codebase (else Haiku)
ADVISOR_MODEL=                              # optional: advisor (else Opus)
```

Then Edit the LIVE `.env` (Read it first; gitignored — do NOT commit): change `CODE_GRAPH_LLM_MODEL=gemini-3.5-flash` to `CODE_GRAPH_LLM_MODEL=claude-sonnet-4-6`. If absent, note it and skip.

- [ ] **Step 7: Commit (do not stage `.env`)**

```bash
git add src/code_context_graph/agent/models.py tests/agent/test_models.py src/code_context_graph/brd/pipeline.py .env.example
git commit -m "feat(agent): single resolve_model() selector with Claude tiers"
```

---

## Task 2: Harness cache + cost tracking; 1-hour TTL

**Files:**
- Modify: `src/code_context_graph/agent/harness.py`
- Create: `tests/agent/test_harness_usage.py`

- [ ] **Step 1: Write the failing test for the pure accumulator**

Create `tests/agent/test_harness_usage.py`:

```python
from __future__ import annotations

from code_context_graph.agent.harness import _accumulate_usage, _caching_env


def test_accumulate_sums_all_four_token_buckets():
    tu = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}
    _accumulate_usage(tu, {"input_tokens": 10, "output_tokens": 5,
                           "cache_read_input_tokens": 3,
                           "cache_creation_input_tokens": 7})
    _accumulate_usage(tu, {"input_tokens": 1, "output_tokens": 1})  # missing cache keys
    assert tu == {"input": 11, "output": 6, "cache_read": 3, "cache_creation": 7}


def test_accumulate_tolerates_none_and_empty():
    tu = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}
    _accumulate_usage(tu, None)
    _accumulate_usage(tu, {})
    assert tu == {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}


def test_caching_env_off_by_default(monkeypatch):
    monkeypatch.delenv("CCG_PROMPT_CACHING_1H", raising=False)
    assert _caching_env() == {}


def test_caching_env_on_when_flag_set(monkeypatch):
    monkeypatch.setenv("CCG_PROMPT_CACHING_1H", "1")
    assert _caching_env() == {"ENABLE_PROMPT_CACHING_1H": "1"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/agent/test_harness_usage.py -v`
Expected: FAIL — `_accumulate_usage` / `_caching_env` not defined.

- [ ] **Step 3: Refactor the harness**

In `src/code_context_graph/agent/harness.py`, add `import os` at top (if absent), and add these module-level helpers above `SdkAgentRunner`:

```python
def _accumulate_usage(token_usage: dict, usage: dict | None) -> None:
    """Add one ResultMessage.usage dict into the running token_usage, capturing
    standard input/output AND prompt-cache read/creation tokens. Tolerates None,
    missing keys, and None values."""
    usage = usage or {}
    token_usage["input"] += usage.get("input_tokens", 0) or 0
    token_usage["output"] += usage.get("output_tokens", 0) or 0
    token_usage["cache_read"] += usage.get("cache_read_input_tokens", 0) or 0
    token_usage["cache_creation"] += usage.get("cache_creation_input_tokens", 0) or 0


def _caching_env() -> dict[str, str]:
    """Request a 1-hour prompt-cache TTL when CCG_PROMPT_CACHING_1H=1. Useful for
    batch runs (many short queries share a stable system-prompt + tool prefix; the
    default 5-min TTL can expire between subsystems)."""
    if os.getenv("CCG_PROMPT_CACHING_1H", "").lower() in ("1", "true", "yes"):
        return {"ENABLE_PROMPT_CACHING_1H": "1"}
    return {}
```

Change `SdkAgentRunner.__init__` to:

```python
    def __init__(self) -> None:
        self.token_usage = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}
        self.cost_usd = 0.0
```

In `SdkAgentRunner.run_structured`, set `env=_caching_env()` on the `ClaudeAgentOptions(...)` call, and replace the per-message usage handling so the `ResultMessage` branch reads:

```python
            if isinstance(message, ResultMessage):
                structured = message.structured_output or {}
                _accumulate_usage(self.token_usage, getattr(message, "usage", None))
                self.cost_usd += getattr(message, "total_cost_usd", 0.0) or 0.0
```

Keep the existing broad `try/except` that logs and returns `{}` (from Plan 1's review fix). Keep `tools=[]`, `setting_sources=[]`, `output_format=...` as they are.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/agent/test_harness_usage.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Update the BRD pipeline token_usage mapping**

`generate_brd_graph_sync` in `brd/pipeline.py` currently builds `token_usage={"input": runner.token_usage["input"], "output": runner.token_usage["output"]}`. Replace it with the full dict so cache savings persist into `BRDResult.token_usage`:

```python
        token_usage=dict(runner.token_usage),
```

Verify nothing breaks:

Run: `uv run pytest tests/agent/ -q`
Expected: all green.

- [ ] **Step 6: Document the cache flag in `.env.example`**

Append under the model section in `.env.example`:

```bash
# Prompt caching is automatic. Set to 1 to request a 1-hour cache TTL (better for
# big batch runs; cache writes cost slightly more). Leave blank for the 5-min default.
CCG_PROMPT_CACHING_1H=
```

- [ ] **Step 7: Commit**

```bash
git add src/code_context_graph/agent/harness.py tests/agent/test_harness_usage.py src/code_context_graph/brd/pipeline.py .env.example
git commit -m "feat(agent): track prompt-cache + cost tokens; optional 1h TTL"
```

---

## Task 3: Advisor backend + `consult_advisor` in-process tool

**Files:**
- Modify: `pyproject.toml` (re-add `anthropic`)
- Create: `src/code_context_graph/agent/advisor.py`
- Modify: `src/code_context_graph/agent/graph_tools.py` (`build_graph_server` advisor param)
- Create: `tests/agent/test_advisor.py`

- [ ] **Step 1: Re-add the anthropic dependency**

In `pyproject.toml` `[project.dependencies]`, add:

```toml
  "anthropic>=0.40",
```

Run: `uv sync`
Expected: installs `anthropic`.

- [ ] **Step 2: Write the failing tests**

Create `tests/agent/test_advisor.py`:

```python
from __future__ import annotations

import json

import pytest

from code_context_graph.agent.advisor import (
    ADVISOR_TOOL_NAME, AdvisorBackend, make_advisor_handler,
)


class FakeAdvisor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def advise(self, question: str, context: str) -> str:
        self.calls.append((question, context))
        return "Prefer the State Machine reading."


def test_tool_name_is_namespaced():
    assert ADVISOR_TOOL_NAME == "mcp__graph__consult_advisor"


def test_fakeadvisor_satisfies_protocol():
    assert isinstance(FakeAdvisor(), AdvisorBackend)


@pytest.mark.asyncio
async def test_advisor_handler_returns_guidance():
    backend = FakeAdvisor()
    handler = make_advisor_handler(backend, max_uses=2)
    out = await handler({"question": "rule or plumbing?", "context": "para 1000"})
    payload = json.loads(out["content"][0]["text"])
    assert payload["advice"] == "Prefer the State Machine reading."
    assert backend.calls == [("rule or plumbing?", "para 1000")]


@pytest.mark.asyncio
async def test_advisor_handler_enforces_budget():
    backend = FakeAdvisor()
    handler = make_advisor_handler(backend, max_uses=1)
    await handler({"question": "q1", "context": ""})            # uses the 1 allowed call
    out = await handler({"question": "q2", "context": ""})       # over budget
    payload = json.loads(out["content"][0]["text"])
    assert payload["advice"] is None and "budget" in payload["note"].lower()
    assert len(backend.calls) == 1                                # backend not called again
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/agent/test_advisor.py -v`
Expected: FAIL — module not found.

- [ ] **Step 4: Implement the advisor**

Create `src/code_context_graph/agent/advisor.py`:

```python
from __future__ import annotations

import json
import logging
from typing import Any, Protocol, runtime_checkable

from claude_agent_sdk import tool, ToolAnnotations

logger = logging.getLogger(__name__)

ADVISOR_TOOL_NAME = "mcp__graph__consult_advisor"

ADVISOR_SYSTEM = """You are a senior software architect acting as an ADVISOR to a
worker agent that is extracting business requirements from code. The worker calls you
only when it hits a genuinely hard judgment call. Give a SHORT, decisive answer: a
plan, a correction, or a stop signal. Do not restate the question. Do not exceed a few
sentences. You cannot call tools."""


@runtime_checkable
class AdvisorBackend(Protocol):
    async def advise(self, question: str, context: str) -> str:
        ...


class AnthropicAdvisor:
    """Real advisor: one short Opus call via the Anthropic Messages API. The static
    system prompt is marked cacheable. Only exercised in manual verification."""

    def __init__(self, model: str | None = None, max_tokens: int = 700) -> None:
        from code_context_graph.agent.models import resolve_model
        self.model = model or resolve_model("advisor")
        self.max_tokens = max_tokens

    async def advise(self, question: str, context: str) -> str:
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic()
        resp = await client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=[{"type": "text", "text": ADVISOR_SYSTEM,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user",
                       "content": f"Decision: {question}\n\nContext:\n{context}"}],
        )
        return "".join(getattr(b, "text", "") for b in resp.content)


def make_advisor_handler(backend: AdvisorBackend, max_uses: int):
    """Build the async tool handler. Enforces a shared per-run budget; once exhausted
    it returns advice=None so the worker proceeds on its own rather than erroring."""
    budget = [max_uses]

    def _ok(payload: Any) -> dict[str, Any]:
        return {"content": [{"type": "text", "text": json.dumps(payload, default=str)}]}

    async def consult_advisor(args: dict[str, Any]) -> dict[str, Any]:
        if budget[0] <= 0:
            return _ok({"advice": None, "note": "advisor budget exhausted; proceed yourself"})
        budget[0] -= 1
        try:
            advice = await backend.advise(args["question"], args.get("context", ""))
            return _ok({"advice": advice})
        except Exception as exc:
            logger.exception("advisor call failed")
            return {"content": [{"type": "text",
                                 "text": json.dumps({"advice": None,
                                                     "note": f"advisor error: {type(exc).__name__}"})}],
                    "is_error": True}

    return consult_advisor


def build_advisor_tool(backend: AdvisorBackend, max_uses: int):
    """Wrap the handler as an SDK tool on the 'graph' server (hence the FQN
    mcp__graph__consult_advisor)."""
    handler = make_advisor_handler(backend, max_uses)
    return tool(
        "consult_advisor",
        "Ask a senior architect advisor for guidance on ONE hard judgment call "
        "(e.g. is this code a business rule or plumbing?). Pass 'question' and a short "
        "'context'. Returns brief advice; use sparingly — there is a limited budget.",
        {"question": str, "context": str},
        annotations=ToolAnnotations(readOnlyHint=True),
    )(handler)
```

- [ ] **Step 5: Let `build_graph_server` optionally include the advisor**

In `src/code_context_graph/agent/graph_tools.py`, change the `build_graph_server` signature and append the advisor tool when a backend is supplied. Replace the `def build_graph_server(deps: GraphDeps):` definition's signature and the `return` so it reads:

```python
def build_graph_server(deps: GraphDeps, *, advisor=None, advisor_max_uses: int = 3):
    """Build the in-process MCP server exposing graph navigation tools, all bound to
    this repo's GraphDeps. All tools are read-only. If `advisor` (an AdvisorBackend)
    is given, a consult_advisor tool is added with a shared per-server use budget."""
    h = _make_handlers(deps)

    tools = [
        # ... (keep the existing 8 tool(...) entries exactly as they are) ...
    ]
    if advisor is not None:
        from code_context_graph.agent.advisor import build_advisor_tool
        tools.append(build_advisor_tool(advisor, advisor_max_uses))
    return create_sdk_mcp_server(name=SERVER_NAME, version="1.0.0", tools=tools)
```

(Keep the 8 existing tool entries unchanged inside the `tools` list; only add the `if advisor is not None:` block before `return`.)

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/agent/test_advisor.py tests/agent/test_graph_tools.py -v`
Expected: PASS (advisor: 4 passed; graph_tools: 3 passed).

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock src/code_context_graph/agent/advisor.py src/code_context_graph/agent/graph_tools.py tests/agent/test_advisor.py
git commit -m "feat(agent): in-process Opus advisor tool with per-run budget"
```

---

## Task 4: Offer the advisor to BRD map workers

**Files:**
- Modify: `tests/agent/conftest.py` (`FakeAgentRunner` records `allowed_tools`)
- Modify: `src/code_context_graph/agent/brd_orchestrator.py`
- Modify: `src/code_context_graph/brd/pipeline.py` (build advisor from env in the sync wrapper)
- Modify: `tests/agent/test_brd_orchestrator.py` (advisor-offered assertion)

- [ ] **Step 1: Make the fake runner record allowed_tools**

In `tests/agent/conftest.py`, in `FakeAgentRunner.run_structured`, change the recorded call dict to also capture `allowed_tools`:

```python
        self.calls.append({"system": system, "prompt": prompt, "model": model,
                           "max_turns": max_turns, "allowed_tools": allowed_tools})
```

- [ ] **Step 2: Write the failing test**

Add to `tests/agent/test_brd_orchestrator.py`:

```python
@pytest.mark.asyncio
async def test_advisor_offered_to_map_workers_when_enabled(seeded, tmp_path, fake_runner):
    from code_context_graph.agent.advisor import ADVISOR_TOOL_NAME

    class FakeAdvisor:
        async def advise(self, question, context):
            return "advice"

    seeded.when(lambda q, p: "RETURN e.qualified_name AS qn" in q, [{"qn": "a"}])
    seeded.when(lambda q, p: "RETURN a.qualified_name AS src" in q, [])
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=tmp_path)
    fake_runner.script(
        {"sections": [{"title": "Executive Summary", "body_markdown": "x",
                       "requirements": []}], "evidence_map": {}},
    )
    await agenerate_brd_draft(deps, runner=fake_runner, model="m", max_turns=5,
                              max_subsystems=12, advisor=FakeAdvisor(), advisor_max_uses=2)
    # the single map call must have been offered the advisor tool
    assert ADVISOR_TOOL_NAME in fake_runner.calls[0]["allowed_tools"]


@pytest.mark.asyncio
async def test_no_advisor_tool_when_disabled(seeded, tmp_path, fake_runner):
    from code_context_graph.agent.advisor import ADVISOR_TOOL_NAME

    seeded.when(lambda q, p: "RETURN e.qualified_name AS qn" in q, [{"qn": "a"}])
    seeded.when(lambda q, p: "RETURN a.qualified_name AS src" in q, [])
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=tmp_path)
    fake_runner.script(
        {"sections": [{"title": "Executive Summary", "body_markdown": "x",
                       "requirements": []}], "evidence_map": {}},
    )
    await agenerate_brd_draft(deps, runner=fake_runner, model="m", max_turns=5,
                              max_subsystems=12)  # advisor defaults to None
    assert ADVISOR_TOOL_NAME not in fake_runner.calls[0]["allowed_tools"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/agent/test_brd_orchestrator.py -k advisor -v`
Expected: FAIL — `agenerate_brd_draft` does not accept `advisor`.

- [ ] **Step 4: Thread the advisor through the orchestrator**

In `src/code_context_graph/agent/brd_orchestrator.py`:

Add an import at the top:

```python
from code_context_graph.agent.advisor import ADVISOR_TOOL_NAME
```

Change `agenerate_brd_draft`'s signature and body. Replace the function definition through the `server = build_graph_server(deps)` line and the `_map_one` call/reduce `allowed_tools` so it reads:

```python
async def agenerate_brd_draft(deps: GraphDeps, *, runner: AgentRunner, model: str,
                              max_turns: int, max_subsystems: int,
                              advisor=None, advisor_max_uses: int = 3
                              ) -> tuple[BRDDraft, Strategy]:
    server = build_graph_server(deps, advisor=advisor, advisor_max_uses=advisor_max_uses)
    map_tools = list(GRAPH_TOOL_NAMES) + ([ADVISOR_TOOL_NAME] if advisor is not None else [])
    subs = ops.list_subsystems(deps, max_clusters=max_subsystems)["subsystems"]
    if not subs:
        subs = [{"name": deps.repo_id, "members": []}]

    drafts = await asyncio.gather(*[
        _map_one(deps, runner, server, map_tools, model, max_turns, s) for s in subs
    ])

    if len(drafts) == 1:
        return drafts[0], Strategy.single_shot

    try:
        merged = await runner.run_structured(
            system=REDUCE_SYSTEM, prompt=_reduce_prompt(list(drafts)),
            server=server, allowed_tools=GRAPH_TOOL_NAMES, model=model,
            max_turns=max_turns, schema=brd_draft_schema(),
        )
        return BRDDraft.model_validate(merged), Strategy.map_reduce
    except Exception:
        return _merge_drafts_fallback(list(drafts)), Strategy.map_reduce
```

And update `_map_one` to take the tool list (it currently hardcodes `GRAPH_TOOL_NAMES`):

```python
async def _map_one(deps, runner, server, allowed_tools, model, max_turns, sub) -> BRDDraft:
    try:
        raw = await runner.run_structured(
            system=MAP_SYSTEM, prompt=_map_prompt(sub["name"], sub["members"]),
            server=server, allowed_tools=allowed_tools, model=model,
            max_turns=max_turns, schema=brd_draft_schema(),
        )
        return BRDDraft.model_validate(raw)
    except Exception as exc:
        return _stub_draft(sub["name"], exc)
```

(The map workers get the advisor; the reduce step keeps `GRAPH_TOOL_NAMES` only — merging doesn't need escalation. The judge is untouched.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/agent/test_brd_orchestrator.py -v`
Expected: PASS (5 passed — the 3 originals + 2 advisor tests).

- [ ] **Step 6: Build the advisor from env in the BRD sync wrapper**

In `src/code_context_graph/brd/pipeline.py`, `agenerate_brd_graph` calls `agenerate_brd_draft`. Thread an optional advisor through it. First, update `agenerate_brd_graph`'s signature to accept `advisor=None, advisor_max_uses: int = 3` and pass them into the `agenerate_brd_draft(...)` call inside its loop:

```python
        draft, strategy = await agenerate_brd_draft(
            deps, runner=runner, model=model, max_turns=max_turns,
            max_subsystems=max_subsystems, advisor=advisor,
            advisor_max_uses=advisor_max_uses)
```

Then in `generate_brd_graph_sync`, build the advisor from env before running, and pass it through `asyncio.run(agenerate_brd_graph(...))`:

```python
    advisor = None
    advisor_max_uses = int(os.getenv("ADVISOR_MAX_USES", "3"))
    if os.getenv("BRD_ADVISOR_ENABLED", "").lower() in ("1", "true", "yes"):
        from code_context_graph.agent.advisor import AnthropicAdvisor
        advisor = AnthropicAdvisor()
    result = asyncio.run(agenerate_brd_graph(
        deps, runner=runner, model=model, max_retries=max_retries,
        max_turns=max_turns, max_subsystems=max_subsystems,
        advisor=advisor, advisor_max_uses=advisor_max_uses))
```

- [ ] **Step 7: Document the advisor env knobs in `.env.example`**

Append:

```bash
# Advisor strategy: let cheap BRD workers escalate hard calls to an Opus advisor.
BRD_ADVISOR_ENABLED=       # 1 to enable (off by default; adds Opus calls)
ADVISOR_MAX_USES=3         # per-BRD-run advisor call budget (shared across subsystems)
```

- [ ] **Step 8: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS — all green (advisor disabled by default, so existing behavior is unchanged unless `BRD_ADVISOR_ENABLED=1`).

- [ ] **Step 9: Commit**

```bash
git add src/code_context_graph/agent/brd_orchestrator.py src/code_context_graph/brd/pipeline.py tests/agent/conftest.py tests/agent/test_brd_orchestrator.py .env.example
git commit -m "feat(brd): offer Opus advisor tool to map workers (env-gated)"
```

---

## Manual verification (needs ANTHROPIC_API_KEY + a real graph)

1. `CODE_GRAPH_LLM_MODEL=claude-sonnet-4-6` in `.env`. Generate a BRD; confirm `BRDResult.token_usage` now reports `cache_read`/`cache_creation` > 0 on the second+ subsystem (cache hits on the shared system-prompt/tool prefix).
2. Set `CCG_PROMPT_CACHING_1H=1`; confirm cache hits persist across a longer run.
3. Set `BRD_ADVISOR_ENABLED=1`, `ADVISOR_MAX_USES=3`; generate a BRD on a gnarly subsystem and confirm (via logs/model_usage) that some Opus advisor calls occurred, capped at the budget, and the judge still ran.
4. Compare token_usage/cost with advisor off vs on to validate the "fewer judge retries" hypothesis.

---

## Follow-on

- **Plan 2 (enrichment)** now assumes `resolve_model` exists (this plan) and uses `resolve_model("enrichment")`; its model-resolver task is removed. Enrichment stays Haiku-solo (no advisor) per the cost decision.
- **Plan 3 (ask-the-codebase)** routes through `resolve_model("ask")` and may optionally offer the advisor for multi-hop questions.
