from __future__ import annotations

from code_context_graph.agent.models import resolve_model

_ALL = ["BRD_AGENT_MODEL", "ENRICHMENT_MODEL", "ASK_MODEL", "ADVISOR_MODEL",
        "CODE_GRAPH_LLM_MODEL"]


def _clear(monkeypatch):
    for v in _ALL:
        monkeypatch.delenv(v, raising=False)


def test_role_override_wins(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("BRD_AGENT_MODEL", "claude-opus-4-8")
    monkeypatch.setenv("CODE_GRAPH_LLM_MODEL", "claude-sonnet-4-6")
    assert resolve_model("brd") == "claude-opus-4-8"


def test_global_default_used_when_no_role_override(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("CODE_GRAPH_LLM_MODEL", "claude-sonnet-4-6")
    assert resolve_model("enrichment") == "claude-sonnet-4-6"


def test_hardcoded_fallback_per_role(monkeypatch):
    _clear(monkeypatch)
    assert resolve_model("brd") == "claude-sonnet-4-6"
    assert resolve_model("enrichment") == "claude-haiku-4-5-20251001"
    assert resolve_model("ask") == "claude-haiku-4-5-20251001"
    assert resolve_model("advisor") == "claude-opus-4-8"


def test_unknown_role_falls_back_to_sonnet(monkeypatch):
    _clear(monkeypatch)
    assert resolve_model("something_else") == "claude-sonnet-4-6"
