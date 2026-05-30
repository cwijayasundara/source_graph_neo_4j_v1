from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol

from code_context_graph.neo4j_client import Neo4jClient


DEFAULT_LIMIT = 50

BLOCKED_CYPHER_RE = re.compile(
    r"\b("
    r"CREATE|MERGE|SET|DELETE|DETACH|DROP|REMOVE|LOAD\s+CSV|CALL|FOREACH|"
    r"CREATE\s+INDEX|CREATE\s+CONSTRAINT|ALTER|GRANT|DENY|REVOKE|START|STOP"
    r")\b",
    re.IGNORECASE,
)
READ_PREFIX_RE = re.compile(r"^\s*(MATCH|OPTIONAL\s+MATCH|WITH|UNWIND)\b", re.IGNORECASE)


class CypherValidationError(ValueError):
    """Raised when generated Cypher is not safe to execute."""


class LLMClient(Protocol):
    def generate_text(self, prompt: str) -> str:
        ...


@dataclass
class AskCodebaseResult:
    answer: str
    cypher: str
    rows: list[dict]
    explanation: str


class AnthropicTextClient:
    """LLMClient backed by Claude (Anthropic Messages API), used for the two text
    steps of ask_codebase: Cypher generation and answer summarization. Synchronous,
    Haiku-tier by default via resolve_model('ask')."""

    def __init__(self, model: str | None = None, max_tokens: int = 1024) -> None:
        from code_context_graph.agent.models import resolve_model
        self.model = model or resolve_model("ask")
        self.max_tokens = max_tokens

    def generate_text(self, prompt: str) -> str:
        from anthropic import Anthropic
        client = Anthropic()
        resp = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(getattr(b, "text", "") for b in resp.content)


def enforce_read_only_cypher(cypher: str, limit: int = DEFAULT_LIMIT) -> str:
    cleaned = cypher.strip().rstrip(";")
    if not cleaned:
        raise CypherValidationError("Generated Cypher is empty")
    if not READ_PREFIX_RE.search(cleaned):
        raise CypherValidationError("Generated Cypher must start with a read-only clause")
    if BLOCKED_CYPHER_RE.search(cleaned):
        raise CypherValidationError("Generated Cypher contains a blocked clause")
    if "$repo" not in cleaned:
        raise CypherValidationError("Generated Cypher must scope results with $repo")
    if not re.search(r"\bLIMIT\s+\d+\b", cleaned, flags=re.IGNORECASE):
        cleaned = f"{cleaned}\nLIMIT {limit}"
    return cleaned


def ask_codebase(
    client: Neo4jClient,
    repo: str,
    question: str,
    llm: LLMClient | None = None,
    runner=None,
    repo_path=None,
) -> AskCodebaseResult:
    if not question.strip():
        raise ValueError("Question is required")
    model = llm or AnthropicTextClient()

    generation = _parse_generation_response(
        model.generate_text(_build_cypher_prompt(repo=repo, question=question))
    )
    cypher = enforce_read_only_cypher(generation["cypher"])
    rows = client.run(cypher, repo=repo)
    explanation = generation.get("explanation", "")

    if not rows:
        fallback = _graph_fallback(client, repo, question, runner=runner,
                                   repo_path=repo_path)
        if fallback:
            return AskCodebaseResult(
                answer=fallback, cypher=cypher, rows=rows,
                explanation=(explanation + " (answered via graph navigation)").strip())

    answer = model.generate_text(
        _build_summary_prompt(question=question, cypher=cypher, rows=rows))
    return AskCodebaseResult(answer=answer, cypher=cypher, rows=rows,
                             explanation=explanation)


def _graph_fallback(client, repo, question, *, runner=None, repo_path=None):
    """Answer via graph navigation when a single Cypher query returned no rows.
    Best-effort: returns None (so the caller summarizes the empty result) if the repo
    has no local path or the agent produced nothing."""
    import asyncio
    from pathlib import Path

    if repo_path is None:
        from code_context_graph.repo_manager import RepoManager
        meta = RepoManager(client).get(repo)
        if not meta or not meta.get("local_path"):
            return None
        repo_path = meta["local_path"]

    from code_context_graph.agent.deps import GraphDeps
    from code_context_graph.agent.ask_agent import agentic_answer
    from code_context_graph.agent.models import resolve_model

    if runner is None:
        from code_context_graph.agent.harness import SdkAgentRunner
        runner = SdkAgentRunner()
    deps = GraphDeps(client=client, repo_id=repo, repo_path=Path(repo_path))
    try:
        return asyncio.run(agentic_answer(
            deps, runner=runner, question=question,
            model=resolve_model("ask"), max_turns=4))
    except Exception:
        return None


def _parse_generation_response(text: str) -> dict[str, str]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise RuntimeError("the model did not return valid JSON for Cypher generation") from exc
    cypher = payload.get("cypher")
    if not isinstance(cypher, str):
        raise RuntimeError("the model response did not include a Cypher string")
    explanation = payload.get("explanation", "")
    if not isinstance(explanation, str):
        explanation = ""
    return {"cypher": cypher, "explanation": explanation}


def _build_cypher_prompt(repo: str, question: str) -> str:
    return f"""\
You generate read-only Neo4j Cypher for a code knowledge graph.

Return ONLY JSON with this shape:
{{"cypher":"MATCH ... RETURN ...","explanation":"short explanation"}}

Hard rules:
- Query only the selected repository: {repo}
- Include `e.repo = $repo`, or the equivalent source entity repo filter, in the WHERE clause.
- Use the `$repo` parameter exactly.
- Use only read clauses: MATCH, OPTIONAL MATCH, WHERE, WITH, UNWIND, RETURN, ORDER BY, LIMIT.
- Do not use CALL, CREATE, MERGE, SET, DELETE, DETACH, DROP, LOAD CSV, APOC, GDS, or schema commands.
- Return at most 50 rows.

Graph schema:
- (:CodeEntity) properties: qualified_name, simple_name, kind, file_path, start_line, end_line, signature, docstring, complexity, repo
- (:Author) properties: name, email, commit_count
- Relationships:
  - (:CodeEntity)-[:CALLS]->(:CodeEntity)
  - (:CodeEntity)-[:IMPORTS]->(:CodeEntity)
  - (:CodeEntity)-[:DEFINES]->(:CodeEntity)
  - (:CodeEntity)-[:CONTAINS]->(:CodeEntity)
  - (:CodeEntity)-[:INHERITS]->(:CodeEntity)
  - (:CodeEntity)-[:DECORATES]->(:CodeEntity)
  - (:CodeEntity)-[:RAISES]->(:CodeEntity)
  - (:CodeEntity)-[:AUTHORED_BY]->(:Author)
  - (:CodeEntity)-[:CO_CHANGED_WITH]-(:CodeEntity)

Useful entity kinds include Module, Class, Enum, Function, Method, Constant, GlobalVar, External.

Question: {question}
"""


def _build_summary_prompt(question: str, cypher: str, rows: list[dict]) -> str:
    rows_json = json.dumps(rows[:DEFAULT_LIMIT], indent=2, default=str)
    return f"""\
Answer the user's codebase question using only these Neo4j query results.
Keep the answer concise and mention when the result set is empty.

Question: {question}

Cypher:
{cypher}

Rows:
{rows_json}
"""
