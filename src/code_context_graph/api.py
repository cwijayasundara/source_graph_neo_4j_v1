from __future__ import annotations

import json as _json
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from code_context_graph.brd import generate_brd_graph_sync
from code_context_graph.brd.storage import BRDStorage
from code_context_graph.github_client import (
    clone_repo,
    delete_cloned_repo,
    parse_github_url,
    repo_slug,
)
from code_context_graph.ingestion import CodeGraphIngester
from code_context_graph.llm_query import (
    CypherValidationError,
    ask_codebase,
)
from code_context_graph.neo4j_client import Neo4jClient
from code_context_graph.queries import CodeGraphQueries
from code_context_graph.repo_manager import RepoManager

_client: Neo4jClient | None = None
_brd_jobs: dict[str, dict] = {}  # repo_id -> latest job status


def get_client() -> Neo4jClient:
    global _client
    if _client is None:
        _client = Neo4jClient()
    return _client


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _client
    _client = Neo4jClient()
    mgr = RepoManager(_client)
    mgr.ensure_constraints()
    _client.apply_schema()
    yield
    if _client:
        _client.close()
        _client = None


app = FastAPI(title="Code Context Graph API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------- request/response models ---------------


class CloneRequest(BaseModel):
    url: str
    branch: str | None = None
    shallow: bool = True


class LocalIngestRequest(BaseModel):
    path: str


class QueryRequest(BaseModel):
    kind: str
    name: str
    repo: str | None = None
    depth: int = 3
    min_complexity: int = 5


class AskRequest(BaseModel):
    repo: str
    question: str


# --------------- repos ---------------


@app.post("/api/repos/clone")
def clone_and_ingest(req: CloneRequest) -> dict:
    try:
        slug = repo_slug(req.url)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    try:
        local_path = clone_repo(req.url, branch=req.branch, shallow=req.shallow)
    except Exception as exc:
        raise HTTPException(502, f"Clone failed: {exc}")

    return _ingest_repo(slug, req.url, local_path)


@app.post("/api/repos/local")
def ingest_local(req: LocalIngestRequest) -> dict:
    path = Path(req.path).resolve()
    if not path.is_dir():
        raise HTTPException(400, f"Not a directory: {path}")
    slug = path.name
    return _ingest_repo(slug, f"local://{path}", path)


def _ingest_repo(slug: str, url: str, local_path: Path) -> dict:
    client = get_client()
    mgr = RepoManager(client)

    existing = mgr.get(slug)
    if existing:
        mgr.delete(slug)

    try:
        ingester = CodeGraphIngester(client, local_path)
        stats = ingester.ingest(clear=False, with_git=True)
    except Exception as exc:
        raise HTTPException(500, f"Ingestion failed: {traceback.format_exc()}")

    mgr.tag_entities(slug)
    mgr.link_files_to_modules(slug)
    repo_data = mgr.register(slug, url, str(local_path), stats)
    return {"status": "ok", "repo": repo_data, "stats": stats}


@app.get("/api/repos")
def list_repos() -> list[dict]:
    client = get_client()
    return RepoManager(client).list_repos()


# --------------- BRD ---------------
# Registered before /api/repos/{slug:path} so the specific BRD routes
# take precedence over the catch-all repo slug routes.


def _run_brd_job(repo_id: str, max_retries: int | None) -> None:
    try:
        result = generate_brd_graph_sync(
            repo_id,
            client=get_client(),
            max_retries=max_retries,
        )
        _brd_jobs[repo_id] = {
            "status": "done", "brd_id": result.brd_id, "rating": result.rating.value,
            "weighted_score": result.weighted_score, "attempts": result.attempts,
            "version": result.version, "html_path": result.html_path,
            "created_at": result.created_at.isoformat(),
            "strategy": result.strategy.value,
        }
    except Exception as exc:
        _brd_jobs[repo_id] = {"status": "error", "error": str(exc)}


@app.post("/api/repos/{repo_id}/brd")
def start_brd(
    repo_id: str,
    background: BackgroundTasks,
    max_retries: int | None = Query(None),
) -> dict:
    existing = _brd_jobs.get(repo_id)
    if existing and existing.get("status") == "running":
        raise HTTPException(409, f"BRD generation already in progress for {repo_id}")
    _brd_jobs[repo_id] = {"status": "running"}
    background.add_task(_run_brd_job, repo_id, max_retries)
    return {"status": "running", "repo_id": repo_id}


@app.get("/api/repos/{repo_id}/brd/{brd_id}/html", response_class=HTMLResponse)
def get_brd_html(repo_id: str, brd_id: str) -> HTMLResponse:
    client = get_client()
    rows = client.run(
        "MATCH (r:Repository {slug: $repo_id})-[:HAS_BRD]->(b:BRD {id: $brd_id}) "
        "RETURN b.html AS html",
        repo_id=repo_id,
        brd_id=brd_id,
    )
    if not rows:
        raise HTTPException(404, f"BRD not found: {brd_id}")
    return HTMLResponse(rows[0]["html"])


@app.get("/api/repos/{repo_id}/brd")
def get_brd(repo_id: str, all: bool = Query(False)) -> dict | list:
    client = get_client()
    storage = BRDStorage(client)
    if all:
        return storage.list_versions(repo_id)
    rows = client.run(
        "MATCH (r:Repository {slug: $repo_id})-[:HAS_BRD]->(b:BRD) "
        "RETURN b ORDER BY b.version DESC LIMIT 1",
        repo_id=repo_id,
    )
    if not rows:
        job = _brd_jobs.get(repo_id)
        if job:
            return job
        raise HTTPException(404, f"No BRD for {repo_id}")
    b = rows[0]["b"]
    attempt_history = b.get("attempt_history")
    if isinstance(attempt_history, str):
        attempt_history = _json.loads(attempt_history)
    return {
        "id": b.get("id"), "version": b.get("version"),
        "rating": b.get("rating"), "weighted_score": b.get("weighted_score"),
        "attempts": b.get("attempts"), "model": b.get("model"),
        "strategy": b.get("strategy"), "created_at": b.get("created_at"),
        "attempt_history": attempt_history,
    }


@app.get("/api/repos/{slug:path}")
def get_repo(slug: str) -> dict:
    client = get_client()
    repo = RepoManager(client).get(slug)
    if not repo:
        raise HTTPException(404, f"Repo not found: {slug}")
    return repo


@app.delete("/api/repos/{slug:path}")
def remove_repo(slug: str) -> dict:
    client = get_client()
    RepoManager(client).delete(slug)
    delete_cloned_repo(slug)
    return {"status": "deleted", "slug": slug}


# --------------- graph visualization ---------------


def _graph_node_from_props(props: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": props.get("qualified_name"),
        "name": props.get("simple_name"),
        "kind": props.get("kind"),
        "file": props.get("file_path"),
        "complexity": props.get("complexity"),
        "signature": props.get("signature"),
        "docstring": props.get("docstring"),
        "is_async": props.get("is_async"),
        "layer": props.get("semantic_layer"),
        "summary": props.get("semantic_summary"),
    }


@app.get("/api/graph")
def get_graph(
    repo: str | None = Query(None),
    limit: int = Query(200),
) -> dict:
    client = get_client()
    repo_filter = "WHERE e.repo = $repo" if repo else ""
    params: dict[str, Any] = {"limit": limit}
    if repo:
        params["repo"] = repo

    nodes = client.run(
        f"""
        MATCH (e:CodeEntity)
        {repo_filter}
        RETURN properties(e) AS entity
        LIMIT $limit
        """,
        **params,
    )
    normalized_nodes = [_graph_node_from_props(row["entity"]) for row in nodes]

    links = client.run(
        f"""
        MATCH (src:CodeEntity)-[r]->(tgt:CodeEntity)
        {"WHERE src.repo = $repo AND tgt.repo = $repo" if repo else ""}
        RETURN src.qualified_name AS source,
               tgt.qualified_name AS target,
               type(r) AS type
        LIMIT $limit
        """,
        **params,
    )

    node_ids = {n["id"] for n in normalized_nodes}
    filtered_links = [l for l in links if l["source"] in node_ids and l["target"] in node_ids]

    return {"nodes": normalized_nodes, "links": filtered_links}


# --------------- entity detail ---------------


@app.get("/api/entity/{qname:path}")
def get_entity(qname: str) -> dict:
    client = get_client()
    results = client.run(
        """
        MATCH (e:CodeEntity {qualified_name: $qname})
        RETURN e {.*} AS entity
        """,
        qname=qname,
    )
    if not results:
        raise HTTPException(404, f"Entity not found: {qname}")

    incoming = client.run(
        """
        MATCH (src:CodeEntity)-[r]->(e:CodeEntity {qualified_name: $qname})
        RETURN src.qualified_name AS source,
               src.kind AS source_kind,
               type(r) AS relationship
        LIMIT 50
        """,
        qname=qname,
    )
    outgoing = client.run(
        """
        MATCH (e:CodeEntity {qualified_name: $qname})-[r]->(tgt:CodeEntity)
        RETURN tgt.qualified_name AS target,
               tgt.kind AS target_kind,
               type(r) AS relationship
        LIMIT 50
        """,
        qname=qname,
    )

    return {
        "entity": results[0]["entity"],
        "incoming": incoming,
        "outgoing": outgoing,
    }


# --------------- queries ---------------


@app.post("/api/query")
def run_query(req: QueryRequest) -> dict:
    client = get_client()
    q = CodeGraphQueries(client)

    dispatch: dict[str, Any] = {
        "calls": lambda: q.what_does_it_call(req.name, req.repo),
        "callers": lambda: q.what_calls(req.name, req.repo),
        "impact": lambda: q.impact_analysis(req.name, req.depth, req.repo),
        "hierarchy": lambda: q.class_hierarchy(req.name, req.repo),
        "imports": lambda: q.module_dependencies(req.name, req.repo),
        "importers": lambda: q.who_imports_this(req.name, req.repo),
        "cochange": lambda: q.co_changed_files(req.name, req.repo),
        "owners": lambda: q.file_owners(req.name, req.repo),
        "path": lambda: q.full_request_path(req.name, req.repo),
        "complex": lambda: q.complex_functions(req.min_complexity, req.repo),
    }

    fn = dispatch.get(req.kind)
    if fn is None:
        raise HTTPException(400, f"Unknown query kind: {req.kind}. Choose from: {', '.join(dispatch)}")

    return {"kind": req.kind, "name": req.name, "results": fn()}


@app.post("/api/ask")
def ask_question(req: AskRequest) -> dict:
    client = get_client()
    try:
        result = ask_codebase(client=client, repo=req.repo, question=req.question)
    except CypherValidationError as exc:
        raise HTTPException(400, str(exc))
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"Ask failed: {exc}")
    return {
        "answer": result.answer,
        "cypher": result.cypher,
        "rows": result.rows,
        "explanation": result.explanation,
    }


@app.get("/api/search")
def search_entities(
    q: str = Query(..., min_length=1),
    repo: str | None = Query(None),
) -> list[dict]:
    client = get_client()
    queries = CodeGraphQueries(client)
    results = queries.search(q)
    if repo:
        results = [r for r in results if r.get("file", "").startswith(repo) or True]
    return results


@app.get("/api/suggest")
def suggest(
    q: str = Query(..., min_length=1),
    repo: str | None = Query(None),
    limit: int = Query(10, ge=1, le=50),
) -> list[dict]:
    client = get_client()
    return CodeGraphQueries(client).suggest_entities(q, repo, limit)


@app.get("/api/stats")
def get_stats(repo: str | None = Query(None)) -> dict:
    client = get_client()
    q = CodeGraphQueries(client)
    return q.graph_stats()
