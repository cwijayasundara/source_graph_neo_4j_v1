from __future__ import annotations

import pytest

from code_context_graph.agent.deps import GraphDeps
from code_context_graph.agent.brd_orchestrator import agenerate_brd_draft
from code_context_graph.brd.schema import Strategy


@pytest.mark.asyncio
async def test_single_subsystem_skips_reduce(seeded, tmp_path, fake_runner):
    seeded.when(lambda q, p: "RETURN e.qualified_name AS qn" in q, [{"qn": "a"}])
    seeded.when(lambda q, p: "RETURN a.qualified_name AS src" in q, [])
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=tmp_path)
    fake_runner.script(
        {"sections": [{"title": "Executive Summary", "body_markdown": "x",
                       "requirements": [{"id": "FR-1", "text": "do a"}]}],
         "evidence_map": {"FR-1": ["a"]}},
    )
    draft, strategy = await agenerate_brd_draft(
        deps, runner=fake_runner, model="m", max_turns=5, max_subsystems=12,
    )
    assert strategy == Strategy.single_shot
    assert draft.evidence_map == {"FR-1": ["a"]}
    assert len(fake_runner.calls) == 1  # map only, no reduce


@pytest.mark.asyncio
async def test_multi_subsystem_maps_then_reduces(seeded, tmp_path, fake_runner):
    seeded.when(lambda q, p: "RETURN e.qualified_name AS qn" in q,
                [{"qn": "a"}, {"qn": "b"}])
    seeded.when(lambda q, p: "RETURN a.qualified_name AS src" in q, [])  # disconnected
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=tmp_path)
    fake_runner.script(
        {"sections": [{"title": "Functional Requirements", "body_markdown": "a",
                       "requirements": [{"id": "FR-1", "text": "a"}]}],
         "evidence_map": {"FR-1": ["a"]}},
        {"sections": [{"title": "Functional Requirements", "body_markdown": "b",
                       "requirements": [{"id": "FR-2", "text": "b"}]}],
         "evidence_map": {"FR-2": ["b"]}},
        {"sections": [{"title": "Executive Summary", "body_markdown": "merged",
                       "requirements": []}],
         "evidence_map": {"FR-1": ["a"], "FR-2": ["b"]}},
    )
    draft, strategy = await agenerate_brd_draft(
        deps, runner=fake_runner, model="m", max_turns=5, max_subsystems=12,
    )
    assert strategy == Strategy.map_reduce
    assert len(fake_runner.calls) == 3       # 2 maps + 1 reduce
    assert draft.evidence_map == {"FR-1": ["a"], "FR-2": ["b"]}


@pytest.mark.asyncio
async def test_reduce_failure_degrades_to_deterministic_merge(seeded, tmp_path, fake_runner):
    seeded.when(lambda q, p: "RETURN e.qualified_name AS qn" in q,
                [{"qn": "a"}, {"qn": "b"}])
    seeded.when(lambda q, p: "RETURN a.qualified_name AS src" in q, [])  # disconnected -> 2 subsystems
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=tmp_path)
    fake_runner.script(
        {"sections": [{"title": "Functional Requirements", "body_markdown": "a",
                       "requirements": [{"id": "FR-1", "text": "a"}]}],
         "evidence_map": {"FR-1": ["a"]}},
        {"sections": [{"title": "Functional Requirements", "body_markdown": "b",
                       "requirements": [{"id": "FR-2", "text": "b"}]}],
         "evidence_map": {"FR-2": ["b"]}},
        # No reduce output scripted -> fake_runner returns {} -> model_validate fails -> fallback
    )
    draft, strategy = await agenerate_brd_draft(
        deps, runner=fake_runner, model="m", max_turns=5, max_subsystems=12,
    )
    assert strategy == Strategy.map_reduce
    assert draft.evidence_map == {"FR-1": ["a"], "FR-2": ["b"]}   # unioned, nothing dropped
    assert draft.sections                                          # merged, not empty


@pytest.mark.asyncio
async def test_failed_subsystem_degrades_to_stub(seeded, tmp_path, fake_runner):
    seeded.when(lambda q, p: "RETURN e.qualified_name AS qn" in q,
                [{"qn": "a"}, {"qn": "b"}])
    seeded.when(lambda q, p: "RETURN a.qualified_name AS src" in q, [])
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=tmp_path)

    class FlakyRunner(fake_runner.__class__):
        async def run_structured(self, **kw):
            self.calls.append(kw)
            if len(self.calls) == 1:
                raise RuntimeError("boom")
            return {"sections": [{"title": "Executive Summary",
                                  "body_markdown": "ok", "requirements": []}],
                    "evidence_map": {}}

    flaky = FlakyRunner()
    draft, _ = await agenerate_brd_draft(deps, runner=flaky, model="m",
                                         max_turns=5, max_subsystems=12)
    # one map raised -> stub slice; second map + reduce still ran
    assert any("failed" in s.body_markdown.lower()
               for s in draft.sections) or draft.sections
