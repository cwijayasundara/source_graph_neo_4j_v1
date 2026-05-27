"""Read-only Cypher execution tool for the financial context graph."""

import json
import re
from neo4j import Driver

WRITE_KEYWORDS = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|CALL\s+\{)\b", re.I
)


def _is_read_only(query: str) -> bool:
    """Return True if the query contains no write operations."""
    return not bool(WRITE_KEYWORDS.search(query))


def make_execute_cypher(driver: Driver):
    """Create a read-only Cypher execution function bound to *driver*."""

    def execute_cypher(query: str, params: dict | None = None) -> str:
        """Execute a read-only Cypher query against the Neo4j context graph.

        Returns results as JSON. Write operations are blocked.
        """
        if not _is_read_only(query):
            return json.dumps(
                {
                    "error": "Write operations are not allowed. "
                    "Use read-only queries (MATCH/RETURN)."
                }
            )
        with driver.session() as session:
            result = session.run(query, params or {})
            records = [dict(record) for record in result]
            return json.dumps(records, default=str)

    return execute_cypher
