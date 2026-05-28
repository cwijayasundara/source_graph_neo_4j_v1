from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RankedFile:
    file_path: str
    centrality: int


@dataclass
class GraphSummary:
    repo_id: str
    files_parsed: int
    entities: int
    relationships: int
    url: str | None
    ingested_at: str | None
    top_entities: list[dict]
    relationship_counts: dict[str, int]


@dataclass
class PromptContext:
    repo_id: str
    summary_text: str   # rendered string for the prompt
    files: list[tuple[str, str]]  # (relative_path, source)
    strategy: str       # "single_shot" | "map_reduce"
    clusters: list[list[str]] | None  # for map_reduce, list of clusters (each = list of file paths)
    estimated_tokens: int


class ContextBuilder:
    """Build the prompt context for the BRD generator from the Neo4j graph + source on disk."""

    def __init__(self, client, *, single_shot_budget: int | None = None,
                 max_cluster_depth: int | None = None) -> None:
        self.client = client
        self.single_shot_budget = single_shot_budget or int(
            os.getenv("BRD_SINGLE_SHOT_TOKEN_BUDGET", "800000")
        )
        self.max_cluster_depth = max_cluster_depth or int(
            os.getenv("BRD_MAX_CLUSTER_DEPTH", "4")
        )

    def build_graph_summary(self, repo_id: str) -> GraphSummary:
        entities = self.client.run(
            """
            MATCH (e:CodeEntity {repo: $repo_id})
            WHERE e.kind IN ['Class','Function','Method','Module']
            OPTIONAL MATCH (e)-[r]-()
            WITH e, count(r) AS degree
            RETURN e.qualified_name AS qualified_name,
                   e.kind AS kind,
                   e.file_path AS file_path,
                   e.signature AS signature,
                   e.docstring AS docstring,
                   e.semantic_layer AS semantic_layer,
                   e.semantic_summary AS semantic_summary
            ORDER BY degree DESC
            LIMIT 200
            """,
            repo_id=repo_id,
        )
        rel_counts = self.client.run(
            """
            MATCH (s:CodeEntity {repo: $repo_id})-[r]->(t)
            RETURN type(r) AS rel_type, count(r) AS count
            ORDER BY count DESC
            """,
            repo_id=repo_id,
        )
        repo_meta = self.client.run(
            """
            MATCH (r:Repository {slug: $repo_id})
            RETURN r.slug AS slug, r.files_parsed AS files_parsed,
                   r.entities AS entities, r.relationships AS relationships,
                   r.url AS url, r.ingested_at AS ingested_at
            """,
            repo_id=repo_id,
        )
        meta = repo_meta[0] if repo_meta else {}
        return GraphSummary(
            repo_id=repo_id,
            files_parsed=int(meta.get("files_parsed") or 0),
            entities=int(meta.get("entities") or 0),
            relationships=int(meta.get("relationships") or 0),
            url=meta.get("url"),
            ingested_at=meta.get("ingested_at"),
            top_entities=entities,
            relationship_counts={row["rel_type"]: row["count"] for row in rel_counts},
        )

    def rank_files(self, repo_id: str) -> list[RankedFile]:
        rows = self.client.run(
            """
            MATCH (e:CodeEntity {repo: $repo_id})
            WHERE e.file_path IS NOT NULL
            OPTIONAL MATCH (e)-[r]-()
            WITH e.file_path AS file_path, sum(case when r is null then 0 else 1 end) AS centrality
            RETURN file_path, centrality
            ORDER BY centrality DESC
            """,
            repo_id=repo_id,
        )
        return [RankedFile(file_path=row["file_path"], centrality=int(row["centrality"])) for row in rows]
