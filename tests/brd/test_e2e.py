import json
from pathlib import Path

import pytest

from code_context_graph.brd.context_builder import PromptContext
from code_context_graph.brd.generator import Generator
from code_context_graph.brd.judge import Judge
from code_context_graph.brd.pipeline import generate_brd
from code_context_graph.brd.schema import Rating, Strategy
from code_context_graph.brd.storage import BRDStorage


CASSETTE = Path(__file__).parent / "cassettes" / "sample_repo_run.json"


class _Cassette:
    """Alternating fake LLM — odd calls return generator responses, even return judge."""

    def __init__(self, payload: dict) -> None:
        self._gen = list(payload["generator_responses"])
        self._jud = list(payload["judge_responses"])
        self.messages = self
        self._mode = "gen"  # toggles between gen and jud

    def create(self, **kwargs):
        text = self._gen.pop(0) if self._mode == "gen" else self._jud.pop(0)
        self._mode = "jud" if self._mode == "gen" else "gen"

        class B:
            def __init__(self, t): self.text = t
        class U:
            input_tokens = 1; output_tokens = 1
            cache_read_input_tokens = 0; cache_creation_input_tokens = 0
        class R:
            def __init__(self, t): self.content = [B(t)]; self.usage = U()
        return R(text)


@pytest.mark.skipif(not CASSETTE.exists(), reason="cassette missing")
def test_end_to_end_with_cassette(fake_client, tmp_path):
    payload = json.loads(CASSETTE.read_text())
    cassette = _Cassette(payload)

    # Hand-built context bypassing the graph queries
    ctx = PromptContext(
        repo_id="sample", summary_text="Top entities:\n- src/code_context_graph/parser.py",
        files=[("src/code_context_graph/parser.py", "x = 1")],
        strategy="single_shot", clusters=None, estimated_tokens=10,
    )
    gen = Generator(llm=cassette, model="gemini-3.5-flash")
    judge = Judge(llm=cassette, model="gemini-3.5-flash")

    # Storage: tmp_path so we don't write into the repo
    storage = BRDStorage(fake_client, output_dir=tmp_path)
    # Scripted save Cypher: returns version=1 (the atomic save query in storage)
    fake_client.script([{"version": 1}])

    result = generate_brd(
        repo_id="sample",
        client=fake_client,
        context=ctx,
        generator=gen,
        judge=judge,
        storage=storage,
        max_retries=2,
    )
    assert result.rating == Rating.high
    assert result.strategy == Strategy.single_shot
    assert Path(result.html_path).exists()
    # confirm the HTML mentions the requirement that survived
    html = Path(result.html_path).read_text()
    assert "FR-1" in html
    assert "Parse Python source files into a graph." in html
