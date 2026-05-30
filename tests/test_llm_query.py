from __future__ import annotations

import pytest

from code_context_graph.llm_query import (
    AskCodebaseResult,
    CypherValidationError,
    ask_codebase,
    enforce_read_only_cypher,
)


class FakeGraphClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def run(self, query: str, **params):
        self.calls.append((query, params))
        return [{"function": "backend.app.agent.handle_message", "complexity": 8}]


class FakeLLM:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate_text(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if len(self.prompts) == 1:
            return (
                '{"cypher":"MATCH (e:CodeEntity) WHERE e.repo = $repo '
                'RETURN e.qualified_name AS function, e.complexity AS complexity",'
                '"explanation":"Find functions for the selected repo."}'
            )
        return "The selected repo contains backend.app.agent.handle_message."


def test_enforce_read_only_cypher_blocks_writes() -> None:
    with pytest.raises(CypherValidationError):
        enforce_read_only_cypher("MATCH (n) DETACH DELETE n")


def test_enforce_read_only_cypher_adds_limit() -> None:
    cypher = enforce_read_only_cypher("MATCH (e:CodeEntity) WHERE e.repo = $repo RETURN e")

    assert cypher == "MATCH (e:CodeEntity) WHERE e.repo = $repo RETURN e\nLIMIT 50"


def test_ask_codebase_generates_executes_and_summarizes() -> None:
    graph = FakeGraphClient()
    llm = FakeLLM()

    result = ask_codebase(
        client=graph,
        repo="owner/repo",
        question="Which functions are complex?",
        llm=llm,
    )

    assert isinstance(result, AskCodebaseResult)
    assert result.cypher.endswith("LIMIT 50")
    assert result.rows == [{"function": "backend.app.agent.handle_message", "complexity": 8}]
    assert "handle_message" in result.answer
    assert graph.calls == [(result.cypher, {"repo": "owner/repo"})]
    assert "owner/repo" in llm.prompts[0]
    assert "backend.app.agent.handle_message" in llm.prompts[1]


def test_anthropic_text_client_satisfies_protocol_and_resolves_model(monkeypatch):
    from code_context_graph.llm_query import AnthropicTextClient

    for v in ["ASK_MODEL", "CODE_GRAPH_LLM_MODEL"]:
        monkeypatch.delenv(v, raising=False)
    c = AnthropicTextClient()
    # duck-typed LLMClient conformance (LLMClient is a plain Protocol, not
    # runtime_checkable, so isinstance() can't be used here)
    assert callable(getattr(c, "generate_text", None))
    assert c.model == "claude-haiku-4-5-20251001"   # resolve_model("ask") default
    monkeypatch.setenv("ASK_MODEL", "claude-sonnet-4-6")
    assert AnthropicTextClient().model == "claude-sonnet-4-6"
