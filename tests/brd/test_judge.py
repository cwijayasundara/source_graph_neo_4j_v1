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
