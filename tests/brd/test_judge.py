from code_context_graph.brd.context_builder import PromptContext
from code_context_graph.brd.schema import BRD, BRDSection, Requirement, Strategy


def _ctx_with_entities(entities: list[str]) -> PromptContext:
    summary = "Top entities:\n" + "\n".join(f"- {e}" for e in entities)
    return PromptContext(
        repo_id="acme", summary_text=summary,
        files=[("src/a.py", "def foo(): pass")],
        strategy="single_shot", clusters=None, estimated_tokens=10,
    )


def _brd_with_evidence(evidence: dict[str, list[str]]) -> BRD:
    return BRD(
        sections=[BRDSection(title="Executive Summary", body_markdown="", requirements=[])],
        evidence_map=evidence,
        repo_id="acme", model="m", strategy=Strategy.single_shot,
    )


def test_groundedness_passes_when_all_entities_in_context():
    from code_context_graph.brd.judge import groundedness_failures
    ctx = _ctx_with_entities(["src/a.py:foo"])
    brd = _brd_with_evidence({"FR-1": ["src/a.py:foo", "src/a.py"]})
    assert groundedness_failures(brd, ctx) == []


def test_groundedness_flags_unknown_entity():
    from code_context_graph.brd.judge import groundedness_failures
    ctx = _ctx_with_entities(["src/a.py:foo"])
    brd = _brd_with_evidence({"FR-1": ["src/a.py:foo", "src/ghost.py:made_up"]})
    failures = groundedness_failures(brd, ctx)
    assert "src/ghost.py:made_up" in failures
    assert "src/a.py:foo" not in failures


import json as _json

from code_context_graph.brd.schema import Dimension, JudgeReport, Rating


def _judge_payload(c=5, a=5, cl=5, co=5, ac=5, feedback=None):
    return _json.dumps({
        "dimensions": {
            "completeness":  {"score": c,  "rationale": "ok"},
            "accuracy":      {"score": a,  "rationale": "ok"},
            "clarity":       {"score": cl, "rationale": "ok"},
            "consistency":   {"score": co, "rationale": "ok"},
            "actionability": {"score": ac, "rationale": "ok"},
        },
        "feedback": feedback or [],
    })


def test_judge_high_rating(fake_anthropic):
    fake_anthropic.script(_judge_payload(5, 5, 4, 4, 4))
    from code_context_graph.brd.judge import Judge
    j = Judge(anthropic=fake_anthropic, model="claude-opus-4-7[1m]")
    report = j.evaluate(_brd_with_evidence({"FR-1": ["src/a.py:foo"]}),
                        _ctx_with_entities(["src/a.py:foo"]))
    assert report.rating == Rating.high
    assert abs(report.weighted_score - (5*0.25 + 5*0.30 + 4*0.15 + 4*0.15 + 4*0.15)) < 0.001


def test_judge_medium_rating(fake_anthropic):
    fake_anthropic.script(_judge_payload(4, 3, 3, 3, 3))
    from code_context_graph.brd.judge import Judge
    j = Judge(anthropic=fake_anthropic, model="claude-opus-4-7[1m]")
    report = j.evaluate(_brd_with_evidence({"FR-1": ["src/a.py:foo"]}),
                        _ctx_with_entities(["src/a.py:foo"]))
    assert report.rating == Rating.medium


def test_judge_low_when_dimension_below_two(fake_anthropic):
    fake_anthropic.script(_judge_payload(5, 5, 1, 5, 5))
    from code_context_graph.brd.judge import Judge
    j = Judge(anthropic=fake_anthropic, model="claude-opus-4-7[1m]")
    report = j.evaluate(_brd_with_evidence({"FR-1": ["src/a.py:foo"]}),
                        _ctx_with_entities(["src/a.py:foo"]))
    assert report.rating == Rating.low


def test_groundedness_failure_forces_accuracy_le_two(fake_anthropic):
    fake_anthropic.script(_judge_payload(5, 5, 5, 5, 5))
    from code_context_graph.brd.judge import Judge
    j = Judge(anthropic=fake_anthropic, model="claude-opus-4-7[1m]")
    brd = _brd_with_evidence({"FR-1": ["src/ghost.py:nope"]})
    report = j.evaluate(brd, _ctx_with_entities(["src/a.py:foo"]))
    assert report.dimensions[Dimension.accuracy].score <= 2
    assert "src/ghost.py:nope" in report.groundedness_failures
    assert report.rating in (Rating.medium, Rating.low)
