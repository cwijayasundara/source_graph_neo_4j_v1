"""Finance agent — single LangGraph ReAct agent with graph-aware tools.

Uses a single agent with all tools for fast responses (2-3 LLM calls).
Tools emit graph context (nodes/relationships) through the CypherResultCollector
so the frontend can highlight the relevant subgraph.
"""

from __future__ import annotations

import json
import os

from neo4j import GraphDatabase, Driver
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool

from app.tools.schema_tool import make_get_graph_schema
from app.tools.summary_tool import make_get_spending_summary
from app.tools.pattern_tool import make_detect_patterns

_FORMAT_RULES = (
    "\n\nFORMATTING RULES (always follow):\n"
    "- Present any list of 3+ items as a **markdown table** (use | col | col | syntax).\n"
    "- Format all monetary amounts as £X,XXX.XX.\n"
    "- Use **bold** for totals and key figures.\n"
    "- Keep prose short; let the table speak.\n"
    "- For transaction lists, use columns: Date | Merchant | Category | Amount.\n"
    "- For summaries, use columns: Category/Merchant | Total | Count."
)

SYSTEM_PROMPT = (
    "You are a personal finance assistant with access to the user's "
    "bank transaction history stored in a Neo4j context graph. You help "
    "analyze spending, find patterns, and give actionable savings advice.\n\n"
    "TOOLS:\n"
    "- cypher_query: Run Cypher against Neo4j. Call graph_schema first to learn the schema.\n"
    "- graph_schema: Get node labels, relationships, category hierarchy.\n"
    "- merchant_search: Fuzzy search for a merchant name.\n"
    "- spending_summary: Quick aggregation by period/category/account.\n"
    "- pattern_detection: Find recurring payments and trends.\n\n"
    "WORKFLOW:\n"
    "1. Call graph_schema ONCE at the start of a conversation to learn the data model.\n"
    "2. Use spending_summary or pattern_detection for common queries (faster than raw Cypher).\n"
    "3. Use cypher_query for specific or complex lookups.\n"
    "4. Always cite specific merchants and amounts from the data.\n\n"
    "KEY FACTS:\n"
    "- Negative transaction amounts = expenses, positive = income.\n"
    "- TimePeriod.label format: 'YYYY-MM' (e.g., '2025-01').\n"
    "- Use Merchant.normalized_name for merchant matching.\n"
    "- Category.name for category filtering (e.g., 'Groceries', 'Housing').\n\n"
    "CYPHER PATTERNS (use these exact patterns — do NOT inline path expressions in RETURN):\n"
    "IMPORTANT: Always include t.id AS id in RETURN so the graph can be visualized.\n"
    "```\n"
    "// Transactions by merchant\n"
    "MATCH (t:Transaction)-[:AT_MERCHANT]->(m:Merchant)\n"
    "WHERE toLower(m.normalized_name) CONTAINS toLower('costa')\n"
    "OPTIONAL MATCH (t)-[:IN_CATEGORY]->(c:Category)\n"
    "RETURN t.id AS id, t.date AS Date, m.normalized_name AS Merchant, c.name AS Category, t.amount AS Amount\n"
    "ORDER BY t.date\n\n"
    "// Transactions by period\n"
    "MATCH (t:Transaction)-[:IN_PERIOD]->(tp:TimePeriod {label: '2026-01'})\n"
    "MATCH (t)-[:AT_MERCHANT]->(m:Merchant)\n"
    "OPTIONAL MATCH (t)-[:IN_CATEGORY]->(c:Category)\n"
    "RETURN t.id AS id, t.date AS Date, m.normalized_name AS Merchant, c.name AS Category, t.amount AS Amount\n"
    "ORDER BY t.date\n\n"
    "// Spending by category for a period\n"
    "MATCH (t:Transaction)-[:IN_CATEGORY]->(c:Category),\n"
    "      (t)-[:IN_PERIOD]->(tp:TimePeriod {label: '2025-01'})\n"
    "WHERE t.amount < 0\n"
    "RETURN c.name AS Category, round(sum(abs(t.amount)), 2) AS Total, count(t) AS Count\n"
    "ORDER BY Total DESC\n\n"
    "// Biggest expense in a month\n"
    "MATCH (t:Transaction)-[:IN_PERIOD]->(tp:TimePeriod {label: '2026-01'}),\n"
    "      (t)-[:AT_MERCHANT]->(m:Merchant)\n"
    "WHERE t.amount < 0\n"
    "RETURN t.id AS id, t.date AS Date, m.normalized_name AS Merchant, t.amount AS Amount\n"
    "ORDER BY t.amount ASC LIMIT 1\n"
    "```\n"
    "IMPORTANT: Always use MATCH or OPTIONAL MATCH to traverse relationships. "
    "Never use path expressions like (t)-[:REL]->(:Node).property in RETURN clauses."
    + _FORMAT_RULES
)

_schema_cache: str | None = None


def _make_graph_tools(driver: Driver):
    """Create LangChain tools that emit graph context via the collector."""
    from app.tools.cypher_tool import _is_read_only
    from app.context_graph_client import get_collector

    raw_get_schema = make_get_graph_schema(driver)
    raw_spending_summary = make_get_spending_summary(driver)
    raw_detect_patterns = make_detect_patterns(driver)

    @tool
    def graph_schema() -> str:
        """Get the graph schema: node labels, relationships, category hierarchy. Call this first."""
        global _schema_cache
        if _schema_cache is not None:
            return _schema_cache
        _schema_cache = raw_get_schema()
        return _schema_cache

    @tool
    def cypher_query(query: str, params: str = "{}") -> str:
        """Execute a read-only Cypher query against the Neo4j context graph. Returns JSON results."""
        if not _is_read_only(query):
            return json.dumps({"error": "Write operations not allowed."})
        parsed_params = json.loads(params) if params and params != "{}" else {}

        collector = get_collector()
        collector.emit_tool_start("cypher_query", {"query": query})

        with driver.session() as session:
            result = session.run(query, parsed_params)
            records = [dict(record) for record in result]

        output = json.dumps(records, default=str)

        graph_nodes = _extract_graph_context(driver, records)
        collector.collect(graph_nodes)
        collector.collect_tool_call("cypher_query", {"query": query}, output[:300])

        return output

    @tool
    def merchant_search(name: str) -> str:
        """Search for a merchant by name. Returns matches with categories."""
        collector = get_collector()
        collector.emit_tool_start("merchant_search", {"name": name})

        with driver.session() as session:
            result = session.run(
                """MATCH (m:Merchant)
                WHERE toLower(m.normalized_name) CONTAINS toLower($name)
                OPTIONAL MATCH (m)-[:BELONGS_TO]->(c:Category)
                OPTIONAL MATCH (t:Transaction)-[:AT_MERCHANT]->(m)
                WITH m, c, count(t) AS txn_count, sum(abs(t.amount)) AS total
                RETURN m.normalized_name AS merchant, c.name AS category,
                       txn_count, round(total, 2) AS total_spent
                LIMIT 10""",
                {"name": name},
            )
            matches = [dict(r) for r in result]

            graph_objects = []
            graph_result = session.run(
                """MATCH (m:Merchant)
                WHERE toLower(m.normalized_name) CONTAINS toLower($name)
                OPTIONAL MATCH (m)-[r:BELONGS_TO]->(c:Category)
                RETURN m, r, c LIMIT 10""",
                {"name": name},
            )
            for record in graph_result:
                for value in record.values():
                    if value is not None:
                        graph_objects.append(_serialize_graph_element(value))

        output = json.dumps(matches, default=str) if matches else json.dumps({"message": f"No merchants matching '{name}'"})
        collector.collect(graph_objects)
        collector.collect_tool_call("merchant_search", {"name": name}, output[:300])
        return output

    @tool
    def spending_summary(period: str = "", category: str = "", account_id: str = "") -> str:
        """Quick spending summary. Filter by period (YYYY-MM), category name, or account_id."""
        collector = get_collector()
        args = {k: v for k, v in {"period": period, "category": category, "account_id": account_id}.items() if v}
        collector.emit_tool_start("spending_summary", args)

        output = raw_spending_summary(
            period=period or None, category=category or None, account_id=account_id or None
        )
        collector.collect(_collect_finance_story_context(
            driver,
            period=period or None,
            category=category or None,
            account_id=account_id or None,
        ))
        collector.collect_tool_call("spending_summary", args, output[:300])
        return output

    @tool
    def pattern_detection(category: str = "", lookback_months: int = 6) -> str:
        """Detect recurring payments, spending trends, and anomalies."""
        collector = get_collector()
        args = {"category": category, "lookback_months": lookback_months}
        collector.emit_tool_start("pattern_detection", args)

        output = raw_detect_patterns(category=category or None, lookback_months=lookback_months)
        collector.collect(_collect_finance_story_context(
            driver,
            period=None,
            category=category or None,
            account_id=None,
        ))
        collector.collect_tool_call("pattern_detection", args, output[:300])
        return output

    return [graph_schema, cypher_query, merchant_search, spending_summary, pattern_detection]


def _collect_finance_story_context(
    driver: Driver,
    period: str | None = None,
    category: str | None = None,
    account_id: str | None = None,
    limit: int = 40,
) -> list[dict]:
    """Collect a bounded finance subgraph for summary-style tool calls."""
    conditions: list[str] = ["t.amount < 0"]
    params: dict = {"limit": limit}
    if period:
        conditions.append("t.month = $period")
        params["period"] = period
    if category:
        conditions.append("c.name = $category")
        params["category"] = category
    if account_id:
        conditions.append("a.id = $account_id")
        params["account_id"] = account_id

    where_clause = " AND ".join(conditions)
    graph_objects: list[dict] = []
    seen_ids: set[str] = set()

    def _collect(element):
        if element is None:
            return
        serialized = _serialize_graph_element(element)
        eid = serialized.get("elementId")
        if eid and eid not in seen_ids:
            seen_ids.add(eid)
            graph_objects.append(serialized)

    with driver.session() as session:
        result = session.run(
            f"""MATCH (t:Transaction)-[r1:AT_MERCHANT]->(m:Merchant)
            MATCH (t)-[r2:IN_CATEGORY]->(c:Category)
            OPTIONAL MATCH (m)-[r3:BELONGS_TO]->(parent:Category)
            OPTIONAL MATCH (t)-[r4:IN_PERIOD]->(tp:TimePeriod)
            OPTIONAL MATCH (t)-[r5:FROM_ACCOUNT]->(a:Account)
            WHERE {where_clause}
            RETURN t, r1, m, r2, c, r3, parent, r4, tp, r5, a
            ORDER BY abs(t.amount) DESC, t.date DESC
            LIMIT $limit""",
            params,
        )
        for record in result:
            for value in record.values():
                _collect(value)

    return graph_objects


def _extract_graph_context(driver: Driver, records: list[dict]) -> list[dict]:
    """Extract the subgraph behind query results for visualization.

    Scans result records for identifiable values (transaction IDs, merchant names,
    category names, dates) and fetches the actual Neo4j nodes and relationships
    so the frontend can render the relevant subgraph.
    """
    transaction_ids = set()
    merchant_names = set()
    category_names = set()
    dates = set()

    for record in records:
        for key, value in record.items():
            lower_key = key.lower()
            if value is None:
                continue
            if isinstance(value, str):
                if "merchant" in lower_key or "normalized_name" in lower_key:
                    merchant_names.add(value)
                elif "category" in lower_key:
                    category_names.add(value)
                elif "id" in lower_key and "-" in value:
                    transaction_ids.add(value)
                elif "date" in lower_key:
                    dates.add(value)
            elif "description" in lower_key and isinstance(value, str):
                pass

    if not transaction_ids and not merchant_names and not category_names and not dates:
        if records and len(records) <= 20:
            for record in records:
                for value in record.values():
                    if isinstance(value, str) and len(value) > 3:
                        merchant_names.add(value)

    if not transaction_ids and not merchant_names and not category_names:
        return []

    graph_objects: list[dict] = []
    seen_ids: set[str] = set()

    def _collect(element):
        if element is None:
            return
        serialized = _serialize_graph_element(element)
        eid = serialized.get("elementId", "")
        if eid and eid not in seen_ids:
            seen_ids.add(eid)
            graph_objects.append(serialized)

    with driver.session() as session:
        if transaction_ids:
            result = session.run(
                """UNWIND $ids AS tid
                MATCH (t:Transaction {id: tid})
                OPTIONAL MATCH (t)-[r1:AT_MERCHANT]->(m:Merchant)
                OPTIONAL MATCH (t)-[r2:IN_CATEGORY]->(c:Category)
                OPTIONAL MATCH (t)-[r3:IN_PERIOD]->(tp:TimePeriod)
                OPTIONAL MATCH (t)-[r4:FROM_ACCOUNT]->(a:Account)
                RETURN t, r1, m, r2, c, r3, tp, r4, a""",
                {"ids": list(transaction_ids)[:50]},
            )
            for record in result:
                for value in record.values():
                    _collect(value)

        if merchant_names:
            result = session.run(
                """UNWIND $names AS name
                MATCH (m:Merchant {normalized_name: name})
                OPTIONAL MATCH (m)-[r:BELONGS_TO]->(c:Category)
                OPTIONAL MATCH (c)-[r2:SUBCATEGORY_OF]->(parent:Category)
                OPTIONAL MATCH (t:Transaction)-[r3:AT_MERCHANT]->(m)
                WITH m, r, c, r2, parent, t, r3 ORDER BY t.date DESC LIMIT 5
                RETURN m, r, c, r2, parent, t, r3""",
                {"names": list(merchant_names)[:20]},
            )
            for record in result:
                for value in record.values():
                    _collect(value)

        if category_names:
            remaining = category_names - merchant_names
            if remaining:
                result = session.run(
                    """UNWIND $names AS name
                    MATCH (c:Category {name: name})
                    OPTIONAL MATCH (c)-[r:SUBCATEGORY_OF]->(parent:Category)
                    RETURN c, r, parent""",
                    {"names": list(remaining)},
                )
                for record in result:
                    for value in record.values():
                        _collect(value)

        if dates and not transaction_ids and not merchant_names:
            result = session.run(
                """UNWIND $dates AS d
                MATCH (t:Transaction {date: d})
                OPTIONAL MATCH (t)-[r1:AT_MERCHANT]->(m:Merchant)
                OPTIONAL MATCH (t)-[r2:IN_CATEGORY]->(c:Category)
                OPTIONAL MATCH (t)-[r3:IN_PERIOD]->(tp:TimePeriod)
                RETURN t, r1, m, r2, c, r3, tp
                LIMIT 30""",
                {"dates": list(dates)[:10]},
            )
            for record in result:
                for value in record.values():
                    _collect(value)

    return graph_objects


def _serialize_graph_element(element) -> dict:
    """Convert a Neo4j Node or Relationship to a serializable dict matching frontend expectations."""
    from neo4j.graph import Node, Relationship

    if isinstance(element, Node):
        props = dict(element)
        return {
            "elementId": element.element_id,
            "labels": list(element.labels),
            **props,
        }
    elif isinstance(element, Relationship):
        props = dict(element)
        return {
            "elementId": element.element_id,
            "type": element.type,
            "startNodeElementId": element.start_node.element_id,
            "endNodeElementId": element.end_node.element_id,
            **props,
        }
    return {}


def create_orchestrator():
    """Build the LangGraph agent and return (agent, driver)."""
    from app.config import settings

    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USERNAME", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "financegraph")
    driver = GraphDatabase.driver(uri, auth=(user, password))

    tools = _make_graph_tools(driver)

    llm = ChatOpenAI(model=settings.agent_model)
    agent = create_react_agent(llm, tools=tools, prompt=SYSTEM_PROMPT)

    return agent, driver
