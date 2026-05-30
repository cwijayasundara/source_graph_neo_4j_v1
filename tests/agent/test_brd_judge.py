from __future__ import annotations

import pytest

from code_context_graph.agent.deps import GraphDeps
from code_context_graph.agent.brd_judge import ajudge
from code_context_graph.brd.schema import BRD, BRDSection, Requirement, Strategy


def _brd(evidence):
    return BRD(sections=[BRDSection(title="Functional Requirements", body_markdown="x",
                                    requirements=[Requirement(id="FR-1", text="t")])],
               evidence_map=evidence, repo_id="r", model="m",
               strategy=Strategy.map_reduce)


@pytest.mark.asyncio
async def test_hallucinated_reference_floors_accuracy(seeded, tmp_path, fake_runner):
    seeded.when(lambda q, p: "RETURN DISTINCT e.qualified_name" in q,
                [{"qualified_name": "a", "file_path": "src/a.py"}])
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=tmp_path)
    fake_runner.script({"items": [
        {"dimension": "completeness", "score": 5, "rationale": ""},
        {"dimension": "accuracy", "score": 5, "rationale": ""},
        {"dimension": "clarity", "score": 5, "rationale": ""},
        {"dimension": "consistency", "score": 5, "rationale": ""},
        {"dimension": "actionability", "score": 5, "rationale": ""}],
        "feedback": []})
    report = await ajudge(_brd({"FR-1": ["ghost.entity"]}), deps,
                          runner=fake_runner, model="m")
    assert report.groundedness_failures == ["ghost.entity"]
    assert report.dimensions[next(d for d in report.dimensions
                                  if d.value == "accuracy")].score == 2


@pytest.mark.asyncio
async def test_clean_brd_keeps_scores(seeded, tmp_path, fake_runner):
    seeded.when(lambda q, p: "RETURN DISTINCT e.qualified_name" in q,
                [{"qualified_name": "a", "file_path": "src/a.py"}])
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=tmp_path)
    fake_runner.script({"items": [
        {"dimension": "completeness", "score": 4, "rationale": ""},
        {"dimension": "accuracy", "score": 5, "rationale": ""},
        {"dimension": "clarity", "score": 4, "rationale": ""},
        {"dimension": "consistency", "score": 4, "rationale": ""},
        {"dimension": "actionability", "score": 4, "rationale": ""}],
        "feedback": []})
    report = await ajudge(_brd({"FR-1": ["a"]}), deps, runner=fake_runner, model="m")
    assert report.groundedness_failures == []
    assert report.rating.value == "high"
