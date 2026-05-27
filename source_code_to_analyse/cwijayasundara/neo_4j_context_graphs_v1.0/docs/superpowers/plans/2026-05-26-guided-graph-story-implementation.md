# Guided Graph Story Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a readable guided graph story mode with presets while keeping full Neo4j exploration available.

**Architecture:** Add a bounded backend graph-slice endpoint keyed by preset, then update the Graph page to request slices instead of loading the whole database by default. Reuse `ContextGraphView` as the renderer and keep existing node inspection and expansion behavior intact.

**Tech Stack:** FastAPI, Neo4j Python driver, pytest, Next.js App Router, React, Chakra UI, Neo4j NVL.

---

## File Structure

- Modify `backend/app/routes_graph.py`: add preset definitions, graph serialization helpers, and `/api/graph/story`.
- Modify `backend/tests/test_routes_graph.py`: cover the story endpoint and route ordering.
- Modify `frontend/lib/config.ts`: add preset metadata and graph response types.
- Modify `frontend/app/graph/page.tsx`: add left preset rail, fetch selected preset, display counts and error states.
- Modify `frontend/components/ContextGraphView.tsx`: accept a subtitle, reset selected state when graph data changes, and improve captions/sizing for readable slices.

---

### Task 1: Backend Graph Story Endpoint

**Files:**
- Modify: `backend/app/routes_graph.py`
- Test: `backend/tests/test_routes_graph.py`

- [ ] **Step 1: Write the failing backend test**

Add tests that call `routes_graph.graph_story(preset="overview", limit=10)` with fake Neo4j rows and assert the response includes `nodes`, `relationships`, `results`, `preset`, and `stats`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest backend/tests/test_routes_graph.py -q`

Expected: failure because `graph_story` does not exist.

- [ ] **Step 3: Implement endpoint**

Add `GRAPH_STORY_PRESETS` mapping with Cypher for `overview`, `accounts`, `spending`, `merchants`, `categories`, `statements`, and `explore-all`. Add a `/story` route that executes the selected query, serializes all returned nodes and relationships, and returns aggregate stats.

- [ ] **Step 4: Run backend tests**

Run: `uv run pytest backend/tests/test_routes_graph.py backend/tests/test_routes.py -q`

Expected: all tests pass.

---

### Task 2: Frontend Preset Rail And Slice Fetching

**Files:**
- Modify: `frontend/lib/config.ts`
- Modify: `frontend/app/graph/page.tsx`

- [ ] **Step 1: Add frontend preset metadata**

Add a `GRAPH_PRESETS` array with ids and labels matching the backend preset names.

- [ ] **Step 2: Replace default all-graph fetch**

Update `GraphPage` so it owns `selectedPreset`, fetches `/api/graph/story?preset=${selectedPreset}`, and renders a compact left rail. Keep `Explore All` as a preset instead of hidden behavior.

- [ ] **Step 3: Handle preset-specific empty and error states**

Error messages should include the selected preset label. Empty states should say that the selected graph slice has no data and suggest Explore All or ingestion.

- [ ] **Step 4: Run frontend build**

Run: `npm run build`

Expected: build passes.

---

### Task 3: Renderer Readability Improvements

**Files:**
- Modify: `frontend/components/ContextGraphView.tsx`
- Modify: `frontend/lib/config.ts`

- [ ] **Step 1: Improve node captions**

Prefer useful finance labels in caption order: `name`, `merchant`, `raw_description`, `id`, `label`, `title`, label fallback. Trim long captions.

- [ ] **Step 2: Tune graph display for story slices**

Increase major entity node sizes, reduce transaction node size, and hide relationship captions for dense transaction edges except when selected.

- [ ] **Step 3: Reset selection on data change**

Ensure selection clears when switching presets so stale details do not remain visible.

- [ ] **Step 4: Run frontend build**

Run: `npm run build`

Expected: build passes.

---

### Task 4: Verification

**Files:**
- No new files.

- [ ] **Step 1: Backend tests**

Run: `uv run pytest backend/tests/test_routes_graph.py backend/tests/test_routes.py -q`

Expected: all tests pass.

- [ ] **Step 2: Frontend build**

Run: `npm run build`

Expected: build passes.

- [ ] **Step 3: Live API smoke if backend is running**

Run: `curl -s 'http://127.0.0.1:8000/api/graph/story?preset=overview'`

Expected: non-empty `nodes` for an ingested Neo4j database. If backend is not running, report that live API smoke was skipped.
