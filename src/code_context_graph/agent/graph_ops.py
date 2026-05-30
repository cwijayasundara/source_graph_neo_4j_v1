from __future__ import annotations

from typing import Any

from code_context_graph.agent.deps import GraphDeps

# Whitelist: edges and directions an agent may traverse. Anything else is rejected
# so a tool call can never smuggle arbitrary Cypher fragments into a query.
_EDGES = {"CALLS", "IMPORTS", "CONTAINS", "INHERITS", "DECORATES", "RAISES"}
_DIRECTIONS = {"out", "in", "both"}


def get_entity(deps: GraphDeps, name: str) -> dict[str, Any]:
    rows = deps.client.run(
        """
        MATCH (e:CodeEntity {repo: $repo})
        WHERE e.qualified_name = $name OR e.simple_name = $name
        RETURN e.qualified_name AS qualified_name, e.simple_name AS simple_name,
               e.kind AS kind, e.file_path AS file_path,
               e.signature AS signature, e.start_line AS start_line,
               e.end_line AS end_line, e.semantic_layer AS semantic_layer,
               e.semantic_summary AS semantic_summary
        LIMIT 1
        """,
        repo=deps.repo_id, name=name,
    )
    if not rows:
        return {"error": f"unknown entity: {name}"}
    return rows[0]


def find_entities(deps: GraphDeps, *, kind: str | None = None,
                  prefix: str | None = None, limit: int = 50) -> dict[str, Any]:
    rows = deps.client.run(
        """
        MATCH (e:CodeEntity {repo: $repo})
        WHERE ($kind IS NULL OR e.kind = $kind)
          AND ($prefix IS NULL OR toLower(e.qualified_name) STARTS WITH toLower($prefix))
        RETURN e.qualified_name AS qualified_name, e.kind AS kind,
               e.file_path AS file_path
        ORDER BY size(e.qualified_name), e.qualified_name
        LIMIT $limit
        """,
        repo=deps.repo_id, kind=kind, prefix=prefix, limit=limit,
    )
    return {"entities": rows}


def neighbors(deps: GraphDeps, name: str, *, edge: str,
              direction: str = "out", depth: int = 1, limit: int = 50) -> dict[str, Any]:
    if edge not in _EDGES:
        return {"error": f"unsupported edge {edge!r}; allowed: {sorted(_EDGES)}"}
    if direction not in _DIRECTIONS:
        return {"error": f"unsupported direction {direction!r}"}
    depth = max(1, min(int(depth), 5))
    if direction == "out":
        pattern = f"(a:CodeEntity {{repo: $repo}})-[:{edge}*1..{depth}]->(b:CodeEntity)"
    elif direction == "in":
        pattern = f"(a:CodeEntity {{repo: $repo}})<-[:{edge}*1..{depth}]-(b:CodeEntity)"
    else:
        pattern = f"(a:CodeEntity {{repo: $repo}})-[:{edge}*1..{depth}]-(b:CodeEntity)"
    rows = deps.client.run(
        f"""
        MATCH {pattern}
        WHERE a.qualified_name = $name
        RETURN DISTINCT b.qualified_name AS qualified_name, b.kind AS kind,
               b.file_path AS file_path
        ORDER BY b.qualified_name
        LIMIT $limit
        """,
        repo=deps.repo_id, name=name, limit=limit,
    )
    return {"neighbors": rows}


def get_source_slice(deps: GraphDeps, name: str) -> dict[str, Any]:
    rows = deps.client.run(
        """
        MATCH (e:CodeEntity {repo: $repo})
        WHERE e.qualified_name = $name
        RETURN e.file_path AS file, e.start_line AS start, e.end_line AS end
        LIMIT 1
        """,
        repo=deps.repo_id, name=name,
    )
    if not rows or not rows[0].get("file"):
        return {"error": f"unknown entity or no source location: {name}"}
    file = rows[0]["file"]
    start = int(rows[0].get("start") or 1)
    end = int(rows[0].get("end") or start)
    try:
        lines = (deps.repo_path / file).read_text(
            encoding="utf-8", errors="replace"
        ).splitlines()
    except (FileNotFoundError, IsADirectoryError, PermissionError) as exc:
        return {"error": f"could not read {file}: {type(exc).__name__}"}
    source = "\n".join(lines[max(0, start - 1):end])
    return {"entity": name, "file": file, "start_line": start,
            "end_line": end, "source": source}


def graph_summary(deps: GraphDeps) -> dict[str, Any]:
    counts = deps.client.run(
        "MATCH (e:CodeEntity {repo: $repo}) RETURN e.kind AS kind, count(e) AS count "
        "ORDER BY count DESC",
        repo=deps.repo_id,
    )
    rels = deps.client.run(
        "MATCH (s:CodeEntity {repo: $repo})-[r]->(t) "
        "RETURN type(r) AS rel_type, count(r) AS count ORDER BY count DESC",
        repo=deps.repo_id,
    )
    return {"entity_counts": counts,
            "relationship_counts": {r["rel_type"]: r["count"] for r in rels}}
