from __future__ import annotations

from code_context_graph.agent.harness import _accumulate_usage, _caching_env


def test_accumulate_sums_all_four_token_buckets():
    tu = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}
    _accumulate_usage(tu, {"input_tokens": 10, "output_tokens": 5,
                           "cache_read_input_tokens": 3,
                           "cache_creation_input_tokens": 7})
    _accumulate_usage(tu, {"input_tokens": 1, "output_tokens": 1})  # missing cache keys
    assert tu == {"input": 11, "output": 6, "cache_read": 3, "cache_creation": 7}


def test_accumulate_tolerates_none_and_empty():
    tu = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}
    _accumulate_usage(tu, None)
    _accumulate_usage(tu, {})
    assert tu == {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}


def test_caching_env_off_by_default(monkeypatch):
    monkeypatch.delenv("CCG_PROMPT_CACHING_1H", raising=False)
    assert _caching_env() == {}


def test_caching_env_on_when_flag_set(monkeypatch):
    monkeypatch.setenv("CCG_PROMPT_CACHING_1H", "1")
    assert _caching_env() == {"ENABLE_PROMPT_CACHING_1H": "1"}
