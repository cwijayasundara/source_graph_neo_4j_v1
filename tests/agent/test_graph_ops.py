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
