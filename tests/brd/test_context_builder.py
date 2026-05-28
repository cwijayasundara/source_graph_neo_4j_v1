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
