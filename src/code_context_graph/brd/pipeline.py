from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from code_context_graph.brd.context_builder import ContextBuilder, PromptContext
from code_context_graph.brd.generator import Generator
from code_context_graph.brd.judge import Judge
from code_context_graph.brd.renderer import render_html
from code_context_graph.brd.storage import BRDStorage
from code_context_graph.brd.schema import (
    AttemptRecord, BRD, BRDResult, JudgeReport, Rating, Strategy,
)


def _feedback_to_text(report: JudgeReport) -> str:
    lines = [f"Prior rating: {report.rating.value} (weighted score {report.weighted_score:.2f})."]
    if report.groundedness_failures:
        lines.append("Hallucinated references to remove: " + ", ".join(report.groundedness_failures))
    for item in report.feedback:
        lines.append(
            f"[{item.dimension.value}/{item.severity}] {item.target_section}: {item.suggestion}"
        )
    return "\n".join(lines)


def generate_brd(
    repo_id: str,
    *,
    repo_path: Path | str | None = None,
    max_retries: Optional[int] = None,
    force_map_reduce: bool = False,
    client=None,
    context: PromptContext | None = None,
    generator: Generator | None = None,
    judge: Judge | None = None,
    storage: BRDStorage | None = None,
) -> BRDResult:
    if max_retries is None:
        max_retries = int(os.getenv("BRD_MAX_RETRIES", "2"))

    # Track whether the caller provided a pre-built context (test mode).
    test_mode = context is not None

    if context is None:
        if client is None:
            from code_context_graph.neo4j_client import Neo4jClient
            client = Neo4jClient()
        if repo_path is None:
            from code_context_graph.repo_manager import RepoManager
            repo = RepoManager(client).get(repo_id)
            if repo is None or not repo.get("local_path"):
                raise ValueError(f"Repo {repo_id} not registered or missing local_path")
            repo_path = Path(repo["local_path"])
        builder = ContextBuilder(client)
        context = builder.build(repo_id, repo_path=Path(repo_path),
                                force_map_reduce=force_map_reduce)

    if generator is None:
        from code_context_graph.gemini_llm import GeminiMessagesClient
        generator = Generator(llm=GeminiMessagesClient())
    if judge is None:
        from code_context_graph.gemini_llm import GeminiMessagesClient
        judge = Judge(llm=GeminiMessagesClient())
    # Only auto-create storage in production mode (no pre-built context).
    if storage is None and not test_mode and client is not None:
        storage = BRDStorage(client)

    attempts: list[AttemptRecord] = []
    best: tuple[BRD, JudgeReport] | None = None
    feedback_text: str | None = None

    for attempt_no in range(1, max_retries + 2):
        brd = generator.generate(context, revision_guidance=feedback_text)
        report = judge.evaluate(brd, context)
        attempts.append(AttemptRecord(
            attempt=attempt_no, rating=report.rating,
            weighted_score=report.weighted_score, feedback=report.feedback,
        ))
        if best is None or report.weighted_score > best[1].weighted_score:
            best = (brd, report)
        if report.rating == Rating.high:
            break
        feedback_text = _feedback_to_text(report)

    assert best is not None
    final_brd, final_report = best
    html = render_html(final_brd)

    if storage is not None:
        return storage.save(
            repo_id=repo_id, html=html, judge_report=final_report,
            attempt_history=attempts, model=generator.model,
            strategy=Strategy(context.strategy),
            token_usage=generator.token_usage,
        )

    # Storage-less path (test mode or no client).
    return BRDResult(
        brd_id=str(uuid.uuid4()), repo_id=repo_id, version=1,
        rating=final_report.rating, weighted_score=final_report.weighted_score,
        attempts=len(attempts), attempt_history=attempts,
        model=generator.model, strategy=Strategy(context.strategy),
        html_path="(not saved)", created_at=datetime.now(timezone.utc),
        token_usage=generator.token_usage,
    )
