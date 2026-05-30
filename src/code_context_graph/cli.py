from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Code Context Graph — build a Neo4j knowledge graph from source code.")
console = Console()


@app.command()
def ingest(
    repo: Path = typer.Argument(..., help="Path to the repository root to analyze."),
    clear: bool = typer.Option(False, "--clear", help="Clear existing graph before ingesting."),
    no_git: bool = typer.Option(False, "--no-git", help="Skip git history analysis."),
) -> None:
    """Parse source code and load into Neo4j."""
    from code_context_graph.ingestion import CodeGraphIngester
    from code_context_graph.neo4j_client import Neo4jClient

    with Neo4jClient() as client:
        ingester = CodeGraphIngester(client, repo.resolve())
        ingester.ingest(clear=clear, with_git=not no_git)


@app.command()
def clone(
    url: str = typer.Argument(..., help="GitHub repository URL to clone and ingest."),
    branch: str = typer.Option(None, "--branch", "-b", help="Branch to clone."),
    clear: bool = typer.Option(False, "--clear", help="Clear existing graph before ingesting."),
) -> None:
    """Clone a GitHub repo and ingest into Neo4j."""
    from code_context_graph.github_client import clone_repo, repo_slug
    from code_context_graph.ingestion import CodeGraphIngester
    from code_context_graph.neo4j_client import Neo4jClient
    from code_context_graph.repo_manager import RepoManager

    slug = repo_slug(url)
    console.print(f"[cyan]Cloning {slug}...[/cyan]")
    local_path = clone_repo(url, branch=branch, shallow=False)
    console.print(f"  Cloned to {local_path}")

    with Neo4jClient() as client:
        mgr = RepoManager(client)
        mgr.ensure_constraints()
        if clear:
            existing = mgr.get(slug)
            if existing:
                mgr.delete(slug)

        ingester = CodeGraphIngester(client, local_path)
        stats = ingester.ingest(clear=False, with_git=True)
        mgr.tag_entities(slug)
        mgr.link_files_to_modules(slug)
        mgr.register(slug, url, str(local_path), stats)
        console.print(f"[green]Registered repo: {slug}[/green]")


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", help="Bind host."),
    port: int = typer.Option(8000, "--port", help="Bind port."),
) -> None:
    """Start the FastAPI server."""
    import uvicorn

    console.print(f"[cyan]Starting API server on {host}:{port}...[/cyan]")
    uvicorn.run("code_context_graph.api:app", host=host, port=port)


@app.command()
def enrich(
    limit: int = typer.Option(50, "--limit", help="Max entities to enrich per run."),
) -> None:
    """Run LLM semantic enrichment on un-tagged entities."""
    from code_context_graph.enrichment import SemanticEnricher
    from code_context_graph.neo4j_client import Neo4jClient

    with Neo4jClient() as client:
        enricher = SemanticEnricher(client)
        count = enricher.enrich_all(limit=limit)
        console.print(f"[green]Enriched {count} entities[/green]")


@app.command()
def query(
    name: str = typer.Argument(..., help="Entity name to query."),
    kind: str = typer.Option("calls", help="Query kind: calls, callers, impact, hierarchy, imports, importers, cochange, owners, path"),
) -> None:
    """Run pre-built queries against the code graph."""
    from code_context_graph.neo4j_client import Neo4jClient
    from code_context_graph.queries import CodeGraphQueries

    with Neo4jClient() as client:
        q = CodeGraphQueries(client)
        dispatch = {
            "calls": q.what_does_it_call,
            "callers": q.what_calls,
            "impact": q.impact_analysis,
            "hierarchy": q.class_hierarchy,
            "imports": q.module_dependencies,
            "importers": q.who_imports_this,
            "cochange": q.co_changed_files,
            "owners": q.file_owners,
            "path": q.full_request_path,
        }
        fn = dispatch.get(kind)
        if fn is None:
            console.print(f"[red]Unknown query kind: {kind}. Choose from: {', '.join(dispatch)}[/red]")
            raise typer.Exit(1)
        results = fn(name)
        if not results:
            console.print("[yellow]No results found.[/yellow]")
            return
        table = Table(title=f"{kind}: {name}")
        for col in results[0]:
            table.add_column(col)
        for row in results:
            table.add_row(*[str(v) for v in row.values()])
        console.print(table)


@app.command()
def stats() -> None:
    """Show graph statistics."""
    from code_context_graph.neo4j_client import Neo4jClient
    from code_context_graph.queries import CodeGraphQueries

    with Neo4jClient() as client:
        q = CodeGraphQueries(client)
        s = q.graph_stats()
        console.print("[bold]Entity counts:[/bold]")
        for row in s["entity_counts"]:
            console.print(f"  {row['kind']}: {row['count']}")
        console.print("[bold]Relationship counts:[/bold]")
        for row in s["relationship_counts"]:
            console.print(f"  {row['rel_type']}: {row['count']}")


@app.command()
def search(
    query_text: str = typer.Argument(..., help="Search query for entity names and docstrings."),
) -> None:
    """Full-text search across the code graph."""
    from code_context_graph.neo4j_client import Neo4jClient
    from code_context_graph.queries import CodeGraphQueries

    with Neo4jClient() as client:
        q = CodeGraphQueries(client)
        results = q.search(query_text)
        if not results:
            console.print("[yellow]No results found.[/yellow]")
            return
        table = Table(title=f"Search: {query_text}")
        for col in results[0]:
            table.add_column(col)
        for row in results:
            table.add_row(*[str(v) for v in row.values()])
        console.print(table)


@app.command()
def complex(
    min_complexity: int = typer.Option(5, "--min", help="Minimum cyclomatic complexity."),
) -> None:
    """Find the most complex functions in the graph."""
    from code_context_graph.neo4j_client import Neo4jClient
    from code_context_graph.queries import CodeGraphQueries

    with Neo4jClient() as client:
        q = CodeGraphQueries(client)
        results = q.complex_functions(min_complexity)
        if not results:
            console.print("[yellow]No functions above complexity threshold.[/yellow]")
            return
        table = Table(title=f"Functions with complexity >= {min_complexity}")
        for col in results[0]:
            table.add_column(col)
        for row in results:
            table.add_row(*[str(v) for v in row.values()])
        console.print(table)


@app.command()
def brd(
    repo: str = typer.Argument(..., help="Repo slug (or local path) to generate a BRD for."),
    max_retries: int = typer.Option(None, "--max-retries", help="Override BRD_MAX_RETRIES."),
    force_map_reduce: bool = typer.Option(False, "--force-map-reduce",
                                          help="Use map-reduce even if repo fits in context."),
    output_dir: str = typer.Option(None, "--output-dir", help="Override BRD_OUTPUT_DIR."),
    open_browser: bool = typer.Option(False, "--open", help="Open the BRD in the default browser."),
) -> None:
    """Generate a Business Requirements Document for an ingested repo."""
    import os
    import webbrowser
    from code_context_graph.brd import generate_brd
    from code_context_graph.brd.schema import Rating

    if output_dir:
        os.environ["BRD_OUTPUT_DIR"] = output_dir

    console.print(f"[cyan]Generating BRD for {repo}...[/cyan]")
    result = generate_brd(
        repo_id=repo,
        max_retries=max_retries,
        force_map_reduce=force_map_reduce,
    )
    badge = {"high": "green", "medium": "yellow", "low": "red"}[result.rating.value]
    console.print(
        f"[{badge}]Rating: {result.rating.value}[/{badge}] "
        f"(weighted score {result.weighted_score:.2f}, "
        f"{result.attempts} attempt(s), strategy {result.strategy.value})"
    )
    console.print(f"HTML written to: {result.html_path}")
    if open_browser:
        webbrowser.open(f"file://{result.html_path}")
    if result.rating == Rating.high:
        raise typer.Exit(0)
    if result.rating == Rating.medium:
        raise typer.Exit(1)
    raise typer.Exit(2)
