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
