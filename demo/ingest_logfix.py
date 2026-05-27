#!/usr/bin/env python3
"""Demo: Ingest the logfix_engine codebase into a Neo4j code context graph.

Usage:
    # First, ensure Neo4j is running (e.g., via Docker):
    #   docker run -d --name neo4j -p 7474:7474 -p 7687:7687 \
    #     -e NEO4J_AUTH=neo4j/password neo4j:5

    # Set your .env:
    #   NEO4J_URI=bolt://localhost:7687
    #   NEO4J_USER=neo4j
    #   NEO4J_PASSWORD=password

    python demo/ingest_logfix.py
"""
from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from code_context_graph.ingestion import CodeGraphIngester
from code_context_graph.neo4j_client import Neo4jClient
from code_context_graph.queries import CodeGraphQueries

LOGFIX_ROOT = Path(__file__).resolve().parent.parent.parent / "log_analyzer_agent_v2"

console = Console()


def main() -> None:
    console.print(Panel(f"[bold]Code Context Graph Demo[/bold]\nIngesting: {LOGFIX_ROOT}"))

    with Neo4jClient() as client:
        ingester = CodeGraphIngester(client, LOGFIX_ROOT)
        stats = ingester.ingest(clear=True, with_git=True)

        console.print("\n[bold cyan]--- Graph Statistics ---[/bold cyan]")
        q = CodeGraphQueries(client)
        graph_stats = q.graph_stats()

        for row in graph_stats["entity_counts"]:
            console.print(f"  {row['kind']:20s} {row['count']}")
        console.print()
        for row in graph_stats["relationship_counts"]:
            console.print(f"  {row['rel_type']:20s} {row['count']}")

        console.print("\n[bold cyan]--- Sample Queries ---[/bold cyan]\n")

        console.print("[bold]1. What does `run_detection_once` call?[/bold]")
        results = q.what_does_it_call("run_detection_once")
        _print_table(results)

        console.print("\n[bold]2. Impact analysis: what depends on `LogCluster`?[/bold]")
        results = q.impact_analysis("LogCluster")
        _print_table(results)

        console.print("\n[bold]3. Who imports the `models` module?[/bold]")
        results = q.who_imports_this("models")
        _print_table(results)

        console.print("\n[bold]4. Class hierarchy for `ScreenedIssue`[/bold]")
        results = q.class_hierarchy("ScreenedIssue")
        _print_table(results)

        console.print("\n[bold]5. Co-changed files with `graph`[/bold]")
        results = q.co_changed_files("graph")
        _print_table(results)

        console.print("\n[bold]6. Most complex functions[/bold]")
        results = q.complex_functions(min_complexity=3)
        _print_table(results)

        console.print("\n[bold]7. Full call path from CLI `analyze` command[/bold]")
        results = q.full_request_path("analyze")
        _print_table(results)


def _print_table(results: list[dict]) -> None:
    if not results:
        console.print("  [yellow]No results[/yellow]")
        return
    table = Table()
    for col in results[0]:
        table.add_column(col)
    for row in results:
        table.add_row(*[str(v) for v in row.values()])
    console.print(table)


if __name__ == "__main__":
    main()
