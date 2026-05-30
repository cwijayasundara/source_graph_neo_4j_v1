from __future__ import annotations

from code_context_graph.brd.context_builder import PromptContext
from code_context_graph.brd.schema import BRD


def _known_references(ctx: PromptContext) -> set[str]:
    known: set[str] = set()
    known.update(path for path, _ in ctx.files)
    # also extract qualified_name-looking tokens from summary_text
    for line in ctx.summary_text.splitlines():
        for token in line.split():
            token = token.strip("`-•,()[]")
            if ":" in token or "/" in token:
                known.add(token)
    return known


def groundedness_failures(brd: BRD, ctx: PromptContext) -> list[str]:
    """Return any references in the evidence_map that do not appear in the context."""
    known = _known_references(ctx)
    failures: list[str] = []
    for refs in brd.evidence_map.values():
        for ref in refs:
            if ref not in known:
                failures.append(ref)
    return failures


import json
import os
from typing import Any

from code_context_graph.brd.schema import (
    Dimension, DimensionScore, FeedbackItem, JudgeReport, Rating,
)


WEIGHTS = {
    Dimension.completeness:  0.25,
    Dimension.accuracy:      0.30,
    Dimension.clarity:       0.15,
    Dimension.consistency:   0.15,
    Dimension.actionability: 0.15,
}


JUDGE_SYSTEM = """You are evaluating a Business Requirements Document (BRD) generated
from a codebase. Score it on five dimensions, each 1-5, with a brief rationale:
- completeness: are all 11 BRD sections present and substantive?
- accuracy: does every claim tie to real entities/code from the context? No hallucinations.
- clarity: readable, unambiguous, no undefined jargon
- consistency: no contradictions across sections; scope matches requirements
- actionability: requirements are testable; success metrics concrete

Also return a `feedback` list of items the next attempt should address. Each item:
{"dimension": one of the five names, "severity": "low"|"medium"|"high",
 "suggestion": string, "target_section": string}

Return ONLY JSON, no markdown fences:
{"dimensions": {"<name>": {"score": int, "rationale": str}, ...},
 "feedback": [...]}
"""


def _resolve_model() -> str:
    return os.getenv("BRD_MODEL", "gemini-3.5-flash")


def _rate(weighted: float, dims: dict[Dimension, DimensionScore]) -> Rating:
    if weighted >= 4.2 and all(d.score >= 3 for d in dims.values()):
        return Rating.high
    if weighted >= 3.2 and all(d.score >= 2 for d in dims.values()):
        return Rating.medium
    return Rating.low


class Judge:
    def __init__(self, llm, model: str | None = None,
                 max_tokens: int = 4000) -> None:
        self.llm = llm
        self.model = model or _resolve_model()
        self.max_tokens = max_tokens

    def _call_judge(self, brd, ctx) -> dict[str, Any]:
        user = (
            "## Context (graph summary)\n" + ctx.summary_text +
            "\n\n## BRD under review\n```json\n" + brd.model_dump_json() + "\n```"
        )
        response = self.llm.messages.create(
            model=self.model, max_tokens=self.max_tokens,
            system=JUDGE_SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        return json.loads(response.content[0].text)

    def evaluate(self, brd, ctx) -> JudgeReport:
        # 1. hard groundedness pre-check
        failures = groundedness_failures(brd, ctx)
        # 2. LLM rubric
        raw = self._call_judge(brd, ctx)
        dims: dict[Dimension, DimensionScore] = {}
        for name, item in raw["dimensions"].items():
            dim = Dimension(name)
            dims[dim] = DimensionScore(score=int(item["score"]), rationale=item.get("rationale", ""))
        # 3. apply groundedness floor
        if failures:
            current = dims[Dimension.accuracy]
            if current.score > 2:
                dims[Dimension.accuracy] = DimensionScore(
                    score=2,
                    rationale=current.rationale + f" [forced to 2 by hallucinated refs: {failures}]",
                )
        # 4. weighted score + rating
        weighted = sum(dims[d].score * w for d, w in WEIGHTS.items())
        rating = _rate(weighted, dims)
        feedback = [FeedbackItem(**item) for item in raw.get("feedback", [])]
        return JudgeReport(
            dimensions=dims, weighted_score=weighted, rating=rating,
            feedback=feedback, groundedness_failures=failures,
        )
