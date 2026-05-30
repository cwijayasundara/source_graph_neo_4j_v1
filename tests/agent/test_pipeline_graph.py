from __future__ import annotations

import pytest

from code_context_graph.agent.deps import GraphDeps
from code_context_graph.brd.pipeline import agenerate_brd_graph
from code_context_graph.brd.schema import Rating


@pytest.mark.asyncio
async def test_pipeline_runs_map_judge_and_returns_result(seeded, tmp_path, fake_runner):
    seeded.when(lambda q, p: "RETURN e.qualified_name AS qn" in q, [{"qn": "a"}])
    seeded.when(lambda q, p: "RETURN a.qualified_name AS src" in q, [])
    seeded.when(lambda q, p: "RETURN DISTINCT e.qualified_name" in q,
                [{"qualified_name": "a", "file_path": "src/a.py"}])
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=tmp_path)
    fake_runner.script(
        # map (single subsystem)
        {"sections": [{"title": "Executive Summary", "body_markdown": "x",
                       "requirements": [{"id": "FR-1", "text": "t"}]}],
         "evidence_map": {"FR-1": ["a"]}},
        # judge rubric
        {"items": [{"dimension": "completeness", "score": 4, "rationale": ""},
                   {"dimension": "accuracy", "score": 5, "rationale": ""},
                   {"dimension": "clarity", "score": 4, "rationale": ""},
                   {"dimension": "consistency", "score": 4, "rationale": ""},
                   {"dimension": "actionability", "score": 4, "rationale": ""}],
         "feedback": []},
    )
    result = await agenerate_brd_graph(
        deps, runner=fake_runner, model="m", max_retries=0,
        max_turns=5, max_subsystems=12,
    )
    assert result.rating == Rating.high
    assert result.brd.evidence_map == {"FR-1": ["a"]}
    assert result.report.groundedness_failures == []
