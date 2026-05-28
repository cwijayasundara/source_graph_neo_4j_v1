from datetime import datetime, timezone
from pathlib import Path

from code_context_graph.brd.schema import (
    AttemptRecord, BRDResult, Dimension, DimensionScore, FeedbackItem,
    JudgeReport, Rating, Strategy,
)
from code_context_graph.brd.storage import BRDStorage


def _sample_judge_report() -> JudgeReport:
    return JudgeReport(
        dimensions={
            d: DimensionScore(score=5, rationale="ok") for d in Dimension
        },
        weighted_score=5.0,
        rating=Rating.high,
        feedback=[],
        groundedness_failures=[],
    )


def test_save_writes_html_file_and_returns_path(tmp_path, fake_client):
    storage = BRDStorage(fake_client, output_dir=tmp_path)
    fake_client.script([{"max_version": None}])  # no prior versions

    result = storage.save(
        repo_id="acme-app",
        html="<html><body>hello</body></html>",
        judge_report=_sample_judge_report(),
        attempt_history=[
            AttemptRecord(attempt=1, rating=Rating.high, weighted_score=5.0, feedback=[]),
        ],
        model="claude-opus-4-7[1m]",
        strategy=Strategy.single_shot,
        token_usage={"input": 10, "output": 5},
    )

    assert isinstance(result, BRDResult)
    assert result.version == 1
    path = Path(result.html_path)
    assert path.exists()
    assert path.read_text() == "<html><body>hello</body></html>"
    assert path.parent.name == "acme-app"


def test_save_increments_version(tmp_path, fake_client):
    storage = BRDStorage(fake_client, output_dir=tmp_path)
    fake_client.script([{"max_version": 3}])

    result = storage.save(
        repo_id="acme-app",
        html="<p>v4</p>",
        judge_report=_sample_judge_report(),
        attempt_history=[],
        model="claude-opus-4-7[1m]",
        strategy=Strategy.single_shot,
        token_usage={},
    )
    assert result.version == 4
