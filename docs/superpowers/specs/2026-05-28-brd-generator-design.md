# BRD Generator with LLM-as-Judge — Design

**Date:** 2026-05-28
**Status:** Approved for implementation planning
**Owner:** cwijayasundara

## Summary

Add a feature that generates a comprehensive Business Requirements Document (BRD) from a repository previously ingested into Code Context Graph. The generator uses Claude Opus 4.7 (1M context) over the Neo4j graph plus full source tree, with an LLM-as-judge loop that scores the BRD on a five-dimension rubric and triggers up to two targeted regenerations when quality is medium or low. Output is a self-contained HTML file, also persisted as a `:BRD` node in Neo4j and exposed via CLI, API, and the Web UI.

## Goals

- One command (or button click) produces a high-quality BRD for any ingested repo.
- Quality is automatically validated; medium/low BRDs are regenerated with targeted feedback.
- BRDs are grounded in the actual graph + source — no hallucinated APIs or classes.
- Works on repos of any size, including ones that don't fit in a single 1M-token context window.
- BRDs are versioned and queryable from the existing UI.

## Non-goals

- Editing or human-in-the-loop refinement of generated BRDs (read-only artifact for now).
- PDF, DOCX, or Confluence export (HTML only).
- Multi-language BRDs (English only).
- Real-time collaborative editing.

## Inputs and outputs

**Input:** A `repo_id` (or local path resolvable to a `:Repository` in Neo4j) that has been ingested.

**Output:**
- A self-contained `BRD.html` file under `<BRD_OUTPUT_DIR>/brd/<repo_slug>/v<version>.html`.
- A `:BRD` node attached to the `:Repository` in Neo4j with metadata (rating, scores, attempts, model, strategy, token usage, attempt history).
- A `BRDResult` Python object returned from the public API (path, brd_id, rating, attempts, per-attempt judge reports).

## BRD content

Standard BRD, eleven sections:

1. Executive Summary
2. Business Objectives
3. Scope (in-scope / out-of-scope)
4. Stakeholders
5. Functional Requirements
6. Non-functional Requirements
7. Data & Integrations
8. Assumptions
9. Constraints
10. Risks
11. Success Metrics

Each requirement carries an **evidence pointer** — a list of graph entity IDs (e.g. `Function:src/foo.py:bar`) and/or source file paths it was grounded in. The full BRD therefore includes an `evidence_map: dict[requirement_id, list[entity_or_path]]` used both for traceability in the HTML render and for the judge's hard groundedness check.

## Architecture

New subpackage `src/code_context_graph/brd/`:

```
brd/
  __init__.py
  pipeline.py        # orchestrator: generate -> judge -> (retry|finalize)
  context_builder.py # graph + source -> prompt context; chunker
  generator.py       # single-shot, map(cluster), reduce(merge) calls
  judge.py           # rubric scoring -> rating + feedback
  renderer.py        # markdown(internal) -> self-contained HTML
  storage.py         # Neo4j BRD node + on-disk HTML
  schema.py          # Pydantic types: BRD, JudgeReport, BRDResult, etc.
```

Public entrypoint:

```python
def generate_brd(
    repo_id: str,
    *,
    max_retries: int = 2,
    force_map_reduce: bool = False,
) -> BRDResult
```

The CLI, API, and Web UI all call into this single entrypoint.

## Data flow

1. `pipeline.generate(repo_id, max_retries=2)` is invoked.
2. `context_builder.build(repo_id)` queries Neo4j for the repo subgraph, ranks files by graph centrality
   (`degree(callers) + degree(callees) + degree(importers)`), loads source from disk, and estimates token count.
   - If estimate ≤ `BRD_SINGLE_SHOT_TOKEN_BUDGET` (default 800,000, leaving headroom under the 1M limit):
     **single-shot strategy** — emit one prompt with the full graph summary + source.
   - Else: **map-reduce strategy** — cluster nodes by top-level package/directory; each cluster prompt
     contains that cluster's graph slice + source. Each cluster emits a `SubBRD` (same sections, scoped).
     A final reduce prompt merges sub-BRDs into the final BRD, deduping and reconciling cross-cluster items.
   - If a single cluster still exceeds the budget, it is recursively split by sub-directory until each
     fits, up to `BRD_MAX_CLUSTER_DEPTH` (default 4). A cluster that cannot be split further and still
     overruns is summarized via a separate file-by-file summarization pass before entering reduce.
3. `generator.generate(context, prior_attempt=None)` runs the chosen strategy and returns a Markdown BRD
   plus structured metadata (sections, evidence map). On retry, the prior BRD and judge feedback are
   passed in as targeted revision guidance.
4. `judge.evaluate(brd, context)` runs the hard groundedness check, then scores five dimensions, returns
   a `JudgeReport` with dimension scores, weighted score, rating, and structured feedback items.
5. If `rating == "high"` or `attempts == max_retries + 1`: finalize. Otherwise loop with feedback.
6. `renderer.to_html(brd)` produces a self-contained HTML (inlined CSS, no external assets).
7. `storage.save(repo_id, html, judge_report, attempts)` writes the HTML file and creates/updates the
   `:BRD` node, incrementing `version`.

## Judge rubric

Five dimensions, each rated 1–5 by Claude with a short per-score rationale:

| Dimension | Weight | What it measures |
|---|---|---|
| Completeness | 0.25 | All 11 sections present and substantive |
| Accuracy / Groundedness | 0.30 | Every claim ties to real graph entities or source code; no hallucinations |
| Clarity | 0.15 | Readable, unambiguous; no undefined jargon |
| Consistency | 0.15 | No contradictions across sections; scope matches requirements |
| Actionability | 0.15 | Requirements are testable; success metrics are concrete |

Weighted score = `Σ(score_i × weight_i)`, on a 1–5 scale, mapped to:

- **high**: weighted_score ≥ 4.2 AND no dimension < 3
- **medium**: weighted_score ≥ 3.2 AND no dimension < 2
- **low**: otherwise

### Hard groundedness check (pre-rubric)

Before scoring, the judge deterministically verifies that every named entity (class/function/file)
referenced in the BRD's evidence map exists in the graph context passed to the generator. Unrecognized
entities are flagged as hallucinations and force Accuracy ≤ 2 regardless of the LLM's score. This
catches the most damaging failure mode cheaply and without LLM ambiguity.

### Structured feedback

Each judge run returns `feedback_items: list[{dimension, severity, suggestion, target_section}]`.
The next regeneration prompt receives this list verbatim, so retries are targeted rather than random.

## Storage schema

**Neo4j node** — new label `:BRD`:

| Attribute | Type | Notes |
|---|---|---|
| `id` | string (uuid) | Primary key |
| `repo_id` | string | FK to `:Repository` |
| `version` | int | Increments per re-run; latest = max(version) |
| `html` | string | Rendered, self-contained HTML |
| `rating` | string | `high` \| `medium` \| `low` |
| `weighted_score` | float | 1.0–5.0 |
| `dimensions` | json | Per-dimension scores |
| `attempts` | int | Total generation attempts |
| `attempt_history` | json | Per-attempt rating + feedback |
| `model` | string | e.g. `claude-opus-4-7[1m]` |
| `strategy` | string | `single_shot` \| `map_reduce` |
| `token_usage` | json | input / output / cache_read / cache_write |
| `created_at` | datetime | |

Relationship: `(:Repository)-[:HAS_BRD]->(:BRD)`. Multiple `:BRD` nodes per repo allowed (versioned).

**Disk:** `<BRD_OUTPUT_DIR>/brd/<repo_slug>/v<version>.html`.

## Surface area

### CLI

```
ccg brd <repo-id-or-path> [--max-retries 2] [--force-map-reduce]
                          [--output-dir ./brd_output] [--open]
```

- Resolves `repo-id-or-path` (path → looks up `:Repository` by absolute path in Neo4j).
- Streams progress to stdout: tokens estimated → strategy chosen → attempt N generation → judge rating → retry/done.
- `--open` opens the resulting HTML in the default browser.
- Exit codes: `0` if `rating=high`, `1` if `medium` after retries, `2` if `low` after retries, non-zero on hard errors.

### API (FastAPI)

| Method | Path | Behavior |
|---|---|---|
| `POST` | `/api/repos/{repo_id}/brd?max_retries={n}&force_map_reduce={bool}` | Starts a generation in a background task; returns `{ brd_id, status: "running" }`. Both query params optional, default to env config |
| `GET`  | `/api/repos/{repo_id}/brd` | Latest BRD summary (rating, attempts, version, created_at) + paginated attempt_history |
| `GET`  | `/api/repos/{repo_id}/brd?all=true` | List of all versions for the repo |
| `GET`  | `/api/repos/{repo_id}/brd/{brd_id}/html` | Raw HTML, served as `Content-Type: text/html` |

Background-task pattern reuses the same approach as ingestion.

### Web UI

- "Generate BRD" button on the repo detail page.
- Sidebar shows: latest rating badge (high/medium/low), attempts count, version, "Re-generate" button.
- Main panel renders the HTML in a sandboxed iframe (`srcdoc=`) so inline styles don't leak into the app's CSS.
- Below the BRD: collapsible "Judge report" with final dimension scores and feedback from each attempt
  — exposes *why* a re-generation happened.

## Error handling

Boundary-only. No over-validation of internal code.

- **Anthropic API errors:** bubble up with attempt context. SDK-level retries handle transient network/API errors; pipeline-level retries are reserved for judge-driven regeneration.
- **Token estimation overrun:** caught in `context_builder`; falls back to map-reduce automatically.
- **Map step failure (one cluster):** that cluster's slot in the reduce prompt becomes `"<cluster failed to generate; partial>"`. The BRD will likely be downgraded by the judge — preserves transparency over silent gaps.
- **Neo4j write failure after successful generation:** HTML is still written to disk, error surfaced; the user can rerun storage independently without re-paying for generation.
- **Hallucinated entity in BRD:** caught by the hard groundedness check, drives Accuracy ≤ 2, triggers retry naturally.

## Testing

| Test file | What it covers |
|---|---|
| `tests/brd/test_context_builder.py` | single-shot vs map-reduce decision, cluster boundaries, centrality ranking, token estimation |
| `tests/brd/test_judge.py` | rubric math, threshold edges (4.2, 3.2), hard groundedness check (entity not in graph → forces Accuracy ≤ 2), feedback structure |
| `tests/brd/test_pipeline.py` | retry loop with stubbed generator+judge: low→medium→high happy path, low→low→low max-retries returns best attempt with warning, generator exception propagates |
| `tests/brd/test_renderer.py` | HTML is self-contained (no external `<link>` / `<script src=>`), well-formed, escapes user-supplied content from source |
| `tests/brd/test_storage.py` | Neo4j round-trip, versioning increments, file written, idempotency |
| `tests/brd/test_api.py` | endpoints with the BRD pipeline mocked |

One end-to-end test against `source_code_to_analyse/` (small fixture repo) using a recorded Claude response (cassette pattern) so CI doesn't spend tokens.

## Configuration

Added to `.env.example`:

```
ANTHROPIC_API_KEY=...            # already present
BRD_MODEL=claude-opus-4-7        # supports [1m] suffix for 1M context
BRD_OUTPUT_DIR=./brd_output
BRD_MAX_RETRIES=2
BRD_SINGLE_SHOT_TOKEN_BUDGET=800000
BRD_MAX_CLUSTER_DEPTH=4
```

## Open questions

None at design time. Open issues will be tracked in the implementation plan.
