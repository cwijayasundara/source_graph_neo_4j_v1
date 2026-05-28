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


REDUCE_SYSTEM = """You are merging multiple cluster-scoped BRDs into a single
unified BRD for the whole repository. Deduplicate requirements, reconcile
contradictions, prefer the more specific wording, and keep the 11-section
structure exactly. Preserve every entity reference (do not drop evidence pointers).
Return JSON in the same schema as a single BRD."""


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


def _build_cluster_message(ctx: PromptContext, cluster_files: list[str],
                           revision_guidance: str | None) -> str:
    source_by_path = dict(ctx.files)
    parts: list[str] = ["## Graph summary\n", ctx.summary_text,
                        f"\n\n## Cluster files ({len(cluster_files)} files)\n"]
    for path in cluster_files:
        src = source_by_path.get(path, "")
        parts.append(f"\n### {path}\n```\n{src}\n```\n")
    if revision_guidance:
        parts.append("\n\n## Judge feedback to address\n")
        parts.append(revision_guidance)
    return "".join(parts)


def _build_reduce_message(sub_brds: list[BRD], revision_guidance: str | None) -> str:
    payload = [b.model_dump(mode="json") for b in sub_brds]
    text = "## Sub-BRDs to merge\n```json\n" + json.dumps(payload) + "\n```"
    if revision_guidance:
        text += "\n\n## Judge feedback to address\n" + revision_guidance
    return text


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
        if not ctx.clusters:
            raise ValueError("map_reduce strategy requires clusters")
        # map
        sub_brds: list[BRD] = []
        for cluster_files in ctx.clusters:
            try:
                cluster_text = self._call(_build_cluster_message(ctx, cluster_files, revision_guidance))
                sub_brds.append(_parse_brd(cluster_text, repo_id=ctx.repo_id, model=self.model,
                                            strategy=Strategy.map_reduce))
            except Exception:
                # one failed cluster becomes a partial; reduce sees the gap
                sub_brds.append(BRD(
                    sections=[BRDSection(title="Executive Summary",
                                         body_markdown="<cluster failed to generate; partial>",
                                         requirements=[])],
                    evidence_map={}, repo_id=ctx.repo_id, model=self.model,
                    strategy=Strategy.map_reduce,
                ))
        # reduce
        response = self.anthropic.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=REDUCE_SYSTEM,
            messages=[{"role": "user", "content": _build_reduce_message(sub_brds, revision_guidance)}],
        )
        usage = getattr(response, "usage", None)
        if usage is not None:
            self.token_usage["input"] += getattr(usage, "input_tokens", 0) or 0
            self.token_usage["output"] += getattr(usage, "output_tokens", 0) or 0
        return _parse_brd(response.content[0].text, repo_id=ctx.repo_id,
                          model=self.model, strategy=Strategy.map_reduce)
