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
