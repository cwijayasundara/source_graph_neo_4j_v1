from __future__ import annotations

import json

import pytest

from code_context_graph.agent.advisor import (
    ADVISOR_TOOL_NAME, AdvisorBackend, make_advisor_handler,
)


class FakeAdvisor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def advise(self, question: str, context: str) -> str:
        self.calls.append((question, context))
        return "Prefer the State Machine reading."


def test_tool_name_is_namespaced():
    assert ADVISOR_TOOL_NAME == "mcp__graph__consult_advisor"


def test_fakeadvisor_satisfies_protocol():
    assert isinstance(FakeAdvisor(), AdvisorBackend)


@pytest.mark.asyncio
async def test_advisor_handler_returns_guidance():
    backend = FakeAdvisor()
    handler = make_advisor_handler(backend, max_uses=2)
    out = await handler({"question": "rule or plumbing?", "context": "para 1000"})
    payload = json.loads(out["content"][0]["text"])
    assert payload["advice"] == "Prefer the State Machine reading."
    assert backend.calls == [("rule or plumbing?", "para 1000")]


@pytest.mark.asyncio
async def test_advisor_handler_enforces_budget():
    backend = FakeAdvisor()
    handler = make_advisor_handler(backend, max_uses=1)
    await handler({"question": "q1", "context": ""})            # uses the 1 allowed call
    out = await handler({"question": "q2", "context": ""})       # over budget
    payload = json.loads(out["content"][0]["text"])
    assert payload["advice"] is None and "budget" in payload["note"].lower()
    assert len(backend.calls) == 1                                # backend not called again
