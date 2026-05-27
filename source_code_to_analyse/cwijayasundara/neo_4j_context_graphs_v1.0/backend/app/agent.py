"""Financial Services AI Agent — LangGraph implementation."""

from __future__ import annotations

import json

from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from app.config import settings
from app.context_graph_client import execute_cypher, get_schema
from app.memory import store_message, get_context, resolve_session_id


SYSTEM_PROMPT = """You are an AI financial intelligence assistant with access to a comprehensive
knowledge graph of financial data. You help financial advisors, compliance
officers, and portfolio managers analyze accounts, transactions, decisions,
and policies.

Your capabilities include:
- Searching and analyzing client portfolios and transaction history
- Reviewing compliance status and policy adherence
- Tracing decision provenance and causal chains
- Identifying patterns and anomalies in financial data
- Finding similar past decisions to inform current choices

Always provide accurate, data-driven responses. When making recommendations,
cite the specific data points and reasoning from the knowledge graph.


IMPORTANT: You MUST use the available tools to query the knowledge graph before answering any question about the data. Never guess or make up information — always use tools to look up actual data from the graph.

CRITICAL: Call tools DIRECTLY without any introductory text. Do NOT say "I'll search for..." or "Let me look up..." before calling a tool — just call the tool immediately. Only generate text AFTER you have received the tool results and are ready to provide your final answer."""

# ---------------------------------------------------------------------------
# Agent tools — domain-specific for Financial Services
# ---------------------------------------------------------------------------

@tool
async def search_customer(query: str) -> str:
    """Search for clients, advisors, or other people by name or role"""
    cypher = """MATCH (p:Person)
    WHERE toLower(p.name) CONTAINS toLower($query)
       OR toLower(coalesce(p.role, '')) CONTAINS toLower($query)
    OPTIONAL MATCH (p)-[r]-(related)
    RETURN p, type(r) AS rel_type, related
    LIMIT 20
"""
    params = {
        "query": query,
    }
    result = await execute_cypher(cypher, params, tool_name="search_customer")
    return json.dumps(result, default=str)

@tool
async def get_customer_decisions(name: str) -> str:
    """Get all decisions related to a specific client"""
    cypher = """MATCH (p:Person {name: $name})-[:OWNS|MANAGES]->(a:Account)
    OPTIONAL MATCH (d:Decision)-[:CAUSED]->(t:Transaction)-[:TRANSFERRED_TO|TRANSFERRED_FROM]->(a)
    RETURN p, a, d, t
    ORDER BY d.date DESC
    LIMIT 20
"""
    params = {
        "name": name,
    }
    result = await execute_cypher(cypher, params, tool_name="get_customer_decisions")
    return json.dumps(result, default=str)

@tool
async def find_similar_decisions(decision_id: str) -> str:
    """Find decisions similar to a given decision using vector similarity"""
    cypher = """MATCH (d:Decision {decision_id: $decision_id})
    CALL db.index.vector.queryNodes('decision_embeddings', 5, d.embedding)
    YIELD node, score
    WHERE node.decision_id <> $decision_id
    RETURN node AS similar_decision, score
    ORDER BY score DESC
"""
    params = {
        "decision_id": decision_id,
    }
    result = await execute_cypher(cypher, params, tool_name="find_similar_decisions")
    return json.dumps(result, default=str)

@tool
async def get_causal_chain(decision_id: str) -> str:
    """Trace the causal chain of events from a decision"""
    cypher = """MATCH path = (d:Decision {decision_id: $decision_id})-[:CAUSED|PRECEDED_BY*1..5]-(related)
    RETURN path
"""
    params = {
        "decision_id": decision_id,
    }
    result = await execute_cypher(cypher, params, tool_name="get_causal_chain")
    return json.dumps(result, default=str)

@tool
async def detect_fraud_patterns() -> str:
    """Detect unusual transaction patterns that may indicate fraud"""
    cypher = """MATCH (a:Account)<-[:TRANSFERRED_TO]-(t:Transaction)
    WHERE t.date > datetime() - duration('P30D')
    WITH a, count(t) AS tx_count, sum(t.amount) AS total_amount
    WHERE tx_count > 10 OR total_amount > 100000
    RETURN a.account_id, a.name, tx_count, total_amount
    ORDER BY total_amount DESC
"""
    params = {
    }
    result = await execute_cypher(cypher, params, tool_name="detect_fraud_patterns")
    return json.dumps(result, default=str)

@tool
async def list_accounts(limit: str) -> str:
    """List Account records with optional limit"""
    cypher = """MATCH (n:Account)
    RETURN n
    ORDER BY n.name
    LIMIT toInteger($limit)
"""
    params = {
        "limit": limit,
    }
    result = await execute_cypher(cypher, params, tool_name="list_accounts")
    return json.dumps(result, default=str)

@tool
async def get_account_by_id(id: str) -> str:
    """Get a specific Account by ID with all connections"""
    cypher = """MATCH (n:Account {account_id: $id})
    OPTIONAL MATCH (n)-[r]-(related)
    RETURN n, type(r) AS relationship, labels(related) AS related_labels, related.name AS related_name
    LIMIT 50
"""
    params = {
        "id": id,
    }
    result = await execute_cypher(cypher, params, tool_name="get_account_by_id")
    return json.dumps(result, default=str)



@tool
async def run_cypher(query: str, parameters: str = "{}") -> str:
    """Execute a read-only Cypher query against the knowledge graph."""
    try:
        params = json.loads(parameters) if parameters else {}
    except json.JSONDecodeError:
        return json.dumps({"error": "Invalid JSON parameters"})
    params.setdefault("domain", settings.domain_id)
    try:
        result = await execute_cypher(query, params, tool_name="run_cypher")
        return json.dumps(result, default=str)
    except Exception as e:
        return json.dumps({"error": f"Cypher query failed: {e}"})


@tool
async def get_graph_schema() -> str:
    """Get the knowledge graph schema (node labels and relationship types)."""
    result = await get_schema()
    return json.dumps(result, default=str)

TOOLS = [
    search_customer,
    get_customer_decisions,
    find_similar_decisions,
    get_causal_chain,
    detect_fraud_patterns,
    list_accounts,
    get_account_by_id,
    run_cypher,
    get_graph_schema,
]


model = ChatOpenAI(
    model=settings.agent_model,
    api_key=settings.openai_api_key,
)

graph = create_react_agent(model, TOOLS, prompt=SYSTEM_PROMPT)


# ---------------------------------------------------------------------------
# Message handler
# ---------------------------------------------------------------------------


async def handle_message(message: str, session_id: str | None = None) -> dict:
    """Handle an incoming chat message."""
    session_id = resolve_session_id(session_id)

    # Retrieve conversation history and store the new user message
    await store_message(session_id, "user", message)
    context = await get_context(session_id, query=message)
    history = context.get("messages", [])

    # Build messages list with conversation history
    from langchain_core.messages import HumanMessage, AIMessage
    history_messages = []
    for msg in history:
        if msg["role"] == "user":
            history_messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            history_messages.append(AIMessage(content=msg["content"]))

    result = await graph.ainvoke(
        {"messages": history_messages + [HumanMessage(content=message)]},
        config={"configurable": {"thread_id": session_id}},
    )

    # Extract the last AI message
    ai_messages = [m for m in result["messages"] if hasattr(m, "content") and m.type == "ai"]
    response_text = ai_messages[-1].content if ai_messages else ""
    if not response_text.strip():
        response_text = "I searched the knowledge graph but couldn't find relevant results for your query. Could you try rephrasing your question?"

    assistant_result = await store_message(session_id, "assistant", response_text)

    return {
        "response": response_text,
        "session_id": session_id,
        "graph_data": None,
        "entities_extracted": (assistant_result or {}).get("entities", []),
        "preferences_detected": (assistant_result or {}).get("preferences", []),
    }


async def handle_message_stream(message: str, session_id: str | None = None) -> dict:
    """Handle a chat message with streaming text deltas via the collector event queue."""
    from app.context_graph_client import get_collector

    session_id = resolve_session_id(session_id)

    collector = get_collector()
    await store_message(session_id, "user", message)
    context = await get_context(session_id, query=message)
    history = context.get("messages", [])

    from langchain_core.messages import HumanMessage, AIMessage
    history_messages = []
    for msg in history:
        if msg["role"] == "user":
            history_messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            history_messages.append(AIMessage(content=msg["content"]))

    response_text = ""
    async for event in graph.astream_events(
        {"messages": history_messages + [HumanMessage(content=message)]},
        config={"configurable": {"thread_id": session_id}},
        version="v2",
    ):
        kind = event.get("event", "")
        if kind == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if chunk and hasattr(chunk, "content"):
                text = ""
                if isinstance(chunk.content, str):
                    text = chunk.content
                elif isinstance(chunk.content, list):
                    text = "".join(
                        block.get("text", "") if isinstance(block, dict) else getattr(block, "text", "")
                        for block in chunk.content
                        if (isinstance(block, dict) and block.get("type") == "text")
                        or (hasattr(block, "type") and getattr(block, "type", None) == "text")
                    )
                if text:
                    collector.emit_text_delta(text)
                    response_text += text

    if not response_text.strip():
        response_text = "I searched the knowledge graph but couldn't find relevant results for your query. Could you try rephrasing your question?"

    assistant_result = await store_message(session_id, "assistant", response_text)
    if assistant_result:
        collector.emit_entities_extracted(assistant_result.get("entities", []))
        collector.emit_preferences_detected(assistant_result.get("preferences", []))
    collector.emit_done(response_text, session_id)

    return {
        "response": response_text,
        "session_id": session_id,
        "graph_data": None,
    }
