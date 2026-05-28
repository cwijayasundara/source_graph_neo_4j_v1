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
    from code_context_graph.brd.context_builder import estimate_tokens
    assert estimate_tokens("a" * 400) == 100
    assert estimate_tokens("") == 0
