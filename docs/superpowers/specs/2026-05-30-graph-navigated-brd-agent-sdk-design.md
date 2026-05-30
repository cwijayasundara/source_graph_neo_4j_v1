# Graph-Navigated BRD & Context Engineering on the Claude Agent SDK

**Date:** 2026-05-30
**Status:** Approved design, pre-implementation
**Author:** cwijayasundara (with Claude)

## Problem

The Neo4j code/context graph was built specifically to capture dependencies
between entities (CALLS, IMPORTS, CONTAINS, INHERITS, CO_CHANGED_WITH). Today the
BRD generator does **not** use those dependencies to engineer context. Instead it:

- summarizes the graph into a text blob (`brd/context_builder.py:115`),
- ranks files by centrality but only uses the ranking for ordering, never for
  selection or slicing (`context_builder.py:163`),
- loads **whole-file source for every file** and concatenates it into one prompt
  (`context_builder.py:181`), gated only by an 800k-token budget.

For a realistic codebase (`aws-mf-mod-carddemo`: ~40,800 lines of COBOL across 106
files, largest single program 4,236 lines) this dumps the entire codebase into one
LLM call. The graph edges that were expensive to compute never inform *what source
the model sees*. This does not scale and wastes the graph.

Two related paths share the same provider stack and similar weaknesses:
- **Semantic enrichment** (`enrichment.py`) caps at 50 entities/run, serial LLM
  calls, arbitrary `LIMIT` with no centrality ordering.
- **Ask-the-Codebase** (`llm_query.py`) is actually a sound RAG pattern (generate
  read-only Cypher → run → summarize) but is on the path being unified.

## Goal

Re-architect context engineering so BRD generation **navigates the graph and pulls
context incrementally** (only the slices each requirement needs) instead of sending
the whole codebase to the LLM. Use the **Claude Agent SDK** as the execution
substrate for its agentic tool loop, subagent context isolation, automatic
compaction, and prompt caching.

### Hard constraints

1. **Language-agnostic.** The tool must analyse and create BRDs from Python, Java,
   Rust, **and** COBOL codebases. No COBOL-specific assumptions may leak into the
   agent layer. The only language-aware components are the parsers that populate the
   graph; everything in this design sits downstream of that boundary and sees only
   entities and edges.
2. **Read-only and safe.** Graph tools are read-only. The `enforce_read_only_cypher`
   guard (`$repo` scoping + blocked clauses) must survive into the new
   Ask-the-Codebase path.
3. **Bounded cost.** Agentic loops must have explicit `maxTurns`, model tiering, and
   a subsystem fan-out cap.

## Decisions (settled during brainstorming)

| Decision | Choice |
|---|---|
| Scope | All three LLM paths (BRD, enrichment, Ask-the-Codebase) on one shared foundation |
| Spec structure | One spec, sequenced build (foundation → BRD → enrichment → ask-codebase) |
| Substrate | Claude Agent SDK (Claude-only; re-introduces Anthropic dependency, replacing the current Gemini stack) |
| Tool exposure | In-process SDK MCP tools (`create_sdk_mcp_server` / `@tool`), reusing `Neo4jClient` + `CodeGraphQueries` |
| Migration | Replace the Gemini paths outright; delete `gemini_llm.py` |
| BRD orchestration | Approach A — subagent-per-subsystem (map) + parent reduce |

> Note: this reverses the prior commit (`c4848a7`) that standardized the stack on
> Gemini. The Gemini integration is removed across all three paths.

## Architecture

```
                    ┌─────────────────────────────────────────────┐
                    │   Claude Agent SDK harness (Python)          │
                    │                                              │
  BRD orchestrator ─┤  enrichment agent ─┐   ask-codebase agent ─┐ │
   (map/reduce)     │                    │                       │ │
        │           └────────┬───────────┴───────────┬───────────┘ │
        └────────────────────┴────────────────────────┘            │
                             │  all three use ↓                     │
                    ┌────────────────────────────────────┐         │
                    │  graph_tools  (in-process SDK MCP)  │         │
                    │  language-agnostic, read-only       │         │
                    └────────┬───────────────────────────-┘         │
                    ┌────────▼─────────┐   ┌──────────────────┐     │
                    │  CodeGraphQueries│   │ SourceSlicer     │     │
                    │  (Neo4j, exists) │   │ (disk, by lines) │     │
                    └──────────────────┘   └──────────────────┘     │
                    └─────────────────────────────────────────────-┘
```

**Key invariant:** tools return graph facts + line-bounded source slices; the agent
decides what to pull. Nothing in the agent layer knows COBOL vs Python/Java/Rust.

### New module: `src/code_context_graph/agent/`

- **`graph_tools.py`** — in-process SDK MCP server exposing read-only,
  language-agnostic tools:
  - `list_subsystems(repo)` → graph communities (clusters), each = list of entity IDs
  - `get_entity(repo, name)` / `find_entities(repo, kind|prefix)`
  - `neighbors(repo, entity, edge, direction, depth)` → CALLS/IMPORTS/CONTAINS/INHERITS traversal (wraps `queries.py`)
  - `get_source_slice(repo, entity)` → `file[start_line:end_line]` only — **never whole-file dumps**
  - `find_entry_points(repo)` / `find_integration_points(repo)` → graph-heuristic (below)
  - `graph_summary(repo)` → counts + top entities (reuses existing query)
- **`harness.py`** — thin wrapper around `claude_agent_sdk.query()` building
  `ClaudeAgentOptions` (tool set, model tier, `maxTurns`, read-only permissions).
- **`clustering.py`** — community detection in Python (networkx) over edges pulled
  from Neo4j. **No GDS/APOC dependency** (Neo4j Community Edition safe), works on any
  graph regardless of source language.
- **BRD orchestrator** — replaces the internals of `brd/generator.py`; `brd/pipeline.py`
  is rewired to call it.

### Reused unchanged

`Neo4jClient`, `CodeGraphQueries` (`queries.py`), `brd/schema.py` (Pydantic `BRD`),
`brd/storage.py`, `brd/renderer.py`, the `Judge` concept, all parsers, ingestion.

### Removed

`gemini_llm.py`; Gemini calls in `enrichment.py`, `llm_query.py`, `brd/generator.py`.

## BRD orchestration (Approach A)

```
1. PLAN     orchestrator → list_subsystems(repo)         [Python clustering, no LLM]
            → N communities, each a list of entity IDs + a centrality budget

2. MAP      for each subsystem → spawn a subagent (parallel, context-isolated)
              subagent prompt = subsystem name + its entity IDs + BRD-slice instructions
              subagent autonomously calls neighbors(), get_source_slice(),
                find_integration_points() scoped to its entities
              subagent returns a partial BRD (requirements + evidence_map)
              ONLY the partial BRD returns to the parent — not the slices it read

3. REDUCE   parent merges N partial BRDs → 11-section BRD
              dedup requirements, reconcile contradictions, preserve every evidence pointer

4. JUDGE    Judge agent scores groundedness/coverage → feedback → retry (existing loop)
```

This preserves the current map-reduce mental model but: clusters come from **graph
connectivity** not directories; retrieval is **on-demand and line-sliced** not
whole-repo; each subagent's exploration **stays out of the parent's context window**
(SDK context isolation — "the parent receives a concise summary, not every file the
subagent read").

**Subagent fan-out is bounded:** if clustering yields more communities than a
configured cap (default 12), small/peripheral communities merge by centrality.

## Language-agnostic heuristics

All graph-derived, zero language hardcoding:

| Concept | Generic rule (Python / Java / Rust / COBOL) |
|---|---|
| **Subsystem** | Connected components / label-propagation over CALLS+CONTAINS+IMPORTS edges. Python→packages, Java→package/class clusters, Rust→module/crate clusters, COBOL→program groups — all fall out of the same edge topology. |
| **Entry point** | Nodes with zero CALLS in-edges (roots) or high CALLS fan-in, plus `kind`-based hints (module-level callables, `main`/handler names). Ranked, never hardcoded to one language's convention. |
| **Integration point** | Nodes with `is_external=true`, IMPORTS edges crossing into `External` entities, or names matching a **configurable** registry of I/O markers (DB drivers, HTTP clients, DB2/IMS/MQ, file I/O). The registry is data, not code branches. |
| **Source slice** | `start_line`/`end_line` on the entity — identical mechanism for every parser. |

The only language-aware components remain the parsers (tree-sitter for
Py/Java/Rust/Go, ProLeap for COBOL) that populate the graph.

## Enrichment & Ask-the-Codebase on the same foundation

**Semantic enrichment** (replaces `enrichment.py` Gemini loop):
- Process entities in **centrality order**, batched, with **subagent fan-out**
  (Haiku-tier model). No 50-cap; **loop until exhausted**.
- Each batch agent gets the entity *and its graph neighborhood* via tools (not just
  the bare signature it gets today), so tags are grounded in how the entity is used.
- Writes `semantic_layer`/`patterns`/`concepts`/`summary` back via existing Cypher.
- Tags are architectural roles (presentation/business/data/infra) — language-neutral.

**Ask-the-Codebase** (replaces `llm_query.py` two-call flow) — kept focused, not
fully agentic:
- Keep the proven pattern: generate read-only Cypher → run → summarize, on the SDK
  substrate, with graph tools available as a **fallback** when one Cypher query can't
  answer (a few `neighbors()` hops then summarize).
- **Keep `enforce_read_only_cypher`** (`llm_query.py:79`) — `$repo` scoping +
  blocked-clause guard is a real safety control. All graph tools are read-only
  (no Write/Edit/Bash in `allowedTools`).
- Latency-sensitive: low `maxTurns` (3–4), cheaper model tier.

## Cross-cutting concerns

### Cost & determinism
- `maxTurns` per role: BRD subagent ~15, reduce ~10, enrichment batch ~3, ask ~4.
- **Model tiering**: Opus/Sonnet for BRD synthesis & judge, Haiku for enrichment &
  ask. Configurable via env.
- Subsystem cap (≤12) bounds fan-out. Per-role token accounting carried over from
  `generator.py:114`.

### Structured output
- BRD must stay valid JSON matching the Pydantic `BRD` schema. Subagents and the
  reduce step return via a **structured-output tool** (`emit_brd_slice(...)` with the
  schema) — no free-text JSON parsing. A formatting pass recovers a malformed slice.

### Error handling
- A subagent that fails (timeout / maxTurns) degrades to a stub slice (mirrors
  `generator.py:144`); the BRD still generates from surviving subsystems, gap logged.
- Tool errors (missing source file, unknown entity) return structured error payloads
  the agent can react to — not exceptions that kill the run.

### Testing
- Tool layer unit-tested directly against a seeded Neo4j (tools are plain functions).
- Agent paths tested with a **fake SDK transport / recorded transcripts** so tests
  run offline (as `tests/brd/` does today).
- **Language-matrix smoke test**: seed graphs from small Python, Java, Rust, and
  COBOL samples → assert a BRD generates with non-empty grounded requirements for
  each. This enforces the genericity constraint as a test, not a hope.

## Migration / file plan

- **New:** `src/code_context_graph/agent/{__init__,graph_tools,harness,clustering}.py`;
  new BRD orchestrator (replaces `brd/generator.py` internals; `brd/pipeline.py`
  rewired to call it).
- **Rewritten:** `enrichment.py`, `llm_query.py` (keep the Cypher guard).
- **Deleted:** `gemini_llm.py`.
- **Dependencies:** `pyproject.toml` — add `claude-agent-sdk` and `networkx` (for
  clustering). Gemini is currently called via raw `httpx` (no Gemini SDK package), so
  there is no dependency to drop; `httpx` stays (still used elsewhere).
- **Config:** `.env.example` — `ANTHROPIC_API_KEY`, model-tier vars, `maxTurns`,
  subsystem cap, integration-marker registry.
- **Unchanged:** `Neo4jClient`, `queries.py`, `brd/schema.py`, `storage.py`,
  `renderer.py`, parsers, ingestion.

## Sequenced build order

1. **Foundation** — `graph_tools.py` (+ `SourceSlicer`), `clustering.py`, `harness.py`;
   unit tests against seeded Neo4j.
2. **BRD** — orchestrator (Approach A), structured output, Judge wiring, `pipeline.py`
   rewire; language-matrix smoke test.
3. **Enrichment** — centrality-ordered, fan-out, loop-until-exhausted.
4. **Ask-the-Codebase** — Cypher-first with tool fallback; preserve the read-only guard.

## Out of scope (YAGNI)

- Standalone Neo4j MCP server (in-process only for now; `graph_tools` factored so it
  *could* be lifted later without rewrite, but that is not built now).
- Batched Neo4j writes / ingestion performance (separate concern, not this spec).
- Re-introducing a Gemini fallback (explicitly replacing, not flagging).
