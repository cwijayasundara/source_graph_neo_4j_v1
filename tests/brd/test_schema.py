from code_context_graph.brd.schema import (
    BRD,
    BRDSection,
    EvidenceMap,
    Dimension,
    DimensionScore,
    JudgeReport,
    FeedbackItem,
    Rating,
    Strategy,
    AttemptRecord,
    BRDResult,
)


def test_brd_with_evidence_map():
    brd = BRD(
        sections=[
            BRDSection(
                title="Executive Summary",
                body_markdown="A summary.",
                requirements=[],
            ),
        ],
        evidence_map={"FR-1": ["Function:src/x.py:foo"]},
        repo_id="my-repo",
        model="claude-opus-4-7[1m]",
        strategy=Strategy.single_shot,
    )
    assert brd.evidence_map["FR-1"] == ["Function:src/x.py:foo"]


def test_judge_report_rating_computed_from_weighted_score():
    scores = {
        Dimension.completeness: DimensionScore(score=5, rationale="ok"),
        Dimension.accuracy: DimensionScore(score=5, rationale="ok"),
        Dimension.clarity: DimensionScore(score=4, rationale="ok"),
        Dimension.consistency: DimensionScore(score=4, rationale="ok"),
        Dimension.actionability: DimensionScore(score=4, rationale="ok"),
    }
    report = JudgeReport(
        dimensions=scores,
        weighted_score=4.55,
        rating=Rating.high,
        feedback=[],
        groundedness_failures=[],
    )
    assert report.rating == Rating.high


def test_feedback_item_required_fields():
    item = FeedbackItem(
        dimension=Dimension.clarity,
        severity="high",
        suggestion="Define 'tenant' in the glossary.",
        target_section="Scope",
    )
    assert item.dimension == Dimension.clarity
