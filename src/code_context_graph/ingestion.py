from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.progress import Progress

from code_context_graph.git_analyzer import GitAnalyzer
from code_context_graph.models import CodeEntity, CodeRelationship, ParseResult
from code_context_graph.neo4j_client import Neo4jClient
from code_context_graph.parser import parse_directory

console = Console()


class CodeGraphIngester:
    """Orchestrates parsing source code + git history and loading into Neo4j."""

    def __init__(self, client: Neo4jClient, repo_root: Path) -> None:
        self.client = client
        self.repo_root = repo_root

    def ingest(self, clear: bool = False, with_git: bool = True) -> dict[str, int]:
        if clear:
            console.print("[yellow]Clearing existing graph...[/yellow]")
            self.client.clear()

        self.client.apply_schema()

        console.print(f"[cyan]Parsing source files in {self.repo_root}...[/cyan]")
        parse_results = parse_directory(self.repo_root)
        console.print(f"  Found {len(parse_results)} files")

        entity_count = 0
        rel_count = 0

        with Progress() as progress:
            task = progress.add_task("Loading entities...", total=len(parse_results))
            for result in parse_results:
                for entity in result.entities:
                    self._load_entity(entity)
                    entity_count += 1
                progress.advance(task)

        with Progress() as progress:
            task = progress.add_task("Loading relationships...", total=len(parse_results))
            for result in parse_results:
                for rel in result.relationships:
                    self._load_relationship(rel)
                    rel_count += 1
                progress.advance(task)

        git_stats = {"authors": 0, "co_changes": 0}
        if with_git:
            git_stats = self._ingest_git()

        stats = {
            "files_parsed": len(parse_results),
            "entities": entity_count,
            "relationships": rel_count,
            **git_stats,
        }
        console.print(f"[green]Ingestion complete: {stats}[/green]")
        return stats

    def _load_entity(self, entity: CodeEntity) -> None:
        props = {
            "kind": entity.kind.value,
            "simple_name": entity.simple_name,
            "file_path": entity.file_path,
            "start_line": entity.start_line,
            "end_line": entity.end_line,
            "is_async": entity.is_async,
            "is_private": entity.is_private,
            "is_external": entity.is_external,
        }
        if entity.docstring:
            props["docstring"] = entity.docstring
        if entity.signature:
            props["signature"] = entity.signature
        if entity.decorators:
            props["decorators"] = entity.decorators
        if entity.base_classes:
            props["base_classes"] = entity.base_classes
        if entity.complexity is not None:
            props["complexity"] = entity.complexity

        self.client.merge_entity(
            qualified_name=entity.qualified_name,
            label=entity.kind.value,
            props=props,
        )

    def _load_relationship(self, rel: CodeRelationship) -> None:
        props: dict[str, str | int] = {}
        if rel.file_path:
            props["file_path"] = rel.file_path
        if rel.line is not None:
            props["line"] = rel.line
        props.update(rel.metadata)

        self.client.merge_relationship(
            source_qname=rel.source_qname,
            target_qname=rel.target_qname,
            rel_type=rel.kind.value,
            props=props,
            allow_unresolved=True,
        )

    def _ingest_git(self) -> dict[str, int]:
        try:
            analyzer = GitAnalyzer(self.repo_root)
        except Exception:
            console.print("[yellow]Not a git repo — skipping git analysis[/yellow]")
            return {"authors": 0, "co_changes": 0}

        console.print("[cyan]Analyzing git history...[/cyan]")

        authors = analyzer.authors()
        for author in authors:
            self.client.merge_author(
                name=author.name,
                email=author.email,
                commit_count=author.commit_count,
            )

        file_authors = analyzer.file_authors()
        for file_path, emails in file_authors.items():
            for rank, email in enumerate(emails):
                self.client.merge_authored_by(file_path, email, rank)

        co_changes = analyzer.co_changes(min_times=2)
        path_to_module = self._build_path_to_module_map()
        loaded_co = 0
        for cc in co_changes:
            qname_a = path_to_module.get(cc.file_a)
            qname_b = path_to_module.get(cc.file_b)
            if qname_a and qname_b:
                self.client.merge_co_change(qname_a, qname_b, cc.times_changed_together, cc.confidence)
                loaded_co += 1

        console.print(f"  Authors: {len(authors)}, Co-changes: {loaded_co}")
        return {"authors": len(authors), "co_changes": loaded_co}

    def _build_path_to_module_map(self) -> dict[str, str]:
        results = self.client.run(
            "MATCH (e:CodeEntity) WHERE e.kind = 'Module' RETURN e.file_path AS path, e.qualified_name AS qname"
        )
        return {r["path"]: r["qname"] for r in results}
