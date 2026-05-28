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
