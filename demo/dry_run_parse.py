#!/usr/bin/env python3
"""Dry-run parse of logfix_engine — no Neo4j needed. Shows what the graph would contain."""
from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.table import Table

from code_context_graph.parser import parse_directory

LOGFIX_ROOT = Path(__file__).resolve().parent.parent.parent / "log_analyzer_agent_v2"
console = Console()


def main() -> None:
    console.print(f"[bold]Dry-run parsing: {LOGFIX_ROOT}[/bold]\n")
    results = parse_directory(LOGFIX_ROOT)

    all_entities = [e for r in results for e in r.entities]
    all_rels = [rel for r in results for rel in r.relationships]

    console.print(f"Files parsed: {len(results)}")
    console.print(f"Total entities: {len(all_entities)}")
    console.print(f"Total relationships: {len(all_rels)}\n")

    from collections import Counter

    kind_counts = Counter(e.kind.value for e in all_entities)
    table = Table(title="Entity counts by kind")
    table.add_column("Kind")
    table.add_column("Count", justify="right")
    for kind, count in kind_counts.most_common():
        table.add_row(kind, str(count))
    console.print(table)

    rel_counts = Counter(r.kind.value for r in all_rels)
    table = Table(title="Relationship counts by kind")
    table.add_column("Kind")
    table.add_column("Count", justify="right")
    for kind, count in rel_counts.most_common():
        table.add_row(kind, str(count))
    console.print(table)

    console.print("\n[bold]All entities:[/bold]")
    table = Table()
    table.add_column("Kind")
    table.add_column("Qualified Name")
    table.add_column("File")
    table.add_column("Lines")
    table.add_column("Complexity")
    for e in sorted(all_entities, key=lambda e: (e.file_path, e.start_line)):
        table.add_row(
            e.kind.value,
            e.qualified_name,
            e.file_path,
            f"{e.start_line}-{e.end_line}",
            str(e.complexity) if e.complexity else "",
        )
    console.print(table)

    console.print("\n[bold]Sample relationships (first 40):[/bold]")
    table = Table()
    table.add_column("Source")
    table.add_column("Rel")
    table.add_column("Target")
    for rel in all_rels[:40]:
        table.add_row(rel.source_qname, rel.kind.value, rel.target_qname)
    console.print(table)


if __name__ == "__main__":
    main()
