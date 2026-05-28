import json
from pathlib import Path

from code_context_graph.brd.context_builder import PromptContext
from code_context_graph.brd.generator import Generator
from code_context_graph.brd.schema import BRD, Strategy


def _ctx() -> PromptContext:
    return PromptContext(
        repo_id="acme",
        summary_text="# acme\n- top entity",
        files=[("src/a.py", "def foo(): pass\n")],
        strategy="single_shot",
        clusters=None,
        estimated_tokens=100,
    )


def _scripted_brd_json() -> str:
    return json.dumps({
        "sections": [
            {"title": "Executive Summary", "body_markdown": "Summary text.", "requirements": []},
            {"title": "Functional Requirements", "body_markdown": "Features:",
             "requirements": [{"id": "FR-1", "text": "Authenticate users."}]},
        ],
        "evidence_map": {"FR-1": ["src/a.py"]},
    })


def test_single_shot_returns_brd(fake_anthropic):
    fake_anthropic.script(_scripted_brd_json())
    gen = Generator(anthropic=fake_anthropic, model="claude-opus-4-7[1m]")
    brd = gen.generate(_ctx())
    assert isinstance(brd, BRD)
    assert brd.strategy == Strategy.single_shot
    assert any(s.title == "Functional Requirements" for s in brd.sections)
    assert brd.evidence_map["FR-1"] == ["src/a.py"]


def test_single_shot_passes_revision_guidance(fake_anthropic):
    fake_anthropic.script(_scripted_brd_json())
    gen = Generator(anthropic=fake_anthropic, model="claude-opus-4-7[1m]")
    gen.generate(_ctx(), revision_guidance="Address FR-2 missing.")
    sent = fake_anthropic.calls[-1]
    # The user message should mention prior judge feedback
    user_text = sent["messages"][-1]["content"]
    assert "Address FR-2 missing." in user_text
