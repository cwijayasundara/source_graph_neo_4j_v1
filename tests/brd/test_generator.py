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


def _scripted_sub_brd_json(cluster_id: str) -> str:
    import json as _j
    return _j.dumps({
        "sections": [
            {"title": "Executive Summary", "body_markdown": f"Cluster {cluster_id}", "requirements": []},
            {"title": "Functional Requirements", "body_markdown": "",
             "requirements": [{"id": f"FR-{cluster_id}", "text": f"Feature {cluster_id}."}]},
        ],
        "evidence_map": {f"FR-{cluster_id}": [f"src/{cluster_id}/mod.py"]},
    })


def test_map_reduce_runs_one_call_per_cluster_then_reduce(fake_anthropic):
    map_a = _scripted_sub_brd_json("a")
    map_b = _scripted_sub_brd_json("b")
    # reduce returns merged BRD
    reduce_out = _scripted_brd_json().replace(
        '"FR-1"', '"FR-a"'
    )
    fake_anthropic.script(map_a, map_b, reduce_out)
    ctx = PromptContext(
        repo_id="acme",
        summary_text="summary",
        files=[("src/a/mod.py", "code a"), ("src/b/mod.py", "code b")],
        strategy="map_reduce",
        clusters=[["src/a/mod.py"], ["src/b/mod.py"]],
        estimated_tokens=10,
    )
    gen = Generator(anthropic=fake_anthropic, model="claude-opus-4-7[1m]")
    brd = gen.generate(ctx)
    assert brd.strategy == Strategy.map_reduce
    assert len(fake_anthropic.calls) == 3  # 2 maps + 1 reduce
