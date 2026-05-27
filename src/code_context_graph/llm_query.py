from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Protocol

import httpx
from dotenv import load_dotenv

from code_context_graph.neo4j_client import Neo4jClient


DEFAULT_MODEL = "gemini-3.5-flash"
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


class GeminiClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        load_dotenv()
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY", "")
        self.model = model or os.getenv("CODE_GRAPH_LLM_MODEL", DEFAULT_MODEL)
        self.timeout = timeout
        if not self.api_key:
            raise RuntimeError("GOOGLE_API_KEY is not set")

    def generate_text(self, prompt: str) -> str:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1},
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, params={"key": self.api_key}, json=payload)
            response.raise_for_status()
            data = response.json()
        try:
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(part.get("text", "") for part in parts).strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Gemini returned an unexpected response shape") from exc


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
) -> AskCodebaseResult:
    if not question.strip():
        raise ValueError("Question is required")
    model = llm or GeminiClient()

    generation = _parse_generation_response(
        model.generate_text(_build_cypher_prompt(repo=repo, question=question))
    )
    cypher = enforce_read_only_cypher(generation["cypher"])
    rows = client.run(cypher, repo=repo)
    answer = model.generate_text(
        _build_summary_prompt(
            question=question,
            cypher=cypher,
            rows=rows,
        )
    )
    return AskCodebaseResult(
        answer=answer,
        cypher=cypher,
        rows=rows,
        explanation=generation.get("explanation", ""),
    )


def _parse_generation_response(text: str) -> dict[str, str]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Gemini did not return valid JSON for Cypher generation") from exc
    cypher = payload.get("cypher")
    if not isinstance(cypher, str):
        raise RuntimeError("Gemini response did not include a Cypher string")
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
