from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from code_context_graph import schema
from code_context_graph.neo4j_client import Neo4jClient


class RepoManager:
    """Track ingested repositories as :Repository nodes in Neo4j."""

    def __init__(self, client: Neo4jClient) -> None:
        self.client = client

    def ensure_constraints(self) -> None:
        # Kept for backwards compatibility; the canonical constraint definitions
        # live in schema.CONSTRAINTS and are applied via Neo4jClient.apply_schema.
        self.client.apply_schema()

    def register(
        self,
        slug: str,
        url: str,
        local_path: str,
        stats: dict[str, int],
    ) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        self.client.run(
            """
            MERGE (r:Repository {slug: $slug})
            SET r.url = $url,
                r.local_path = $local_path,
                r.files_parsed = $files_parsed,
                r.entities = $entities,
                r.relationships = $relationships,
                r.authors = $authors,
                r.ingested_at = $ingested_at
            """,
            slug=slug,
            url=url,
            local_path=local_path,
            files_parsed=stats.get("files_parsed", 0),
            entities=stats.get("entities", 0),
            relationships=stats.get("relationships", 0),
            authors=stats.get("authors", 0),
            ingested_at=now,
        )
        return self.get(slug)

    def tag_entities(self, slug: str) -> int:
        result = self.client.run(
            """
            MATCH (e:CodeEntity) WHERE e.repo IS NULL
            SET e.repo = $slug
            RETURN count(e) AS tagged
            """,
            slug=slug,
        )
        return result[0]["tagged"] if result else 0

    def link_files_to_modules(self, slug: str) -> int:
        """Create one :File node per distinct file_path in the repo and link
        every :Module CodeEntity to it via [:DEFINED_IN]. Returns file count."""
        rows = self.client.run(schema.LINK_FILES_FOR_REPO, slug=slug)
        return rows[0]["file_count"] if rows else 0

    @staticmethod
    def _normalize_repo(props: dict) -> dict:
        return {
            "slug": props.get("slug"),
            "url": props.get("url"),
            "files_parsed": props.get("files_parsed", 0),
            "entities": props.get("entities", 0),
            "relationships": props.get("relationships", 0),
            "authors": props.get("authors", 0),
            "ingested_at": props.get("ingested_at"),
            "local_path": props.get("local_path"),
        }

    def list_repos(self) -> list[dict]:
        rows = self.client.run(
            """
            MATCH (r:Repository)
            RETURN properties(r) AS repo
            """
        )
        repos = [self._normalize_repo(row["repo"]) for row in rows]
        return sorted(repos, key=lambda repo: repo["ingested_at"] or "", reverse=True)

    def get(self, slug: str) -> dict | None:
        results = self.client.run(
            """
            MATCH (r:Repository {slug: $slug})
            RETURN properties(r) AS repo
            """,
            slug=slug,
        )
        return self._normalize_repo(results[0]["repo"]) if results else None

    def delete(self, slug: str) -> bool:
        self.client.run(
            "MATCH (e:CodeEntity {repo: $slug}) DETACH DELETE e",
            slug=slug,
        )
        self.client.run(schema.DELETE_FILES_FOR_REPO, slug=slug)
        self.client.run(
            "MATCH (r:Repository {slug: $slug}) DETACH DELETE r",
            slug=slug,
        )
        return True
