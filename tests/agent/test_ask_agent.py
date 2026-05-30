from __future__ import annotations

import pytest

from code_context_graph.agent.deps import GraphDeps
from code_context_graph.agent.ask_agent import agentic_answer


@pytest.mark.asyncio
async def test_agentic_answer_returns_model_answer(seeded, tmp_path, fake_runner):
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=tmp_path)
    fake_runner.script({"answer": "It validates the account then posts the transaction."})
    out = await agentic_answer(deps, runner=fake_runner, question="what does X do?",
                               model="m", max_turns=4)
    assert out == "It validates the account then posts the transaction."
    from code_context_graph.agent.graph_tools import GRAPH_TOOL_NAMES
    assert fake_runner.calls[0]["allowed_tools"] == GRAPH_TOOL_NAMES


@pytest.mark.asyncio
async def test_agentic_answer_empty_returns_none(seeded, tmp_path, fake_runner):
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=tmp_path)
    fake_runner.script({})  # SDK error / empty
    out = await agentic_answer(deps, runner=fake_runner, question="q", model="m", max_turns=4)
    assert out is None
