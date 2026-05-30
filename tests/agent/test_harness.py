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
