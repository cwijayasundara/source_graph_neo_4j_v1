from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from code_context_graph.agent.brd_judge import ajudge as _ajudge_t
    from code_context_graph.agent.brd_orchestrator import agenerate_brd_draft as _adraft_t
    from code_context_graph.agent.deps import GraphDeps
    from code_context_graph.agent.harness import AgentRunner, SdkAgentRunner

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


@dataclass
class GraphBRDResult:
    """In-memory result of a graph-navigated BRD run, before persistence."""
    brd: BRD
    report: JudgeReport
    rating: Rating
    weighted_score: float
    attempts: int
    attempt_history: list[AttemptRecord]
    strategy: Strategy


def _draft_to_brd(draft, repo_id: str, model: str, strategy: Strategy) -> BRD:
    return BRD(sections=draft.sections, evidence_map=draft.evidence_map,
               repo_id=repo_id, model=model, strategy=strategy)


async def agenerate_brd_graph(deps: GraphDeps, *, runner: AgentRunner, model: str,
                              max_retries: int, max_turns: int,
                              max_subsystems: int) -> GraphBRDResult:
    from code_context_graph.agent.brd_judge import ajudge
    from code_context_graph.agent.brd_orchestrator import agenerate_brd_draft

    attempts: list[AttemptRecord] = []
    best: tuple[BRD, JudgeReport] | None = None

    for attempt_no in range(1, max_retries + 2):
        draft, strategy = await agenerate_brd_draft(
            deps, runner=runner, model=model, max_turns=max_turns,
            max_subsystems=max_subsystems)
        brd = _draft_to_brd(draft, deps.repo_id, model, strategy)
        report = await ajudge(brd, deps, runner=runner, model=model)
        attempts.append(AttemptRecord(attempt=attempt_no, rating=report.rating,
                                      weighted_score=report.weighted_score,
                                      feedback=report.feedback))
        if best is None or report.weighted_score > best[1].weighted_score:
            best = (brd, report)
        if report.rating == Rating.high:
            break

    assert best is not None
    final_brd, final_report = best
    return GraphBRDResult(brd=final_brd, report=final_report,
                          rating=final_report.rating,
                          weighted_score=final_report.weighted_score,
                          attempts=len(attempts), attempt_history=attempts,
                          strategy=final_brd.strategy)


def generate_brd_graph_sync(repo_id: str, *, client=None, repo_path=None,
                            max_retries: int | None = None, model: str | None = None,
                            max_turns: int | None = None,
                            max_subsystems: int | None = None,
                            storage: BRDStorage | None = None) -> BRDResult:
    """Sync entry point for CLI/API. Resolves deps + env defaults, runs the graph
    loop, renders + persists HTML, and returns the existing BRDResult so callers are
    unchanged. Mirrors the old generate_brd() contract."""
    if client is None:
        from code_context_graph.neo4j_client import Neo4jClient
        client = Neo4jClient()
    if repo_path is None:
        from code_context_graph.repo_manager import RepoManager
        repo = RepoManager(client).get(repo_id)
        if repo is None or not repo.get("local_path"):
            raise ValueError(f"Repo {repo_id} not registered or missing local_path")
        repo_path = repo["local_path"]
    model = model or os.getenv("BRD_AGENT_MODEL", "claude-sonnet-4-6")
    max_retries = int(os.getenv("BRD_MAX_RETRIES", "1")) if max_retries is None else max_retries
    max_turns = int(os.getenv("BRD_AGENT_MAX_TURNS", "15")) if max_turns is None else max_turns
    max_subsystems = int(os.getenv("BRD_MAX_SUBSYSTEMS", "12")) if max_subsystems is None else max_subsystems

    from code_context_graph.agent.deps import GraphDeps
    from code_context_graph.agent.harness import SdkAgentRunner
    deps = GraphDeps(client=client, repo_id=repo_id, repo_path=Path(repo_path))
    runner = SdkAgentRunner()
    result = asyncio.run(agenerate_brd_graph(
        deps, runner=runner, model=model, max_retries=max_retries,
        max_turns=max_turns, max_subsystems=max_subsystems))

    html = render_html(result.brd)
    if storage is None:
        storage = BRDStorage(client)
    return storage.save(
        repo_id=repo_id, html=html, judge_report=result.report,
        attempt_history=result.attempt_history, model=model,
        strategy=result.strategy,
        token_usage={"input": runner.token_usage["input"],
                     "output": runner.token_usage["output"]},
    )
