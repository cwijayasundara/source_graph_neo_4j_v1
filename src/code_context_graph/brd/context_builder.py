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


def estimate_tokens(text: str) -> int:
    """Char-over-4 heuristic; cheap and good enough for budget gating."""
    return len(text) // 4


def _format_summary_text(summary: "GraphSummary") -> str:
    lines: list[str] = []
    lines.append(f"# Repository: {summary.repo_id}")
    if summary.url:
        lines.append(f"Source: {summary.url}")
    lines.append(
        f"Files parsed: {summary.files_parsed} | "
        f"Entities: {summary.entities} | Relationships: {summary.relationships}"
    )
    lines.append("\n## Relationship distribution")
    for rel, count in summary.relationship_counts.items():
        lines.append(f"- {rel}: {count}")
    lines.append("\n## Top entities (by graph centrality)")
    for e in summary.top_entities:
        sig = e.get("signature") or ""
        layer = e.get("semantic_layer") or ""
        summary_str = e.get("semantic_summary") or ""
        lines.append(
            f"- [{e['kind']}] {e['qualified_name']}"
            + (f" — {layer}" if layer else "")
            + (f" — {summary_str}" if summary_str else "")
        )
    return "\n".join(lines)


def _load_source(repo_path: Path, file_path: str) -> str | None:
    full = (repo_path / file_path)
    try:
        return full.read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, IsADirectoryError, PermissionError):
        return None


def _cluster_by_top_dir(file_paths: list[str], depth: int = 1) -> dict[str, list[str]]:
    clusters: dict[str, list[str]] = {}
    for fp in file_paths:
        parts = fp.split("/")
        key = "/".join(parts[:depth]) if len(parts) > depth else parts[0]
        clusters.setdefault(key, []).append(fp)
    return clusters


def _split_oversized_cluster(
    files: list[tuple[str, str]],
    budget: int,
    current_depth: int,
    max_depth: int,
) -> list[list[tuple[str, str]]]:
    """If a cluster overruns the budget, recursively split by deeper directory."""
    total = sum(estimate_tokens(src) for _, src in files)
    if total <= budget or current_depth >= max_depth:
        return [files]
    paths = [fp for fp, _ in files]
    sub = _cluster_by_top_dir(paths, depth=current_depth + 1)
    result: list[list[tuple[str, str]]] = []
    source_by_path = dict(files)
    for cluster_files in sub.values():
        sub_pairs = [(p, source_by_path[p]) for p in cluster_files]
        result.extend(_split_oversized_cluster(sub_pairs, budget, current_depth + 1, max_depth))
    return result


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

    def build(self, repo_id: str, *, repo_path: Path, force_map_reduce: bool = False) -> PromptContext:
        summary = self.build_graph_summary(repo_id)
        summary_text = _format_summary_text(summary)
        ranked = self.rank_files(repo_id)
        files: list[tuple[str, str]] = []
        for rf in ranked:
            src = _load_source(repo_path, rf.file_path)
            if src is not None:
                files.append((rf.file_path, src))
        source_tokens = sum(estimate_tokens(src) for _, src in files)
        total = estimate_tokens(summary_text) + source_tokens
        if not force_map_reduce and total <= self.single_shot_budget:
            return PromptContext(
                repo_id=repo_id, summary_text=summary_text, files=files,
                strategy="single_shot", clusters=None, estimated_tokens=total,
            )
        # map-reduce
        clusters_map = _cluster_by_top_dir([fp for fp, _ in files], depth=1)
        source_by_path = dict(files)
        all_clusters: list[list[str]] = []
        for cluster_files in clusters_map.values():
            sub_pairs = [(p, source_by_path[p]) for p in cluster_files]
            for split in _split_oversized_cluster(
                sub_pairs, self.single_shot_budget, current_depth=1, max_depth=self.max_cluster_depth
            ):
                all_clusters.append([p for p, _ in split])
        return PromptContext(
            repo_id=repo_id, summary_text=summary_text, files=files,
            strategy="map_reduce", clusters=all_clusters, estimated_tokens=total,
        )
