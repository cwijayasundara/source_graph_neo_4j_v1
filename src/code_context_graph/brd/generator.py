from __future__ import annotations

import json
import os
from typing import Any

from code_context_graph.brd.context_builder import PromptContext
from code_context_graph.brd.schema import BRD, BRDSection, Requirement, Strategy


SYSTEM_PROMPT = """You are a senior business analyst writing a Business Requirements
Document (BRD) for an engineering team. You will be given:
1. A graph summary of the codebase (entities, layers, relationships).
2. The full source tree of the repository, file by file.
3. Optionally, judge feedback from a prior attempt that you must address.

Produce a comprehensive BRD with these 11 sections (use exactly these titles):
- Executive Summary
- Business Objectives
- Scope
- Stakeholders
- Functional Requirements
- Non-functional Requirements
- Data & Integrations
- Assumptions
- Constraints
- Risks
- Success Metrics

Rules:
- Every functional requirement MUST be grounded in real entities or files from the
  provided context. Use IDs of the form FR-1, FR-2, ... and NFR-1, NFR-2, ...
- Provide an `evidence_map` linking each requirement ID to the graph entities or
  file paths that justified it. Use real entity qualified_names or paths from the input.
- Do NOT invent classes, functions, or files that aren't in the input.
- Return ONLY valid JSON, no markdown fences, matching this schema:
  {"sections":[{"title": str, "body_markdown": str,
                 "requirements":[{"id": str, "text": str}, ...]}, ...],
   "evidence_map": {req_id: [entity_or_path, ...], ...}}
"""


def _build_user_message(ctx: PromptContext, revision_guidance: str | None) -> str:
    parts: list[str] = []
    parts.append("## Graph summary\n")
    parts.append(ctx.summary_text)
    parts.append("\n\n## Source files\n")
    for path, src in ctx.files:
        parts.append(f"\n### {path}\n```\n{src}\n```\n")
    if revision_guidance:
        parts.append("\n\n## Judge feedback to address in this revision\n")
        parts.append(revision_guidance)
    return "".join(parts)


def _parse_brd(json_text: str, *, repo_id: str, model: str, strategy: Strategy) -> BRD:
    data = json.loads(json_text)
    sections = [
        BRDSection(
            title=s["title"],
            body_markdown=s.get("body_markdown", ""),
            requirements=[Requirement(**r) for r in s.get("requirements", [])],
        )
        for s in data["sections"]
    ]
    return BRD(
        sections=sections,
        evidence_map=data.get("evidence_map", {}),
        repo_id=repo_id,
        model=model,
        strategy=strategy,
    )


def _resolve_model() -> str:
    """Pick the BRD model id, appending the 1M-context suffix only if not already present."""
    base = os.getenv("BRD_MODEL", "claude-opus-4-7")
    return base if "[" in base else f"{base}[1m]"


class Generator:
    def __init__(self, anthropic, model: str | None = None,
                 max_tokens: int = 16_000) -> None:
        self.anthropic = anthropic
        self.model = model or _resolve_model()
        self.max_tokens = max_tokens
        self.token_usage = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}

    def _call(self, user_message: str) -> str:
        response = self.anthropic.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        usage = getattr(response, "usage", None)
        if usage is not None:
            self.token_usage["input"] += getattr(usage, "input_tokens", 0) or 0
            self.token_usage["output"] += getattr(usage, "output_tokens", 0) or 0
            self.token_usage["cache_read"] += getattr(usage, "cache_read_input_tokens", 0) or 0
            self.token_usage["cache_write"] += getattr(usage, "cache_creation_input_tokens", 0) or 0
        return response.content[0].text

    def generate(self, ctx: PromptContext, *, revision_guidance: str | None = None) -> BRD:
        if ctx.strategy == "single_shot":
            text = self._call(_build_user_message(ctx, revision_guidance))
            return _parse_brd(text, repo_id=ctx.repo_id, model=self.model,
                              strategy=Strategy.single_shot)
        # map_reduce path implemented in Task 8
        raise NotImplementedError("map_reduce path added in Task 8")
