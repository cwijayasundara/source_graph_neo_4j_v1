from pathlib import Path

from code_context_graph.brd.context_builder import PromptContext
from code_context_graph.brd.pipeline import generate_brd
from code_context_graph.brd.schema import (
    BRD, BRDSection, Dimension, DimensionScore, JudgeReport, Rating, Strategy,
)


class _StubGenerator:
    def __init__(self, brds: list[BRD]) -> None:
        self.brds = brds
        self.calls: list[str | None] = []
        self.token_usage = {"input": 1, "output": 1, "cache_read": 0, "cache_write": 0}
        self.model = "claude-opus-4-7[1m]"

    def generate(self, ctx, *, revision_guidance=None):
        self.calls.append(revision_guidance)
        return self.brds.pop(0)


class _StubJudge:
    def __init__(self, reports: list[JudgeReport]) -> None:
        self.reports = reports

    def evaluate(self, brd, ctx):
        return self.reports.pop(0)


def _brd() -> BRD:
    return BRD(
        sections=[BRDSection(title="Executive Summary", body_markdown="", requirements=[])],
        evidence_map={}, repo_id="acme", model="m", strategy=Strategy.single_shot,
    )


def _report(rating: Rating, score: float = 3.0) -> JudgeReport:
    return JudgeReport(
        dimensions={d: DimensionScore(score=3, rationale="") for d in Dimension},
        weighted_score=score, rating=rating, feedback=[], groundedness_failures=[],
    )


def test_pipeline_short_circuits_on_high(fake_client, tmp_path):
    ctx = PromptContext(repo_id="acme", summary_text="s", files=[],
                        strategy="single_shot", clusters=None, estimated_tokens=10)
    gen = _StubGenerator([_brd()])
    judge = _StubJudge([_report(Rating.high, 4.5)])
    result = generate_brd(
        repo_id="acme", repo_path=tmp_path,
        client=fake_client, context=ctx, generator=gen, judge=judge,
        max_retries=2,
    )
    assert result.rating == Rating.high
    assert result.attempts == 1
    assert gen.calls == [None]


def test_pipeline_retries_with_feedback_then_succeeds(fake_client, tmp_path):
    ctx = PromptContext(repo_id="acme", summary_text="s", files=[],
                        strategy="single_shot", clusters=None, estimated_tokens=10)
    gen = _StubGenerator([_brd(), _brd(), _brd()])
    judge = _StubJudge([_report(Rating.low, 2.0), _report(Rating.medium, 3.5),
                        _report(Rating.high, 4.5)])
    result = generate_brd(
        repo_id="acme", repo_path=tmp_path,
        client=fake_client, context=ctx, generator=gen, judge=judge,
        max_retries=2,
    )
    assert result.attempts == 3
    assert result.rating == Rating.high
    assert gen.calls[0] is None
    assert gen.calls[1] is not None and gen.calls[2] is not None


def test_pipeline_returns_best_attempt_after_max_retries(fake_client, tmp_path):
    ctx = PromptContext(repo_id="acme", summary_text="s", files=[],
                        strategy="single_shot", clusters=None, estimated_tokens=10)
    gen = _StubGenerator([_brd(), _brd(), _brd()])
    judge = _StubJudge([_report(Rating.low, 2.0), _report(Rating.medium, 3.5),
                        _report(Rating.low, 2.5)])
    result = generate_brd(
        repo_id="acme", repo_path=tmp_path,
        client=fake_client, context=ctx, generator=gen, judge=judge,
        max_retries=2,
    )
    assert result.attempts == 3
    # best attempt is #2 (medium, 3.5)
    assert result.rating == Rating.medium
    assert result.weighted_score == 3.5
