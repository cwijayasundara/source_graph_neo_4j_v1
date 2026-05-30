from __future__ import annotations

import pytest

from code_context_graph.agent.deps import GraphDeps
from code_context_graph.agent.enricher import aenrich


@pytest.mark.asyncio
async def test_enriches_one_entity_and_writes_back_then_terminates(seeded, tmp_path, fake_runner):
    seeded.when(lambda q, p: "semantic_layer IS NULL" in q,
                [{"qualified_name": "pkg.a", "kind": "Function",
                  "signature": "def a()", "file_path": "src/a.py"}])
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=tmp_path)
    fake_runner.script(
        {"patterns": ["Repository"], "layer": "data_access",
         "concepts": ["persistence"], "summary": "Reads records."},
    )
    n = await aenrich(deps, runner=fake_runner, model="m",
                      batch_size=10, max_concurrency=4, max_turns=4)
    assert n == 1
    assert len(fake_runner.calls) == 1
    writes = [(q, p) for q, p in seeded.calls if "SET e.semantic_layer" in q]
    assert writes and writes[0][1]["layer"] == "data_access"
    assert writes[0][1]["qname"] == "pkg.a"


@pytest.mark.asyncio
async def test_no_untagged_entities_is_zero(seeded, tmp_path, fake_runner):
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=tmp_path)  # no rules -> []
    n = await aenrich(deps, runner=fake_runner, model="m",
                      batch_size=10, max_concurrency=4, max_turns=4)
    assert n == 0
    assert len(fake_runner.calls) == 0


@pytest.mark.asyncio
async def test_empty_model_result_is_a_failure_not_a_write(seeded, tmp_path, fake_runner):
    seeded.when(lambda q, p: "semantic_layer IS NULL" in q,
                [{"qualified_name": "pkg.b", "kind": "Method",
                  "signature": "", "file_path": "src/b.py"}])
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=tmp_path)
    fake_runner.script({})  # empty result
    n = await aenrich(deps, runner=fake_runner, model="m",
                      batch_size=10, max_concurrency=4, max_turns=4)
    assert n == 0
    assert not any("SET e.semantic_layer" in q for q, _ in seeded.calls)
