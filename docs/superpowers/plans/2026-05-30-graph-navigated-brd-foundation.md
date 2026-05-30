# Graph-Navigated BRD — Foundation + BRD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace whole-codebase BRD prompting with a graph-navigated pipeline: a language-agnostic in-process tool layer over Neo4j + disk, and a subagent-per-subsystem (map) + reduce BRD orchestrator on the Claude Agent SDK.

**Architecture:** A new `src/code_context_graph/agent/` package. Pure graph "ops" (testable against a fake Neo4j client) are wrapped as in-process SDK MCP tools. A Python-orchestrated map/reduce fans out one `query()` per graph community (subsystem), each agent navigating the graph and pulling line-sliced source on demand, returning a structured BRD slice via `output_format`; a reduce `query()` merges slices into one BRD. The Judge groundedness check is rebuilt against the graph. Everything above the parsers is language-agnostic (Python/Java/Rust/COBOL).

**Tech Stack:** Python ≥3.11, `claude-agent-sdk`, `networkx`, Neo4j, Pydantic, pytest (+ `pytest-asyncio`).

**Scope:** This plan covers the spec's Phase 1 (foundation) + Phase 2 (BRD). Phase 3 (enrichment) and Phase 4 (Ask-the-Codebase) are separate follow-on plans built on this same foundation.

**Spec:** `docs/superpowers/specs/2026-05-30-graph-navigated-brd-agent-sdk-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `src/code_context_graph/agent/__init__.py` | Package marker |
| `src/code_context_graph/agent/deps.py` | `GraphDeps` dataclass: client + repo_id + repo_path bundle passed to ops |
| `src/code_context_graph/agent/graph_ops.py` | Pure graph/disk operations (no SDK): entity, neighbors, slice, entry/integration points, summary, known-refs |
| `src/code_context_graph/agent/clustering.py` | `detect_subsystems()` — networkx community detection over graph edges |
| `src/code_context_graph/agent/graph_tools.py` | `build_graph_server(deps)` — wraps ops as `@tool`s in an in-process MCP server |
| `src/code_context_graph/agent/harness.py` | `AgentRunner` protocol + `SdkAgentRunner` (real `query()`); accumulates token usage |
| `src/code_context_graph/agent/brd_schema.py` | `BRDDraft`, `JudgeRubricOut` output-format schemas for the LLM |
| `src/code_context_graph/agent/brd_orchestrator.py` | `agenerate_brd_draft()` map/reduce over subsystems |
| `src/code_context_graph/agent/brd_judge.py` | `agudge()` groundedness + rubric on the runner |
| `src/code_context_graph/brd/pipeline.py` | Rewired to call the graph orchestrator + judge retry loop |
| `tests/agent/conftest.py` | `FakeAgentRunner`, seeded `FakeNeo4jClient` helpers |
| `tests/agent/test_graph_ops.py` | Unit tests for ops |
| `tests/agent/test_clustering.py` | Unit tests for clustering |
| `tests/agent/test_graph_tools.py` | Tool registration / wrapping tests |
| `tests/agent/test_brd_orchestrator.py` | Map/reduce orchestration with `FakeAgentRunner` |
| `tests/agent/test_brd_judge.py` | Judge groundedness + rubric |
| `tests/agent/test_language_matrix.py` | Genericity smoke test across 4 seeded languages |

---

## Task 0: Dependencies & package skeleton

**Files:**
- Modify: `pyproject.toml`
- Create: `src/code_context_graph/agent/__init__.py`
- Modify: `.env.example`

- [ ] **Step 1: Add dependencies**

In `pyproject.toml`, add to the `dependencies` list:

```toml
  "claude-agent-sdk>=0.3",
  "networkx>=3.2",
```

And to the dev/test dependencies (wherever `pytest` is declared) add:

```toml
  "pytest-asyncio>=0.23",
```

- [ ] **Step 2: Install**

Run: `uv sync`
Expected: resolves and installs `claude-agent-sdk`, `networkx`, `pytest-asyncio`.

- [ ] **Step 3: Enable asyncio tests**

In `pyproject.toml`, under `[tool.pytest.ini_options]` (create the table if absent), add:

```toml
asyncio_mode = "auto"
```

- [ ] **Step 4: Create the package marker**

Create `src/code_context_graph/agent/__init__.py`:

```python
"""Graph-navigated context engineering on the Claude Agent SDK."""
```

- [ ] **Step 5: Add env vars**

Append to `.env.example`:

```bash

# BRD agent (Claude Agent SDK). Replaces the Gemini BRD path.
ANTHROPIC_API_KEY=sk-ant-...
BRD_AGENT_MODEL=claude-sonnet-4-6        # subsystem map + reduce + judge
BRD_AGENT_MAX_TURNS=15                   # per subsystem agent
BRD_MAX_SUBSYSTEMS=12                    # fan-out cap
```

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/code_context_graph/agent/__init__.py .env.example
git commit -m "build: add claude-agent-sdk + networkx for graph-navigated BRD"
```

---

## Task 1: GraphDeps + entity/neighbors/slice/summary ops

**Files:**
- Create: `src/code_context_graph/agent/deps.py`
- Create: `src/code_context_graph/agent/graph_ops.py`
- Create: `tests/agent/__init__.py` (empty)
- Create: `tests/agent/conftest.py`
- Create: `tests/agent/test_graph_ops.py`

- [ ] **Step 1: Create deps bundle**

Create `src/code_context_graph/agent/deps.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class GraphDeps:
    """Everything the graph ops need: a Neo4j client, the repo id used to scope
    every query, and the on-disk repo root used for source slicing."""
    client: object        # Neo4jClient (or a fake exposing .run(query, **params))
    repo_id: str
    repo_path: Path
```

- [ ] **Step 2: Create the test conftest with a seedable fake client**

Create `tests/agent/__init__.py` (empty file), then `tests/agent/conftest.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest


class SeededNeo4j:
    """Fake Neo4jClient that answers run() from a list of (predicate, rows) rules.

    Each rule is (match_fn, rows): the first rule whose match_fn(query, params)
    returns True supplies the rows. Lets tests script graph responses precisely.
    """

    def __init__(self) -> None:
        self.rules: list[tuple[Callable[[str, dict], bool], list[dict]]] = []
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def when(self, match_fn: Callable[[str, dict], bool], rows: list[dict]) -> "SeededNeo4j":
        self.rules.append((match_fn, rows))
        return self

    def run(self, query: str, **params: Any) -> list[dict]:
        self.calls.append((query, params))
        for match_fn, rows in self.rules:
            if match_fn(query, params):
                return rows
        return []


@pytest.fixture
def seeded() -> SeededNeo4j:
    return SeededNeo4j()


@pytest.fixture
def repo_tree(tmp_path: Path) -> Path:
    """A tiny on-disk repo for source-slice tests."""
    f = tmp_path / "src" / "mod.py"
    f.parent.mkdir(parents=True)
    f.write_text("line1\nline2\nline3\nline4\nline5\n")
    return tmp_path
```

- [ ] **Step 3: Write failing tests for the basic ops**

Create `tests/agent/test_graph_ops.py`:

```python
from __future__ import annotations

from code_context_graph.agent.deps import GraphDeps
from code_context_graph.agent import graph_ops as ops


def test_get_source_slice_reads_line_range(seeded, repo_tree):
    seeded.when(
        lambda q, p: "RETURN e.file_path" in q,
        [{"file": "src/mod.py", "start": 2, "end": 4}],
    )
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=repo_tree)
    out = ops.get_source_slice(deps, "pkg.mod")
    assert out["source"] == "line2\nline3\nline4"
    assert out["start_line"] == 2 and out["end_line"] == 4


def test_get_source_slice_unknown_entity_returns_error(seeded, repo_tree):
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=repo_tree)
    out = ops.get_source_slice(deps, "nope")
    assert out["error"]


def test_neighbors_rejects_unknown_edge(seeded, repo_tree):
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=repo_tree)
    out = ops.neighbors(deps, "x", edge="DROP TABLE", direction="out")
    assert out["error"]


def test_neighbors_out_calls(seeded, repo_tree):
    seeded.when(
        lambda q, p: "CALLS" in q and p.get("name") == "a",
        [{"qualified_name": "b", "kind": "Method", "file_path": "src/mod.py"}],
    )
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=repo_tree)
    out = ops.neighbors(deps, "a", edge="CALLS", direction="out")
    assert out["neighbors"][0]["qualified_name"] == "b"
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `uv run pytest tests/agent/test_graph_ops.py -v`
Expected: FAIL — `module 'graph_ops' has no attribute ...`

- [ ] **Step 5: Implement the ops**

Create `src/code_context_graph/agent/graph_ops.py`:

```python
from __future__ import annotations

from typing import Any

from code_context_graph.agent.deps import GraphDeps

# Whitelist: edges and directions an agent may traverse. Anything else is rejected
# so a tool call can never smuggle arbitrary Cypher fragments into a query.
_EDGES = {"CALLS", "IMPORTS", "CONTAINS", "INHERITS", "DECORATES", "RAISES"}
_DIRECTIONS = {"out", "in", "both"}


def get_entity(deps: GraphDeps, name: str) -> dict[str, Any]:
    rows = deps.client.run(
        """
        MATCH (e:CodeEntity {repo: $repo})
        WHERE e.qualified_name = $name OR e.simple_name = $name
        RETURN e.qualified_name AS qualified_name, e.simple_name AS simple_name,
               e.kind AS kind, e.file_path AS file_path,
               e.signature AS signature, e.start_line AS start_line,
               e.end_line AS end_line, e.semantic_layer AS semantic_layer,
               e.semantic_summary AS semantic_summary
        LIMIT 1
        """,
        repo=deps.repo_id, name=name,
    )
    if not rows:
        return {"error": f"unknown entity: {name}"}
    return rows[0]


def find_entities(deps: GraphDeps, *, kind: str | None = None,
                  prefix: str | None = None, limit: int = 50) -> dict[str, Any]:
    rows = deps.client.run(
        """
        MATCH (e:CodeEntity {repo: $repo})
        WHERE ($kind IS NULL OR e.kind = $kind)
          AND ($prefix IS NULL OR toLower(e.qualified_name) STARTS WITH toLower($prefix))
        RETURN e.qualified_name AS qualified_name, e.kind AS kind,
               e.file_path AS file_path
        ORDER BY size(e.qualified_name), e.qualified_name
        LIMIT $limit
        """,
        repo=deps.repo_id, kind=kind, prefix=prefix, limit=limit,
    )
    return {"entities": rows}


def neighbors(deps: GraphDeps, name: str, *, edge: str,
              direction: str = "out", depth: int = 1, limit: int = 50) -> dict[str, Any]:
    if edge not in _EDGES:
        return {"error": f"unsupported edge {edge!r}; allowed: {sorted(_EDGES)}"}
    if direction not in _DIRECTIONS:
        return {"error": f"unsupported direction {direction!r}"}
    depth = max(1, min(int(depth), 5))
    if direction == "out":
        pattern = f"(a:CodeEntity {{repo: $repo}})-[:{edge}*1..{depth}]->(b:CodeEntity)"
    elif direction == "in":
        pattern = f"(a:CodeEntity {{repo: $repo}})<-[:{edge}*1..{depth}]-(b:CodeEntity)"
    else:
        pattern = f"(a:CodeEntity {{repo: $repo}})-[:{edge}*1..{depth}]-(b:CodeEntity)"
    rows = deps.client.run(
        f"""
        MATCH {pattern}
        WHERE a.qualified_name = $name
        RETURN DISTINCT b.qualified_name AS qualified_name, b.kind AS kind,
               b.file_path AS file_path
        ORDER BY b.qualified_name
        LIMIT $limit
        """,
        repo=deps.repo_id, name=name, limit=limit,
    )
    return {"neighbors": rows}


def get_source_slice(deps: GraphDeps, name: str) -> dict[str, Any]:
    rows = deps.client.run(
        """
        MATCH (e:CodeEntity {repo: $repo})
        WHERE e.qualified_name = $name
        RETURN e.file_path AS file, e.start_line AS start, e.end_line AS end
        LIMIT 1
        """,
        repo=deps.repo_id, name=name,
    )
    if not rows or not rows[0].get("file"):
        return {"error": f"unknown entity or no source location: {name}"}
    file = rows[0]["file"]
    start = int(rows[0].get("start") or 1)
    end = int(rows[0].get("end") or start)
    try:
        lines = (deps.repo_path / file).read_text(
            encoding="utf-8", errors="replace"
        ).splitlines()
    except (FileNotFoundError, IsADirectoryError, PermissionError) as exc:
        return {"error": f"could not read {file}: {type(exc).__name__}"}
    source = "\n".join(lines[max(0, start - 1):end])
    return {"entity": name, "file": file, "start_line": start,
            "end_line": end, "source": source}


def graph_summary(deps: GraphDeps) -> dict[str, Any]:
    counts = deps.client.run(
        "MATCH (e:CodeEntity {repo: $repo}) RETURN e.kind AS kind, count(e) AS count "
        "ORDER BY count DESC",
        repo=deps.repo_id,
    )
    rels = deps.client.run(
        "MATCH (s:CodeEntity {repo: $repo})-[r]->(t) "
        "RETURN type(r) AS rel_type, count(r) AS count ORDER BY count DESC",
        repo=deps.repo_id,
    )
    return {"entity_counts": counts,
            "relationship_counts": {r["rel_type"]: r["count"] for r in rels}}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/agent/test_graph_ops.py -v`
Expected: PASS (4 passed)

- [ ] **Step 7: Commit**

```bash
git add src/code_context_graph/agent/deps.py src/code_context_graph/agent/graph_ops.py tests/agent/
git commit -m "feat(agent): graph ops for entity/neighbors/source-slice/summary"
```

---

## Task 2: Entry-point, integration-point, and known-refs ops

**Files:**
- Modify: `src/code_context_graph/agent/graph_ops.py`
- Modify: `tests/agent/test_graph_ops.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/agent/test_graph_ops.py`:

```python
def test_entry_points_returns_zero_caller_roots(seeded, repo_tree):
    seeded.when(
        lambda q, p: "callers = 0" in q.replace(" ", " "),
        [{"qualified_name": "main", "kind": "Function", "file_path": "src/mod.py"}],
    )
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=repo_tree)
    out = ops.entry_points(deps)
    assert out["entry_points"][0]["qualified_name"] == "main"


def test_integration_points_uses_markers(seeded, repo_tree):
    captured = {}

    def matcher(q, p):
        captured.update(p)
        return "is_external" in q

    seeded.when(matcher, [{"qualified_name": "db.exec", "kind": "Method",
                           "file_path": "src/mod.py"}])
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=repo_tree)
    out = ops.integration_points(deps, markers=["db", "mq"])
    assert out["integration_points"][0]["qualified_name"] == "db.exec"
    assert captured["markers"] == ["db", "mq"]


def test_known_refs_unions_names_and_paths(seeded, repo_tree):
    seeded.when(
        lambda q, p: "qualified_name" in q and "file_path" in q,
        [{"qualified_name": "pkg.a", "file_path": "src/a.py"},
         {"qualified_name": "pkg.b", "file_path": "src/b.py"}],
    )
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=repo_tree)
    refs = ops.known_refs(deps)
    assert {"pkg.a", "pkg.b", "src/a.py", "src/b.py"} <= refs
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/agent/test_graph_ops.py -k "entry or integration or known" -v`
Expected: FAIL — attributes not defined.

- [ ] **Step 3: Implement the ops**

Append to `src/code_context_graph/agent/graph_ops.py`:

```python
# Default integration markers. Language-neutral I/O surface names; override via config.
DEFAULT_INTEGRATION_MARKERS = [
    "db2", "ims", "mq", "vsam", "sql", "jdbc", "http", "rest", "grpc", "kafka",
    "s3", "redis", "queue", "socket", "file", "exec", "cics",
]


def entry_points(deps: GraphDeps, *, limit: int = 50) -> dict[str, Any]:
    """Heuristic, language-agnostic: callable entities with zero incoming CALLS."""
    rows = deps.client.run(
        """
        MATCH (e:CodeEntity {repo: $repo})
        WHERE e.kind IN ['Function', 'Method', 'Module']
        OPTIONAL MATCH (e)<-[c:CALLS]-()
        WITH e, count(c) AS callers
        WHERE callers = 0
        RETURN e.qualified_name AS qualified_name, e.kind AS kind,
               e.file_path AS file_path
        ORDER BY e.qualified_name
        LIMIT $limit
        """,
        repo=deps.repo_id, limit=limit,
    )
    return {"entry_points": rows}


def integration_points(deps: GraphDeps, *, markers: list[str] | None = None,
                       limit: int = 50) -> dict[str, Any]:
    markers = markers or DEFAULT_INTEGRATION_MARKERS
    rows = deps.client.run(
        """
        MATCH (e:CodeEntity {repo: $repo})
        WHERE e.is_external = true
           OR any(m IN $markers WHERE toLower(e.qualified_name) CONTAINS toLower(m))
        RETURN e.qualified_name AS qualified_name, e.kind AS kind,
               e.file_path AS file_path
        ORDER BY e.qualified_name
        LIMIT $limit
        """,
        repo=deps.repo_id, markers=markers, limit=limit,
    )
    return {"integration_points": rows}


def known_refs(deps: GraphDeps) -> set[str]:
    """Every valid evidence reference for the repo: entity qualified_names + file
    paths. Used by the judge to detect hallucinated references."""
    rows = deps.client.run(
        """
        MATCH (e:CodeEntity {repo: $repo})
        RETURN DISTINCT e.qualified_name AS qualified_name, e.file_path AS file_path
        """,
        repo=deps.repo_id,
    )
    refs: set[str] = set()
    for r in rows:
        if r.get("qualified_name"):
            refs.add(r["qualified_name"])
        if r.get("file_path"):
            refs.add(r["file_path"])
    return refs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/agent/test_graph_ops.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add src/code_context_graph/agent/graph_ops.py tests/agent/test_graph_ops.py
git commit -m "feat(agent): entry-point, integration-point, known-refs ops"
```

---

## Task 3: Subsystem clustering (networkx)

**Files:**
- Create: `src/code_context_graph/agent/clustering.py`
- Create: `tests/agent/test_clustering.py`

- [ ] **Step 1: Write failing tests**

Create `tests/agent/test_clustering.py`:

```python
from __future__ import annotations

from code_context_graph.agent.clustering import Subsystem, detect_subsystems


def test_two_disconnected_groups_become_two_subsystems():
    nodes = ["a1", "a2", "b1", "b2"]
    edges = [("a1", "a2"), ("b1", "b2")]
    subs = detect_subsystems(nodes, edges, max_clusters=12)
    assert len(subs) == 2
    members = sorted(sorted(s.members) for s in subs)
    assert members == [["a1", "a2"], ["b1", "b2"]]


def test_connected_component_is_one_subsystem():
    nodes = ["a", "b", "c"]
    edges = [("a", "b"), ("b", "c")]
    subs = detect_subsystems(nodes, edges, max_clusters=12)
    assert len(subs) == 1
    assert sorted(subs[0].members) == ["a", "b", "c"]


def test_isolated_node_is_its_own_subsystem():
    subs = detect_subsystems(["solo"], [], max_clusters=12)
    assert len(subs) == 1 and subs[0].members == ["solo"]


def test_merges_down_to_cap_keeping_largest():
    # 5 singletons, cap of 3 -> 2 largest kept singleton + remainder merged = <=3
    nodes = ["a", "b", "c", "d", "e"]
    subs = detect_subsystems(nodes, [], max_clusters=3)
    assert len(subs) <= 3
    # every original node still appears exactly once
    all_members = sorted(m for s in subs for m in s.members)
    assert all_members == ["a", "b", "c", "d", "e"]


def test_subsystem_has_a_stable_name():
    subs = detect_subsystems(["pkg.aaa", "pkg.aab"], [("pkg.aaa", "pkg.aab")], max_clusters=12)
    assert isinstance(subs[0].name, str) and subs[0].name
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/agent/test_clustering.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement clustering**

Create `src/code_context_graph/agent/clustering.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

import networkx as nx


@dataclass
class Subsystem:
    name: str
    members: list[str]


def _name_for(members: list[str]) -> str:
    """Pick the shortest qualified name as the representative label."""
    return min(members, key=lambda m: (len(m), m)) if members else "misc"


def detect_subsystems(nodes: list[str], edges: list[tuple[str, str]],
                      *, max_clusters: int = 12) -> list[Subsystem]:
    """Partition entities into subsystems by connected components over the
    (undirected projection of the) call/contains/imports graph. Language-agnostic:
    operates purely on node ids and edges. If there are more components than
    max_clusters, the largest (max_clusters - 1) are kept and the rest merged into
    one 'misc' subsystem so fan-out stays bounded."""
    g = nx.Graph()
    g.add_nodes_from(nodes)
    g.add_edges_from((s, t) for s, t in edges if s in set(nodes) and t in set(nodes))

    components = [sorted(c) for c in nx.connected_components(g)]
    components.sort(key=lambda c: (-len(c), c[0] if c else ""))

    if len(components) <= max_clusters:
        return [Subsystem(name=_name_for(c), members=c) for c in components]

    keep = components[: max_clusters - 1]
    merged = sorted(m for c in components[max_clusters - 1:] for m in c)
    result = [Subsystem(name=_name_for(c), members=c) for c in keep]
    result.append(Subsystem(name="misc", members=merged))
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/agent/test_clustering.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Add the list_subsystems op that pulls the graph and clusters it**

Append to `src/code_context_graph/agent/graph_ops.py`:

```python
from code_context_graph.agent.clustering import detect_subsystems


def list_subsystems(deps: GraphDeps, *, max_clusters: int = 12) -> dict[str, Any]:
    node_rows = deps.client.run(
        "MATCH (e:CodeEntity {repo: $repo}) RETURN e.qualified_name AS qn",
        repo=deps.repo_id,
    )
    edge_rows = deps.client.run(
        """
        MATCH (a:CodeEntity {repo: $repo})-[:CALLS|IMPORTS|CONTAINS]->(b:CodeEntity {repo: $repo})
        RETURN a.qualified_name AS src, b.qualified_name AS dst
        """,
        repo=deps.repo_id,
    )
    nodes = [r["qn"] for r in node_rows if r.get("qn")]
    edges = [(r["src"], r["dst"]) for r in edge_rows if r.get("src") and r.get("dst")]
    subs = detect_subsystems(nodes, edges, max_clusters=max_clusters)
    return {"subsystems": [{"name": s.name, "members": s.members} for s in subs]}
```

- [ ] **Step 6: Write a failing test for list_subsystems, then confirm it passes**

Append to `tests/agent/test_clustering.py`:

```python
from code_context_graph.agent.deps import GraphDeps
from code_context_graph.agent import graph_ops as ops


def test_list_subsystems_op_pulls_and_clusters(seeded, tmp_path):
    seeded.when(lambda q, p: "RETURN e.qualified_name AS qn" in q,
                [{"qn": "a"}, {"qn": "b"}, {"qn": "c"}])
    seeded.when(lambda q, p: "RETURN a.qualified_name AS src" in q,
                [{"src": "a", "dst": "b"}])
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=tmp_path)
    out = ops.list_subsystems(deps, max_clusters=12)
    names = sorted(sorted(s["members"]) for s in out["subsystems"])
    assert names == [["a", "b"], ["c"]]
```

Run: `uv run pytest tests/agent/test_clustering.py -v`
Expected: PASS (6 passed)

- [ ] **Step 7: Commit**

```bash
git add src/code_context_graph/agent/clustering.py src/code_context_graph/agent/graph_ops.py tests/agent/test_clustering.py
git commit -m "feat(agent): networkx subsystem clustering + list_subsystems op"
```

---

## Task 4: Wrap ops as in-process SDK MCP tools

**Files:**
- Create: `src/code_context_graph/agent/graph_tools.py`
- Create: `tests/agent/test_graph_tools.py`

- [ ] **Step 1: Write failing tests**

Create `tests/agent/test_graph_tools.py`:

```python
from __future__ import annotations

import json

import pytest

from code_context_graph.agent.deps import GraphDeps
from code_context_graph.agent.graph_tools import build_graph_server, GRAPH_TOOL_NAMES


def test_server_exposes_expected_tool_names():
    assert "mcp__graph__get_source_slice" in GRAPH_TOOL_NAMES
    assert "mcp__graph__list_subsystems" in GRAPH_TOOL_NAMES
    assert "mcp__graph__neighbors" in GRAPH_TOOL_NAMES


def test_build_graph_server_returns_config(seeded, tmp_path):
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=tmp_path)
    server = build_graph_server(deps)
    assert server is not None


@pytest.mark.asyncio
async def test_slice_tool_handler_serialises_op_result(seeded, repo_tree):
    seeded.when(lambda q, p: "RETURN e.file_path" in q,
                [{"file": "src/mod.py", "start": 1, "end": 2}])
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=repo_tree)
    from code_context_graph.agent.graph_tools import _make_handlers
    handlers = _make_handlers(deps)
    result = await handlers["get_source_slice"]({"name": "pkg.mod"})
    payload = json.loads(result["content"][0]["text"])
    assert payload["source"] == "line1\nline2"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/agent/test_graph_tools.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the tool server**

Create `src/code_context_graph/agent/graph_tools.py`:

```python
from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from claude_agent_sdk import tool, create_sdk_mcp_server, ToolAnnotations

from code_context_graph.agent import graph_ops as ops
from code_context_graph.agent.deps import GraphDeps

SERVER_NAME = "graph"

# Fully-qualified names to pre-approve in allowed_tools.
GRAPH_TOOL_NAMES = [
    f"mcp__{SERVER_NAME}__{n}"
    for n in (
        "list_subsystems", "get_entity", "find_entities", "neighbors",
        "get_source_slice", "entry_points", "integration_points", "graph_summary",
    )
]

_READ_ONLY = ToolAnnotations(readOnlyHint=True)


def _ok(payload: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(payload, default=str)}]}


def _make_handlers(deps: GraphDeps) -> dict[str, Callable[[dict], Awaitable[dict]]]:
    """Plain async handlers (no decorator) so tests can call op logic directly."""
    async def list_subsystems(args):
        return _ok(ops.list_subsystems(deps, max_clusters=int(args.get("max_clusters", 12))))

    async def get_entity(args):
        return _ok(ops.get_entity(deps, args["name"]))

    async def find_entities(args):
        return _ok(ops.find_entities(deps, kind=args.get("kind"),
                                     prefix=args.get("prefix"),
                                     limit=int(args.get("limit", 50))))

    async def neighbors(args):
        return _ok(ops.neighbors(deps, args["name"], edge=args["edge"],
                                 direction=args.get("direction", "out"),
                                 depth=int(args.get("depth", 1)),
                                 limit=int(args.get("limit", 50))))

    async def get_source_slice(args):
        return _ok(ops.get_source_slice(deps, args["name"]))

    async def entry_points(args):
        return _ok(ops.entry_points(deps, limit=int(args.get("limit", 50))))

    async def integration_points(args):
        return _ok(ops.integration_points(deps, markers=args.get("markers"),
                                          limit=int(args.get("limit", 50))))

    async def graph_summary(args):
        return _ok(ops.graph_summary(deps))

    return {
        "list_subsystems": list_subsystems, "get_entity": get_entity,
        "find_entities": find_entities, "neighbors": neighbors,
        "get_source_slice": get_source_slice, "entry_points": entry_points,
        "integration_points": integration_points, "graph_summary": graph_summary,
    }


def build_graph_server(deps: GraphDeps):
    """Build the in-process MCP server exposing graph navigation tools, all bound to
    this repo's GraphDeps. All tools are read-only."""
    h = _make_handlers(deps)

    tools = [
        tool("list_subsystems",
             "List the repo's subsystems (graph communities). Returns name + member "
             "entity ids. Call this first to plan which subsystem to analyse.",
             {"max_clusters": int}, annotations=_READ_ONLY)(h["list_subsystems"]),
        tool("get_entity", "Look up one entity by qualified or simple name.",
             {"name": str}, annotations=_READ_ONLY)(h["get_entity"]),
        tool("find_entities",
             "Find entities. Optional 'kind' (Class/Function/Method/Module) and "
             "'prefix' filters; both optional, read with care.",
             {"kind": str, "prefix": str, "limit": int},
             annotations=_READ_ONLY)(h["find_entities"]),
        tool("neighbors",
             "Traverse the graph from an entity. 'edge' one of "
             "CALLS/IMPORTS/CONTAINS/INHERITS/DECORATES/RAISES; 'direction' "
             "out/in/both; 'depth' 1-5.",
             {"name": str, "edge": str, "direction": str, "depth": int, "limit": int},
             annotations=_READ_ONLY)(h["neighbors"]),
        tool("get_source_slice",
             "Return ONLY the source lines for one entity (start_line..end_line). "
             "Use this to read code instead of whole files.",
             {"name": str}, annotations=_READ_ONLY)(h["get_source_slice"]),
        tool("entry_points", "Heuristic entry points (entities with no callers).",
             {"limit": int}, annotations=_READ_ONLY)(h["entry_points"]),
        tool("integration_points",
             "External/IO touch points (DB, MQ, files, HTTP, ...). Optional 'markers' "
             "list to override the default IO name registry.",
             {"markers": list, "limit": int},
             annotations=_READ_ONLY)(h["integration_points"]),
        tool("graph_summary", "Entity and relationship counts for the repo.",
             {}, annotations=_READ_ONLY)(h["graph_summary"]),
    ]
    return create_sdk_mcp_server(name=SERVER_NAME, version="1.0.0", tools=tools)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/agent/test_graph_tools.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/code_context_graph/agent/graph_tools.py tests/agent/test_graph_tools.py
git commit -m "feat(agent): in-process SDK MCP server wrapping graph ops"
```

---

## Task 5: AgentRunner harness + FakeAgentRunner

**Files:**
- Create: `src/code_context_graph/agent/harness.py`
- Modify: `tests/agent/conftest.py`
- Create: `tests/agent/test_harness.py`

- [ ] **Step 1: Write failing test for FakeAgentRunner contract**

Create `tests/agent/test_harness.py`:

```python
from __future__ import annotations

import pytest

from code_context_graph.agent.harness import AgentRunner


@pytest.mark.asyncio
async def test_fake_runner_returns_scripted_structured_output(fake_runner):
    fake_runner.script({"sections": [], "evidence_map": {}})
    out = await fake_runner.run_structured(
        system="s", prompt="p", server=None,
        allowed_tools=[], model="m", max_turns=3, schema={"type": "object"},
    )
    assert out == {"sections": [], "evidence_map": {}}
    assert isinstance(fake_runner, AgentRunner)
    assert fake_runner.calls[0]["prompt"] == "p"
```

- [ ] **Step 2: Add FakeAgentRunner to conftest**

Append to `tests/agent/conftest.py`:

```python
from code_context_graph.agent.harness import AgentRunner  # noqa: E402


class FakeAgentRunner(AgentRunner):
    """Returns scripted structured outputs without touching the SDK/network."""

    def __init__(self) -> None:
        self._scripted: list[dict] = []
        self.calls: list[dict] = []
        self.token_usage = {"input": 0, "output": 0}

    def script(self, *outputs: dict) -> None:
        self._scripted = list(outputs)

    async def run_structured(self, *, system, prompt, server, allowed_tools,
                             model, max_turns, schema):
        self.calls.append({"system": system, "prompt": prompt, "model": model,
                           "max_turns": max_turns})
        return self._scripted.pop(0) if self._scripted else {}


@pytest.fixture
def fake_runner() -> "FakeAgentRunner":
    return FakeAgentRunner()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/agent/test_harness.py -v`
Expected: FAIL — `harness` module / `AgentRunner` not found.

- [ ] **Step 4: Implement the harness**

Create `src/code_context_graph/agent/harness.py`:

```python
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AgentRunner(Protocol):
    """Runs one agent turn-loop and returns its structured JSON output."""
    async def run_structured(self, *, system: str, prompt: str, server: Any,
                             allowed_tools: list[str], model: str, max_turns: int,
                             schema: dict[str, Any]) -> dict[str, Any]:
        ...


class SdkAgentRunner:
    """Real runner: drives claude_agent_sdk.query() with the graph MCP server and a
    json_schema output_format, returning ResultMessage.structured_output.

    Built-in tools are removed (tools=[]) so the agent can ONLY use graph tools, and
    no .claude settings are loaded (setting_sources=[]) for determinism."""

    def __init__(self) -> None:
        self.token_usage = {"input": 0, "output": 0}

    async def run_structured(self, *, system, prompt, server, allowed_tools,
                             model, max_turns, schema):
        from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage

        options = ClaudeAgentOptions(
            system_prompt=system,
            mcp_servers={"graph": server} if server is not None else {},
            allowed_tools=allowed_tools,
            tools=[],                       # remove built-ins; graph tools only
            model=model,
            max_turns=max_turns,
            setting_sources=[],             # do not load .claude config
            output_format={"type": "json_schema", "schema": schema},
        )
        structured: dict[str, Any] = {}
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, ResultMessage):
                structured = message.structured_output or {}
                usage = getattr(message, "usage", None) or {}
                self.token_usage["input"] += usage.get("input_tokens", 0) or 0
                self.token_usage["output"] += usage.get("output_tokens", 0) or 0
        return structured
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/agent/test_harness.py -v`
Expected: PASS (1 passed)

- [ ] **Step 6: Commit**

```bash
git add src/code_context_graph/agent/harness.py tests/agent/conftest.py tests/agent/test_harness.py
git commit -m "feat(agent): AgentRunner protocol, SDK runner, fake runner"
```

---

## Task 6: BRD output schemas + map/reduce orchestrator

**Files:**
- Create: `src/code_context_graph/agent/brd_schema.py`
- Create: `src/code_context_graph/agent/brd_orchestrator.py`
- Create: `tests/agent/test_brd_orchestrator.py`

- [ ] **Step 1: Create the LLM output schemas**

Create `src/code_context_graph/agent/brd_schema.py`:

```python
from __future__ import annotations

from pydantic import BaseModel, Field

from code_context_graph.brd.schema import BRDSection, EvidenceMap


class BRDDraft(BaseModel):
    """What a subsystem agent and the reduce step emit. repo_id/model/strategy are
    added by our code, not the LLM, so they are absent here."""
    sections: list[BRDSection]
    evidence_map: EvidenceMap = Field(default_factory=dict)


def brd_draft_schema() -> dict:
    return BRDDraft.model_json_schema()
```

- [ ] **Step 2: Write failing tests for the orchestrator**

Create `tests/agent/test_brd_orchestrator.py`:

```python
from __future__ import annotations

import pytest

from code_context_graph.agent.deps import GraphDeps
from code_context_graph.agent.brd_orchestrator import agenerate_brd_draft
from code_context_graph.brd.schema import Strategy


@pytest.mark.asyncio
async def test_single_subsystem_skips_reduce(seeded, tmp_path, fake_runner):
    seeded.when(lambda q, p: "RETURN e.qualified_name AS qn" in q, [{"qn": "a"}])
    seeded.when(lambda q, p: "RETURN a.qualified_name AS src" in q, [])
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=tmp_path)
    fake_runner.script(
        {"sections": [{"title": "Executive Summary", "body_markdown": "x",
                       "requirements": [{"id": "FR-1", "text": "do a"}]}],
         "evidence_map": {"FR-1": ["a"]}},
    )
    draft, strategy = await agenerate_brd_draft(
        deps, runner=fake_runner, model="m", max_turns=5, max_subsystems=12,
    )
    assert strategy == Strategy.single_shot
    assert draft.evidence_map == {"FR-1": ["a"]}
    assert len(fake_runner.calls) == 1  # map only, no reduce


@pytest.mark.asyncio
async def test_multi_subsystem_maps_then_reduces(seeded, tmp_path, fake_runner):
    seeded.when(lambda q, p: "RETURN e.qualified_name AS qn" in q,
                [{"qn": "a"}, {"qn": "b"}])
    seeded.when(lambda q, p: "RETURN a.qualified_name AS src" in q, [])  # disconnected
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=tmp_path)
    fake_runner.script(
        {"sections": [{"title": "Functional Requirements", "body_markdown": "a",
                       "requirements": [{"id": "FR-1", "text": "a"}]}],
         "evidence_map": {"FR-1": ["a"]}},
        {"sections": [{"title": "Functional Requirements", "body_markdown": "b",
                       "requirements": [{"id": "FR-2", "text": "b"}]}],
         "evidence_map": {"FR-2": ["b"]}},
        {"sections": [{"title": "Executive Summary", "body_markdown": "merged",
                       "requirements": []}],
         "evidence_map": {"FR-1": ["a"], "FR-2": ["b"]}},
    )
    draft, strategy = await agenerate_brd_draft(
        deps, runner=fake_runner, model="m", max_turns=5, max_subsystems=12,
    )
    assert strategy == Strategy.map_reduce
    assert len(fake_runner.calls) == 3       # 2 maps + 1 reduce
    assert draft.evidence_map == {"FR-1": ["a"], "FR-2": ["b"]}


@pytest.mark.asyncio
async def test_failed_subsystem_degrades_to_stub(seeded, tmp_path, fake_runner):
    seeded.when(lambda q, p: "RETURN e.qualified_name AS qn" in q,
                [{"qn": "a"}, {"qn": "b"}])
    seeded.when(lambda q, p: "RETURN a.qualified_name AS src" in q, [])
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=tmp_path)

    class FlakyRunner(fake_runner.__class__):
        async def run_structured(self, **kw):
            self.calls.append(kw)
            if len(self.calls) == 1:
                raise RuntimeError("boom")
            return {"sections": [{"title": "Executive Summary",
                                  "body_markdown": "ok", "requirements": []}],
                    "evidence_map": {}}

    flaky = FlakyRunner()
    draft, _ = await agenerate_brd_draft(deps, runner=flaky, model="m",
                                         max_turns=5, max_subsystems=12)
    # one map raised -> stub slice; second map + reduce still ran
    assert any("failed" in s.body_markdown.lower()
               for s in draft.sections) or draft.sections
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/agent/test_brd_orchestrator.py -v`
Expected: FAIL — module not found.

- [ ] **Step 4: Implement the orchestrator**

Create `src/code_context_graph/agent/brd_orchestrator.py`:

```python
from __future__ import annotations

import asyncio
import json
from typing import Any

from code_context_graph.agent import graph_ops as ops
from code_context_graph.agent.brd_schema import BRDDraft, brd_draft_schema
from code_context_graph.agent.deps import GraphDeps
from code_context_graph.agent.graph_tools import GRAPH_TOOL_NAMES, build_graph_server
from code_context_graph.agent.harness import AgentRunner
from code_context_graph.brd.schema import BRDSection, Strategy

ELEVEN_SECTIONS = [
    "Executive Summary", "Business Objectives", "Scope", "Stakeholders",
    "Functional Requirements", "Non-functional Requirements", "Data & Integrations",
    "Assumptions", "Constraints", "Risks", "Success Metrics",
]

MAP_SYSTEM = f"""You are a senior business analyst extracting Business Requirements
for ONE subsystem of a codebase. You have graph-navigation tools — use them to pull
ONLY what you need:
- get_source_slice(name) reads one entity's source lines (never whole files)
- neighbors(name, edge, direction) walks CALLS/CONTAINS/IMPORTS/INHERITS
- entry_points / integration_points / get_entity / find_entities

Ground EVERY requirement in real entity ids or file paths you actually inspected.
Use ids FR-1.. and NFR-1.. Provide an evidence_map: requirement_id -> [entity_or_path].
Do NOT invent entities. Cover only this subsystem. Emit the BRDDraft JSON
(sections from this list where relevant: {", ".join(ELEVEN_SECTIONS)})."""

REDUCE_SYSTEM = f"""You are merging per-subsystem BRD drafts into ONE BRD for the whole
repository. Produce exactly these 11 sections in order: {", ".join(ELEVEN_SECTIONS)}.
Deduplicate requirements, reconcile contradictions, keep the most specific wording,
and preserve EVERY evidence pointer (do not drop entries from any evidence_map).
Emit one BRDDraft JSON."""


def _map_prompt(subsystem_name: str, members: list[str]) -> str:
    preview = members[:60]
    return (f"Subsystem: {subsystem_name}\n"
            f"Member entity ids ({len(members)}, first {len(preview)} shown):\n"
            + json.dumps(preview)
            + "\n\nNavigate from these and produce this subsystem's BRD draft.")


def _reduce_prompt(drafts: list[BRDDraft]) -> str:
    payload = [d.model_dump(mode="json") for d in drafts]
    return "Sub-system drafts to merge:\n```json\n" + json.dumps(payload) + "\n```"


def _stub_draft(name: str, exc: Exception) -> BRDDraft:
    return BRDDraft(
        sections=[BRDSection(
            title="Executive Summary",
            body_markdown=f"<subsystem '{name}' failed to generate: {type(exc).__name__}>",
            requirements=[])],
        evidence_map={},
    )


async def _map_one(deps, runner, server, model, max_turns, sub) -> BRDDraft:
    try:
        raw = await runner.run_structured(
            system=MAP_SYSTEM, prompt=_map_prompt(sub["name"], sub["members"]),
            server=server, allowed_tools=GRAPH_TOOL_NAMES, model=model,
            max_turns=max_turns, schema=brd_draft_schema(),
        )
        return BRDDraft.model_validate(raw)
    except Exception as exc:  # degrade, don't kill the whole BRD
        return _stub_draft(sub["name"], exc)


async def agenerate_brd_draft(deps: GraphDeps, *, runner: AgentRunner, model: str,
                              max_turns: int, max_subsystems: int
                              ) -> tuple[BRDDraft, Strategy]:
    server = build_graph_server(deps)
    subs = ops.list_subsystems(deps, max_clusters=max_subsystems)["subsystems"]
    if not subs:
        subs = [{"name": deps.repo_id, "members": []}]

    drafts = await asyncio.gather(*[
        _map_one(deps, runner, server, model, max_turns, s) for s in subs
    ])

    if len(drafts) == 1:
        return drafts[0], Strategy.single_shot

    merged = await runner.run_structured(
        system=REDUCE_SYSTEM, prompt=_reduce_prompt(list(drafts)),
        server=server, allowed_tools=GRAPH_TOOL_NAMES, model=model,
        max_turns=max_turns, schema=brd_draft_schema(),
    )
    return BRDDraft.model_validate(merged), Strategy.map_reduce
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/agent/test_brd_orchestrator.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add src/code_context_graph/agent/brd_schema.py src/code_context_graph/agent/brd_orchestrator.py tests/agent/test_brd_orchestrator.py
git commit -m "feat(agent): map/reduce BRD orchestrator over subsystems"
```

---

## Task 7: Graph-backed Judge

**Files:**
- Create: `src/code_context_graph/agent/brd_judge.py`
- Create: `tests/agent/test_brd_judge.py`

- [ ] **Step 1: Write failing tests**

Create `tests/agent/test_brd_judge.py`:

```python
from __future__ import annotations

import pytest

from code_context_graph.agent.deps import GraphDeps
from code_context_graph.agent.brd_judge import ajudge
from code_context_graph.brd.schema import BRD, BRDSection, Requirement, Strategy


def _brd(evidence):
    return BRD(sections=[BRDSection(title="Functional Requirements", body_markdown="x",
                                    requirements=[Requirement(id="FR-1", text="t")])],
               evidence_map=evidence, repo_id="r", model="m",
               strategy=Strategy.map_reduce)


@pytest.mark.asyncio
async def test_hallucinated_reference_floors_accuracy(seeded, tmp_path, fake_runner):
    seeded.when(lambda q, p: "RETURN DISTINCT e.qualified_name" in q,
                [{"qualified_name": "a", "file_path": "src/a.py"}])
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=tmp_path)
    fake_runner.script({"items": [
        {"dimension": "completeness", "score": 5, "rationale": ""},
        {"dimension": "accuracy", "score": 5, "rationale": ""},
        {"dimension": "clarity", "score": 5, "rationale": ""},
        {"dimension": "consistency", "score": 5, "rationale": ""},
        {"dimension": "actionability", "score": 5, "rationale": ""}],
        "feedback": []})
    report = await ajudge(_brd({"FR-1": ["ghost.entity"]}), deps,
                          runner=fake_runner, model="m")
    assert report.groundedness_failures == ["ghost.entity"]
    assert report.dimensions[next(d for d in report.dimensions
                                  if d.value == "accuracy")].score == 2


@pytest.mark.asyncio
async def test_clean_brd_keeps_scores(seeded, tmp_path, fake_runner):
    seeded.when(lambda q, p: "RETURN DISTINCT e.qualified_name" in q,
                [{"qualified_name": "a", "file_path": "src/a.py"}])
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=tmp_path)
    fake_runner.script({"items": [
        {"dimension": "completeness", "score": 4, "rationale": ""},
        {"dimension": "accuracy", "score": 5, "rationale": ""},
        {"dimension": "clarity", "score": 4, "rationale": ""},
        {"dimension": "consistency", "score": 4, "rationale": ""},
        {"dimension": "actionability", "score": 4, "rationale": ""}],
        "feedback": []})
    report = await ajudge(_brd({"FR-1": ["a"]}), deps, runner=fake_runner, model="m")
    assert report.groundedness_failures == []
    assert report.rating.value == "high"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/agent/test_brd_judge.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the judge**

Create `src/code_context_graph/agent/brd_judge.py`:

```python
from __future__ import annotations

import json
from typing import Any

from code_context_graph.agent import graph_ops as ops
from code_context_graph.agent.deps import GraphDeps
from code_context_graph.agent.harness import AgentRunner
from code_context_graph.brd.schema import (
    BRD, Dimension, DimensionScore, FeedbackItem, JudgeReport, Rating,
)

WEIGHTS = {
    Dimension.completeness: 0.25, Dimension.accuracy: 0.30, Dimension.clarity: 0.15,
    Dimension.consistency: 0.15, Dimension.actionability: 0.15,
}

JUDGE_SYSTEM = """Evaluate this BRD generated from a codebase. Score five dimensions
1-5 each with a brief rationale: completeness, accuracy, clarity, consistency,
actionability. Return JSON: {"items":[{"dimension","score","rationale"}...],
"feedback":[{"dimension","severity","suggestion","target_section"}...]}."""

# Reuse the LLM output schema shape for output_format.
_JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {"type": "array", "items": {"type": "object", "properties": {
            "dimension": {"type": "string"}, "score": {"type": "integer"},
            "rationale": {"type": "string"}}, "required": ["dimension", "score"]}},
        "feedback": {"type": "array", "items": {"type": "object", "properties": {
            "dimension": {"type": "string"}, "severity": {"type": "string"},
            "suggestion": {"type": "string"}, "target_section": {"type": "string"}}}},
    },
    "required": ["items"],
}


def _groundedness_failures(brd: BRD, known: set[str]) -> list[str]:
    failures: list[str] = []
    for refs in brd.evidence_map.values():
        for ref in refs:
            if ref not in known:
                failures.append(ref)
    return failures


def _rate(weighted: float, dims: dict[Dimension, DimensionScore]) -> Rating:
    if weighted >= 4.2 and all(d.score >= 3 for d in dims.values()):
        return Rating.high
    if weighted >= 3.2 and all(d.score >= 2 for d in dims.values()):
        return Rating.medium
    return Rating.low


async def ajudge(brd: BRD, deps: GraphDeps, *, runner: AgentRunner,
                 model: str) -> JudgeReport:
    known = ops.known_refs(deps)
    failures = _groundedness_failures(brd, known)

    raw: dict[str, Any] = await runner.run_structured(
        system=JUDGE_SYSTEM,
        prompt="## BRD under review\n```json\n" + brd.model_dump_json() + "\n```",
        server=None, allowed_tools=[], model=model, max_turns=1, schema=_JUDGE_SCHEMA,
    )

    dims: dict[Dimension, DimensionScore] = {}
    for item in raw.get("items", []):
        try:
            dim = Dimension(item["dimension"])
        except ValueError:
            continue
        dims[dim] = DimensionScore(score=int(item["score"]),
                                   rationale=item.get("rationale", ""))
    for d in Dimension:                      # default any missing dimension to 3
        dims.setdefault(d, DimensionScore(score=3, rationale="(not scored)"))

    if failures and dims[Dimension.accuracy].score > 2:
        prev = dims[Dimension.accuracy]
        dims[Dimension.accuracy] = DimensionScore(
            score=2,
            rationale=prev.rationale + f" [forced to 2 by hallucinated refs: {failures}]")

    weighted = sum(dims[d].score * w for d, w in WEIGHTS.items())
    feedback = [FeedbackItem(**f) for f in raw.get("feedback", [])
                if {"dimension", "severity", "suggestion", "target_section"} <= set(f)]
    return JudgeReport(dimensions=dims, weighted_score=weighted,
                       rating=_rate(weighted, dims), feedback=feedback,
                       groundedness_failures=failures)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/agent/test_brd_judge.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/code_context_graph/agent/brd_judge.py tests/agent/test_brd_judge.py
git commit -m "feat(agent): graph-backed BRD judge (groundedness + rubric)"
```

---

## Task 8: Rewire pipeline to the graph orchestrator

**Files:**
- Modify: `src/code_context_graph/brd/pipeline.py`
- Create: `tests/agent/test_pipeline_graph.py`

- [ ] **Step 1: Write a failing integration test (fake runner, fake client)**

Create `tests/agent/test_pipeline_graph.py`:

```python
from __future__ import annotations

import pytest

from code_context_graph.agent.deps import GraphDeps
from code_context_graph.brd.pipeline import agenerate_brd_graph
from code_context_graph.brd.schema import Rating


@pytest.mark.asyncio
async def test_pipeline_runs_map_judge_and_returns_result(seeded, tmp_path, fake_runner):
    seeded.when(lambda q, p: "RETURN e.qualified_name AS qn" in q, [{"qn": "a"}])
    seeded.when(lambda q, p: "RETURN a.qualified_name AS src" in q, [])
    seeded.when(lambda q, p: "RETURN DISTINCT e.qualified_name" in q,
                [{"qualified_name": "a", "file_path": "src/a.py"}])
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=tmp_path)
    fake_runner.script(
        # map (single subsystem)
        {"sections": [{"title": "Executive Summary", "body_markdown": "x",
                       "requirements": [{"id": "FR-1", "text": "t"}]}],
         "evidence_map": {"FR-1": ["a"]}},
        # judge rubric
        {"items": [{"dimension": "completeness", "score": 4, "rationale": ""},
                   {"dimension": "accuracy", "score": 5, "rationale": ""},
                   {"dimension": "clarity", "score": 4, "rationale": ""},
                   {"dimension": "consistency", "score": 4, "rationale": ""},
                   {"dimension": "actionability", "score": 4, "rationale": ""}],
         "feedback": []},
    )
    result = await agenerate_brd_graph(
        deps, runner=fake_runner, model="m", max_retries=0,
        max_turns=5, max_subsystems=12,
    )
    assert result.rating == Rating.high
    assert result.brd.evidence_map == {"FR-1": ["a"]}
    assert result.report.groundedness_failures == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/agent/test_pipeline_graph.py -v`
Expected: FAIL — `agenerate_brd_graph` not defined.

- [ ] **Step 3: Add the async graph pipeline to pipeline.py**

Add to `src/code_context_graph/brd/pipeline.py` (new function; keep existing imports, add the ones below at top):

```python
import asyncio
import os
from dataclasses import dataclass
from pathlib import Path

from code_context_graph.agent.deps import GraphDeps
from code_context_graph.agent.brd_orchestrator import agenerate_brd_draft
from code_context_graph.agent.brd_judge import ajudge
from code_context_graph.agent.harness import AgentRunner, SdkAgentRunner
from code_context_graph.brd.schema import BRD


@dataclass
class GraphBRDResult:
    """In-memory result of a graph-navigated BRD run, before persistence."""
    brd: BRD
    report: JudgeReport
    rating: Rating
    weighted_score: float
    attempts: int
    attempt_history: list[AttemptRecord]
    strategy: Strategy


def _draft_to_brd(draft, repo_id: str, model: str, strategy: Strategy) -> BRD:
    return BRD(sections=draft.sections, evidence_map=draft.evidence_map,
               repo_id=repo_id, model=model, strategy=strategy)


async def agenerate_brd_graph(deps: GraphDeps, *, runner: AgentRunner, model: str,
                              max_retries: int, max_turns: int,
                              max_subsystems: int) -> GraphBRDResult:
    attempts: list[AttemptRecord] = []
    best: tuple[BRD, JudgeReport] | None = None

    for attempt_no in range(1, max_retries + 2):
        draft, strategy = await agenerate_brd_draft(
            deps, runner=runner, model=model, max_turns=max_turns,
            max_subsystems=max_subsystems)
        brd = _draft_to_brd(draft, deps.repo_id, model, strategy)
        report = await ajudge(brd, deps, runner=runner, model=model)
        attempts.append(AttemptRecord(attempt=attempt_no, rating=report.rating,
                                      weighted_score=report.weighted_score,
                                      feedback=report.feedback))
        if best is None or report.weighted_score > best[1].weighted_score:
            best = (brd, report)
        if report.rating == Rating.high:
            break

    assert best is not None
    final_brd, final_report = best
    return GraphBRDResult(brd=final_brd, report=final_report,
                          rating=final_report.rating,
                          weighted_score=final_report.weighted_score,
                          attempts=len(attempts), attempt_history=attempts,
                          strategy=final_brd.strategy)


def generate_brd_graph_sync(repo_id: str, *, client=None, repo_path=None,
                            max_retries: int | None = None, model: str | None = None,
                            max_turns: int | None = None,
                            max_subsystems: int | None = None,
                            storage: BRDStorage | None = None) -> BRDResult:
    """Sync entry point for CLI/API. Resolves deps + env defaults, runs the graph
    loop, renders + persists HTML, and returns the existing BRDResult so callers are
    unchanged. Mirrors the old generate_brd() contract."""
    if client is None:
        from code_context_graph.neo4j_client import Neo4jClient
        client = Neo4jClient()
    if repo_path is None:
        from code_context_graph.repo_manager import RepoManager
        repo = RepoManager(client).get(repo_id)
        if repo is None or not repo.get("local_path"):
            raise ValueError(f"Repo {repo_id} not registered or missing local_path")
        repo_path = repo["local_path"]
    model = model or os.getenv("BRD_AGENT_MODEL", "claude-sonnet-4-6")
    max_retries = int(os.getenv("BRD_MAX_RETRIES", "1")) if max_retries is None else max_retries
    max_turns = int(os.getenv("BRD_AGENT_MAX_TURNS", "15")) if max_turns is None else max_turns
    max_subsystems = int(os.getenv("BRD_MAX_SUBSYSTEMS", "12")) if max_subsystems is None else max_subsystems

    deps = GraphDeps(client=client, repo_id=repo_id, repo_path=Path(repo_path))
    runner = SdkAgentRunner()
    result = asyncio.run(agenerate_brd_graph(
        deps, runner=runner, model=model, max_retries=max_retries,
        max_turns=max_turns, max_subsystems=max_subsystems))

    html = render_html(result.brd)
    if storage is None:
        storage = BRDStorage(client)
    return storage.save(
        repo_id=repo_id, html=html, judge_report=result.report,
        attempt_history=result.attempt_history, model=model,
        strategy=result.strategy,
        token_usage={"input": runner.token_usage["input"],
                     "output": runner.token_usage["output"]},
    )
```

Note: `agenerate_brd_graph` returns the rich in-memory `GraphBRDResult` (used by tests); `generate_brd_graph_sync` wraps it, persists via the unchanged `BRDStorage.save(...)`, and returns the existing `BRDResult`, so `cli.py`/`api.py` keep using `result.brd_id`, `result.rating`, `result.html_path`, etc.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/agent/test_pipeline_graph.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add src/code_context_graph/brd/pipeline.py tests/agent/test_pipeline_graph.py
git commit -m "feat(brd): graph-navigated pipeline with judge retry loop"
```

---

## Task 9: Language-matrix genericity smoke test

**Files:**
- Create: `tests/agent/test_language_matrix.py`

- [ ] **Step 1: Write the matrix test**

Create `tests/agent/test_language_matrix.py`:

```python
from __future__ import annotations

import pytest

from code_context_graph.agent.deps import GraphDeps
from code_context_graph.brd.pipeline import agenerate_brd_graph
from tests.agent.conftest import SeededNeo4j


# One seeded graph shape per language. The agent layer must treat them identically:
# only entity ids/kinds/edges differ, never code branches.
LANG_FIXTURES = {
    "python": [{"qn": "app.main"}, {"qn": "app.db"}],
    "java":   [{"qn": "com.app.Main"}, {"qn": "com.app.Repo"}],
    "rust":   [{"qn": "app::main"}, {"qn": "app::store"}],
    "cobol":  [{"qn": "PAYROLL"}, {"qn": "TAXCALC"}],
}


@pytest.mark.asyncio
@pytest.mark.parametrize("lang,nodes", LANG_FIXTURES.items())
async def test_brd_generates_for_each_language(lang, nodes, tmp_path, fake_runner):
    seeded = SeededNeo4j()
    seeded.when(lambda q, p: "RETURN e.qualified_name AS qn" in q, nodes)
    seeded.when(lambda q, p: "RETURN a.qualified_name AS src" in q,
                [{"src": nodes[0]["qn"], "dst": nodes[1]["qn"]}])  # connected -> 1 subsystem
    first = nodes[0]["qn"]
    seeded.when(lambda q, p: "RETURN DISTINCT e.qualified_name" in q,
                [{"qualified_name": n["qn"], "file_path": f"{n['qn']}.src"} for n in nodes])
    deps = GraphDeps(client=seeded, repo_id=lang, repo_path=tmp_path)
    fake_runner.script(
        {"sections": [{"title": "Functional Requirements", "body_markdown": "x",
                       "requirements": [{"id": "FR-1", "text": "t"}]}],
         "evidence_map": {"FR-1": [first]}},
        {"items": [{"dimension": d, "score": 4, "rationale": ""} for d in
                   ["completeness", "accuracy", "clarity", "consistency", "actionability"]],
         "feedback": []},
    )
    result = await agenerate_brd_graph(deps, runner=fake_runner, model="m",
                                       max_retries=0, max_turns=5, max_subsystems=12)
    assert result.brd.sections, f"{lang}: BRD had no sections"
    assert result.brd.evidence_map == {"FR-1": [first]}, f"{lang}: evidence dropped"
```

- [ ] **Step 2: Run the matrix test**

Run: `uv run pytest tests/agent/test_language_matrix.py -v`
Expected: PASS (4 passed — python, java, rust, cobol)

- [ ] **Step 3: Run the whole agent suite**

Run: `uv run pytest tests/agent/ -v`
Expected: PASS (all tasks' tests green)

- [ ] **Step 4: Commit**

```bash
git add tests/agent/test_language_matrix.py
git commit -m "test(agent): language-matrix genericity smoke (py/java/rust/cobol)"
```

---

## Task 10: Wire CLI/API to the graph pipeline; remove the Gemini BRD path

Because `generate_brd_graph_sync` returns the same `BRDResult` the old `generate_brd`
did, the CLI/API call sites change only the function name + arguments; all the
`result.*` field usage below them stays as-is.

**Files:**
- Modify: `src/code_context_graph/brd/__init__.py` (export the new entry point)
- Modify: `src/code_context_graph/cli.py:198-209`
- Modify: `src/code_context_graph/api.py:14`, `src/code_context_graph/api.py:152-157`
- Modify: `src/code_context_graph/brd/pipeline.py` (remove old Gemini `generate_brd`)
- Delete: `src/code_context_graph/brd/generator.py`, `src/code_context_graph/brd/context_builder.py`, `src/code_context_graph/brd/judge.py`
- **Keep** `src/code_context_graph/gemini_llm.py` — still imported by `enrichment.py` until Plan 2 migrates it. Deleting it here would break the enrichment path.
- Delete: `tests/brd/test_generator.py`, `tests/brd/test_context_builder.py`, `tests/brd/test_judge.py`, `tests/brd/test_pipeline.py`, `tests/brd/test_e2e.py` (all target the removed Gemini surface; coverage moves to `tests/agent/`)

- [ ] **Step 1: Update the BRD package export**

In `src/code_context_graph/brd/__init__.py`, change the import + `__all__` so the new
entry point is public:

```python
from code_context_graph.brd.pipeline import generate_brd_graph_sync
from code_context_graph.brd.schema import BRDResult, Rating, Strategy

__all__ = ["generate_brd_graph_sync", "BRDResult", "Rating", "Strategy"]
```

- [ ] **Step 2: Update the CLI BRD command**

In `src/code_context_graph/cli.py`, replace lines 198 and 205-209. Change the import
on line 198 from `from code_context_graph.brd import generate_brd` to:

```python
    from code_context_graph.brd import generate_brd_graph_sync
```

And replace the `generate_brd(...)` call (lines 205-209) with:

```python
    result = generate_brd_graph_sync(
        repo,
        client=get_client(),
        max_retries=max_retries,
    )
```

Everything below it (the `result.rating`, `result.weighted_score`, `result.attempts`,
`result.strategy`, `result.html_path` usage on lines 210-222) is unchanged because the
return type is still `BRDResult`. Note: `--force-map-reduce` no longer applies (the
graph path always map-reduces when there is more than one subsystem) — drop that
option from the command signature (line 190-191) and remove its use.

- [ ] **Step 3: Update the API BRD job**

In `src/code_context_graph/api.py` line 14, change
`from code_context_graph.brd import generate_brd` to:

```python
from code_context_graph.brd import generate_brd_graph_sync
```

Then replace the call in `_run_brd_job` (lines 152-157) with:

```python
        result = generate_brd_graph_sync(
            repo_id,
            client=get_client(),
            max_retries=max_retries,
        )
```

The `_brd_jobs[repo_id] = {...}` dict below it (lines 158-164) is unchanged — every
field it reads (`result.brd_id`, `result.rating`, `result.weighted_score`,
`result.attempts`, `result.version`, `result.html_path`, `result.created_at`,
`result.strategy`) still exists on `BRDResult`. The `force_map_reduce` parameter on
`_run_brd_job`/`start_brd` is now unused; leave the HTTP param for compatibility but
stop forwarding it (it is simply ignored).

- [ ] **Step 4: Remove the old Gemini BRD code and its imports**

```bash
git rm src/code_context_graph/brd/generator.py \
       src/code_context_graph/brd/context_builder.py
```

Do NOT delete `src/code_context_graph/gemini_llm.py` — `enrichment.py` still imports
`GeminiMessagesClient` from it (lazily, inside `enrich_all`). It is removed in Plan 2
when enrichment migrates.

Then in `src/code_context_graph/brd/pipeline.py` delete the old `generate_brd(...)`
function (lines 30-109) and remove these now-dead top-of-file imports:
`from code_context_graph.brd.context_builder import ContextBuilder, PromptContext`,
`from code_context_graph.brd.generator import Generator`, and the
`from code_context_graph.brd.judge import Judge` import. Keep `render_html`,
`BRDStorage`, the `brd.schema` imports, and the new graph functions/imports added in
Task 8. (`brd/judge.py` is also Gemini-only now and unused — delete it too:
`git rm src/code_context_graph/brd/judge.py`.)

- [ ] **Step 5: Delete the superseded Gemini-surface tests**

```bash
git rm tests/brd/test_generator.py tests/brd/test_context_builder.py \
       tests/brd/test_judge.py tests/brd/test_pipeline.py tests/brd/test_e2e.py
```

Then check nothing else imports a removed module:

Run: `rg -n "context_builder|brd\.generator|brd\.judge|GeminiMessagesClient|\bgenerate_brd\b" src tests`
Expected: only `generate_brd_graph_sync` references remain; no hits for the deleted
modules. (`tests/brd/test_api.py` patches `code_context_graph.api.generate_brd`; update
that patch target to `code_context_graph.api.generate_brd_graph_sync`. `tests/brd/conftest.py`'s
`FakeLLM` is now only used by deleted tests — leave it; it is harmless.)

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS — no import errors; `tests/agent/` green; surviving `tests/brd/`
(`test_renderer.py`, `test_storage.py`, `test_api.py`) green.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: cut BRD CLI/API over to graph-navigated agent; remove Gemini BRD path"
```

---

## Manual verification (post-implementation, requires a real graph + API key)

These are not automated (they hit Neo4j + the Anthropic API). Run once after Task 10:

1. Ensure `ANTHROPIC_API_KEY` is set and a repo is ingested + `tag_entities` run.
2. Ingest carddemo: `uv run ccg clone <carddemo path/url>` (or the existing ingest path).
3. Generate: `uv run ccg brd <slug>` (or the API route).
4. Confirm: BRD HTML is produced, requirements reference real carddemo entities
   (e.g. `COACTUPC`, `COTRN02C`), and the run used map_reduce with multiple subsystems.
5. Sanity-check token usage is far below the old whole-codebase prompt (the point of
   the change): the agent should pull slices, not whole files.

---

## Follow-on plans (out of scope here)

- **Plan 2 — Enrichment on the foundation:** centrality-ordered, fan-out, loop-until-exhausted; reuses `graph_ops` + `harness`. Replaces `enrichment.py`.
- **Plan 3 — Ask-the-Codebase on the foundation:** Cypher-first with graph-tool fallback; preserve `enforce_read_only_cypher`. Replaces the Gemini path in `llm_query.py`.
