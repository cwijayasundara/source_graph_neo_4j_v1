from __future__ import annotations

from code_context_graph.agent.deps import GraphDeps
from code_context_graph.agent.graph_tools import GRAPH_TOOL_NAMES, build_graph_server
from code_context_graph.agent.harness import AgentRunner

ASK_AGENT_SYSTEM = """You answer a question about ONE repository's code using the
graph-navigation tools: list_subsystems, find_entities, get_entity, neighbors
(CALLS/IMPORTS/CONTAINS/INHERITS), get_source_slice (reads only an entity's lines),
entry_points, integration_points. Inspect only what you need, then answer concisely
and ground the answer in real entity ids / file paths. Emit JSON {"answer": "..."}.
If the graph does not contain enough to answer, say so in the answer."""

_ANSWER_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
}


async def agentic_answer(deps: GraphDeps, *, runner: AgentRunner, question: str,
                         model: str, max_turns: int = 4) -> str | None:
    """Answer a question by navigating the graph (fallback when a single Cypher query
    returns nothing). Returns the answer text, or None if the agent produced nothing."""
    server = build_graph_server(deps)
    raw = await runner.run_structured(
        system=ASK_AGENT_SYSTEM, prompt=question, server=server,
        allowed_tools=GRAPH_TOOL_NAMES, model=model, max_turns=max_turns,
        schema=_ANSWER_SCHEMA,
    )
    answer = (raw or {}).get("answer")
    return answer or None
