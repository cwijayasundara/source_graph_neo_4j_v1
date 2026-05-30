from __future__ import annotations

import pytest

from code_context_graph.agent.deps import GraphDeps
from code_context_graph.brd.pipeline import agenerate_brd_graph
from tests.agent.conftest import SeededNeo4j


# One seeded graph shape per language. The agent layer must treat them identically:
# only entity ids/kinds/edges differ, never code branches.
LANG_FIXTURES = {
    "python": [{"qn": "app.main"}, {"qn": "app.db"}],
    "java":   [{"qn": "com.app.Main"}, {"qn": "com.app.Repo"}],
    "rust":   [{"qn": "app::main"}, {"qn": "app::store"}],
    "cobol":  [{"qn": "PAYROLL"}, {"qn": "TAXCALC"}],
}


@pytest.mark.asyncio
@pytest.mark.parametrize("lang,nodes", LANG_FIXTURES.items())
async def test_brd_generates_for_each_language(lang, nodes, tmp_path, fake_runner):
    seeded = SeededNeo4j()
    seeded.when(lambda q, p: "RETURN e.qualified_name AS qn" in q, nodes)
    seeded.when(lambda q, p: "RETURN a.qualified_name AS src" in q,
                [{"src": nodes[0]["qn"], "dst": nodes[1]["qn"]}])  # connected -> 1 subsystem
    first = nodes[0]["qn"]
    seeded.when(lambda q, p: "RETURN DISTINCT e.qualified_name" in q,
                [{"qualified_name": n["qn"], "file_path": f"{n['qn']}.src"} for n in nodes])
    deps = GraphDeps(client=seeded, repo_id=lang, repo_path=tmp_path)
    fake_runner.script(
        {"sections": [{"title": "Functional Requirements", "body_markdown": "x",
                       "requirements": [{"id": "FR-1", "text": "t"}]}],
         "evidence_map": {"FR-1": [first]}},
        {"items": [{"dimension": d, "score": 4, "rationale": ""} for d in
                   ["completeness", "accuracy", "clarity", "consistency", "actionability"]],
         "feedback": []},
    )
    result = await agenerate_brd_graph(deps, runner=fake_runner, model="m",
                                       max_retries=0, max_turns=5, max_subsystems=12)
    assert result.brd.sections, f"{lang}: BRD had no sections"
    assert result.brd.evidence_map == {"FR-1": [first]}, f"{lang}: evidence dropped"
