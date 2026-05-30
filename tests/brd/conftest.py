from __future__ import annotations

from typing import Any

import pytest


class FakeNeo4jClient:
    """Records run() calls and returns scripted results."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._scripted: list[list[dict]] = []

    def script(self, *results: list[dict]) -> None:
        self._scripted = list(results)

    def run(self, query: str, **params: Any) -> list[dict]:
        self.calls.append((query, params))
        if self._scripted:
            return self._scripted.pop(0)
        return []


@pytest.fixture
def fake_client() -> FakeNeo4jClient:
    return FakeNeo4jClient()


class FakeLLM:
    """Records messages.create() calls and returns scripted text responses.

    Matches the GeminiMessagesClient surface (and the Anthropic SDK surface it
    was modelled on): ``.messages.create(...)`` returning an object with
    ``content[0].text`` and a ``usage`` namespace.
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._responses: list[str] = []
        self.messages = self

    def script(self, *texts: str) -> None:
        self._responses = list(texts)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        text = self._responses.pop(0) if self._responses else "{}"

        class _Block:
            def __init__(self, t: str) -> None:
                self.text = t

        class _Response:
            def __init__(self, t: str) -> None:
                self.content = [_Block(t)]
                self.usage = type("U", (), {"input_tokens": 10, "output_tokens": 5,
                                            "cache_read_input_tokens": 0,
                                            "cache_creation_input_tokens": 0})()

        return _Response(text)


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()
