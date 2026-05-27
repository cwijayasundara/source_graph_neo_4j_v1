"""Graph exploration API routes — node listing, neighbor expansion."""

import logging
from fastapi import APIRouter, HTTPException, Query
from neo4j import Driver

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/graph", tags=["graph"])
_driver: Driver | None = None

GRAPH_STORY_PRESETS: dict[str, str] = {
    "overview": """
        CALL () {
            MATCH (source:Person)-[rel:OWNS]->(target:Account)
            RETURN source, rel, target, 1 AS rank, '' AS sort_key LIMIT 10
            UNION ALL
            MATCH (source:Account)-[rel:AT_INSTITUTION]->(target:Institution)
            RETURN source, rel, target, 2 AS rank, '' AS sort_key LIMIT 10
            UNION ALL
            MATCH (source:Account)-[rel:HAS_STATEMENT]->(target:Statement)
            RETURN source, rel, target, 3 AS rank, coalesce(target.period_start, '') AS sort_key
            ORDER BY sort_key DESC LIMIT 40
            UNION ALL
            MATCH (source:Statement)-[rel:CONTAINS]->(target:Transaction)
            RETURN source, rel, target, 4 AS rank, coalesce(target.date, '') AS sort_key
            ORDER BY sort_key DESC LIMIT 50
            UNION ALL
            MATCH (source:Transaction)-[rel:AT_MERCHANT]->(target:Merchant)
            RETURN source, rel, target, 5 AS rank, coalesce(source.date, '') AS sort_key
            ORDER BY sort_key DESC LIMIT 50
            UNION ALL
            MATCH (source:Transaction)-[rel:IN_CATEGORY]->(target:Category)
            RETURN source, rel, target, 6 AS rank, coalesce(source.date, '') AS sort_key
            ORDER BY sort_key DESC LIMIT 50
            UNION ALL
            MATCH (source:Transaction)-[rel:IN_PERIOD]->(target:TimePeriod)
            RETURN source, rel, target, 7 AS rank, coalesce(source.date, '') AS sort_key
            ORDER BY sort_key DESC LIMIT 30
            UNION ALL
            MATCH (source:Merchant)-[rel:BELONGS_TO]->(target:Category)
            RETURN source, rel, target, 8 AS rank, source.name AS sort_key LIMIT 60
        }
        RETURN source, rel, target
        ORDER BY rank, sort_key DESC
        LIMIT $limit
    """,
    "accounts": """
        MATCH (source)-[rel]->(target)
        WHERE type(rel) IN ['OWNS', 'AT_INSTITUTION', 'HAS_STATEMENT']
        RETURN source, rel, target
        LIMIT $limit
    """,
    "spending": """
        MATCH (source)-[rel]->(target)
        WHERE type(rel) IN ['CONTAINS', 'AT_MERCHANT', 'IN_CATEGORY', 'IN_PERIOD']
        RETURN source, rel, target
        LIMIT $limit
    """,
    "merchants": """
        MATCH (source)-[rel]->(target)
        WHERE type(rel) IN ['AT_MERCHANT', 'BELONGS_TO']
        RETURN source, rel, target
        LIMIT $limit
    """,
    "categories": """
        MATCH (source)-[rel]->(target)
        WHERE type(rel) IN ['IN_CATEGORY', 'BELONGS_TO', 'SUBCATEGORY_OF']
        RETURN source, rel, target
        LIMIT $limit
    """,
    "statements": """
        MATCH (source)-[rel]->(target)
        WHERE type(rel) IN ['HAS_STATEMENT', 'CONTAINS']
        RETURN source, rel, target
        LIMIT $limit
    """,
    "explore-all": """
        MATCH (source)-[rel]->(target)
        RETURN source, rel, target
        LIMIT $limit
    """,
}


def init_graph(driver: Driver):
    global _driver
    _driver = driver
    logger.info("Graph routes initialized with driver: %s", driver is not None)


def _serialize_graph_records(records) -> tuple[list[dict], list[dict]]:
    from neo4j.graph import Node, Relationship

    nodes: dict[str, dict] = {}
    relationships: dict[str, dict] = {}

    def collect_node(node):
        if not isinstance(node, Node):
            return
        eid = node.element_id
        if eid not in nodes:
            nodes[eid] = {"elementId": eid, "labels": list(node.labels), **dict(node)}

    def collect_rel(rel):
        if not isinstance(rel, Relationship):
            return
        eid = rel.element_id
        if eid not in relationships:
            relationships[eid] = {
                "elementId": eid,
                "type": rel.type,
                "startNodeElementId": rel.start_node.element_id,
                "endNodeElementId": rel.end_node.element_id,
            }

    for record in records:
        for value in record.values():
            collect_node(value)
            collect_rel(value)

    return list(nodes.values()), list(relationships.values())


def _graph_stats(nodes: list[dict], relationships: list[dict]) -> dict:
    def count_label(label: str) -> int:
        return sum(1 for node in nodes if label in node.get("labels", []))

    return {
        "nodes": len(nodes),
        "relationships": len(relationships),
        "people": count_label("Person"),
        "accounts": count_label("Account"),
        "statements": count_label("Statement"),
        "transactions": count_label("Transaction"),
        "merchants": count_label("Merchant"),
        "categories": count_label("Category"),
        "time_periods": count_label("TimePeriod"),
    }


@router.get("/nodes")
def get_nodes(
    label: str = Query(..., description="Node label e.g. Merchant, Category"),
    limit: int = Query(50, ge=1, le=500),
):
    """Get nodes for visualization, filtered by label."""
    with _driver.session() as session:
        result = session.run(
            f"MATCH (n:`{label}`) RETURN elementId(n) AS id, labels(n) AS labels, "
            f"properties(n) AS properties LIMIT $limit",
            {"limit": limit},
        )
        nodes = []
        for r in result:
            node = {
                "id": r["id"],
                "labels": r["labels"],
                "properties": dict(r["properties"]),
            }
            nodes.append(node)
        return {"nodes": nodes, "count": len(nodes)}


@router.get("/story")
def graph_story(
    preset: str = Query("overview", description="Story preset to visualize"),
    limit: int = Query(250, ge=1, le=5000),
):
    """Return a bounded graph slice for a guided graph story preset."""
    if _driver is None:
        logger.error("graph-story: _driver is None — init_graph was not called")
        return {"preset": preset, "nodes": [], "relationships": [], "results": [], "stats": _graph_stats([], [])}

    query = GRAPH_STORY_PRESETS.get(preset)
    if query is None:
        valid = ", ".join(sorted(GRAPH_STORY_PRESETS))
        raise HTTPException(status_code=400, detail=f"Unknown graph story preset '{preset}'. Valid presets: {valid}")

    try:
        with _driver.session() as session:
            records = list(session.run(query, {"limit": limit}))
    except Exception as e:
        logger.exception("graph-story failed for preset %s: %s", preset, e)
        raise HTTPException(status_code=500, detail=f"Failed to load graph story preset '{preset}'")

    nodes, relationships = _serialize_graph_records(records)
    return {
        "preset": preset,
        "nodes": nodes,
        "relationships": relationships,
        "results": nodes + relationships,
        "stats": _graph_stats(nodes, relationships),
    }


@router.get("/finance-overview")
def finance_overview(
    node_limit: int = Query(2500, ge=1, le=10000),
    relationship_limit: int = Query(10000, ge=0, le=50000),
):
    """Return graph data for visualization.

    This endpoint backs the Graph page, so it should show the data currently in
    Neo4j rather than only one curated finance path. It returns both a direct
    graph shape and the legacy ``results`` list consumed by existing clients.
    """
    from neo4j.graph import Node, Relationship

    logger.info("finance-overview called, driver=%s", _driver is not None)

    if _driver is None:
        logger.error("finance-overview: _driver is None — init_graph was not called")
        return {"results": []}

    nodes: dict[str, dict] = {}
    relationships: dict[str, dict] = {}

    def _collect_node(node, extra_props: dict | None = None):
        if not isinstance(node, Node):
            logger.warning("_collect_node: expected Node, got %s: %s", type(node).__name__, node)
            return
        eid = node.element_id
        if eid not in nodes:
            props = dict(node)
            if extra_props:
                props.update(extra_props)
            nodes[eid] = {"elementId": eid, "labels": list(node.labels), **props}

    def _collect_rel(rel):
        if not isinstance(rel, Relationship):
            return
        eid = rel.element_id
        if eid not in relationships:
            relationships[eid] = {
                "elementId": eid,
                "type": rel.type,
                "startNodeElementId": rel.start_node.element_id,
                "endNodeElementId": rel.end_node.element_id,
            }

    try:
        with _driver.session() as session:
            rel_rows = list(session.run(
                """MATCH (source)-[rel]->(target)
                RETURN source, rel, target
                LIMIT $relationship_limit""",
                {"relationship_limit": relationship_limit},
            ))
            logger.info("finance-overview relationship rows: %d", len(rel_rows))
            for record in rel_rows:
                _collect_node(record["source"])
                _collect_rel(record["rel"])
                _collect_node(record["target"])

            node_rows = list(session.run(
                """MATCH (node)
                RETURN node
                LIMIT $node_limit""",
                {"node_limit": node_limit},
            ))
            logger.info("finance-overview node rows: %d", len(node_rows))
            for record in node_rows:
                _collect_node(record["node"])

        logger.info("finance-overview result: %d nodes, %d relationships", len(nodes), len(relationships))
    except Exception as e:
        logger.exception("finance-overview failed: %s", e)
        return {"results": []}

    node_list = list(nodes.values())
    relationship_list = list(relationships.values())
    return {
        "nodes": node_list,
        "relationships": relationship_list,
        "results": node_list + relationship_list,
    }


@router.get("/neighbors/{node_id}")
def get_neighbors(
    node_id: str,
    depth: int = Query(1, ge=1, le=3),
):
    """Expand a node's relationships up to given depth.

    Uses APOC path expansion when available, falls back to
    variable-length pattern matching.
    """
    with _driver.session() as session:
        # Try APOC first for richer expansion
        try:
            result = session.run(
                """CALL apoc.path.subgraphAll($nodeId, {maxLevel: $depth})
                YIELD nodes, relationships
                UNWIND nodes AS n
                WITH collect(DISTINCT {
                    id: elementId(n),
                    labels: labels(n),
                    properties: properties(n)
                }) AS nodeList,
                relationships
                UNWIND relationships AS r
                RETURN nodeList AS nodes,
                collect(DISTINCT {
                    id: elementId(r),
                    type: type(r),
                    startNode: elementId(startNode(r)),
                    endNode: elementId(endNode(r)),
                    properties: properties(r)
                }) AS relationships""",
                {"nodeId": node_id, "depth": depth},
            ).single()
            if result:
                return {
                    "nodes": result["nodes"],
                    "relationships": result["relationships"],
                }
        except Exception:
            pass  # APOC not available, fall back

        # Fallback: simple variable-length match
        result = session.run(
            """MATCH (start) WHERE elementId(start) = $nodeId
            OPTIONAL MATCH path = (start)-[*1..""" + str(depth) + """]->(end)
            WITH start, collect(DISTINCT {
                id: elementId(end),
                labels: labels(end),
                properties: properties(end)
            }) AS neighbors
            RETURN {
                id: elementId(start),
                labels: labels(start),
                properties: properties(start)
            } AS source, neighbors""",
            {"nodeId": node_id},
        ).single()
        if not result:
            raise HTTPException(status_code=404, detail="Node not found")
        return {
            "source": result["source"],
            "neighbors": [n for n in result["neighbors"] if n["id"] is not None],
        }
