"""Tests for the agent tools — primarily the read-only Cypher guard."""

import json
import pytest
from unittest.mock import MagicMock, patch

from app.tools.cypher_tool import _is_read_only, make_execute_cypher
from app.deep_agent import _collect_finance_story_context
from neo4j.graph import Graph, Node


# ---------------------------------------------------------------------------
# _is_read_only – pure-logic tests (no DB needed)
# ---------------------------------------------------------------------------


class TestIsReadOnly:
    """Verify the write-keyword guard."""

    @pytest.mark.parametrize(
        "query",
        [
            "MATCH (n) RETURN n",
            "MATCH (n:Transaction) WHERE n.amount < 0 RETURN n",
            "MATCH (a)-[r]->(b) RETURN a, type(r), b",
            "MATCH (t) WITH t ORDER BY t.date RETURN t LIMIT 10",
            "MATCH (m:Merchant) WHERE m.name CONTAINS 'Tesco' RETURN m",
            "CALL db.labels() YIELD label RETURN label",
            "MATCH (n) RETURN count(n)",
        ],
    )
    def test_allows_read_queries(self, query: str):
        assert _is_read_only(query) is True

    @pytest.mark.parametrize(
        "query",
        [
            "CREATE (n:Test {name: 'x'})",
            "MERGE (n:Test {name: 'x'})",
            "MATCH (n) DELETE n",
            "MATCH (n) DETACH DELETE n",
            "MATCH (n) SET n.name = 'y'",
            "MATCH (n) REMOVE n.name",
            "DROP CONSTRAINT ON (n:Test) ASSERT n.name IS UNIQUE",
        ],
    )
    def test_blocks_write_queries(self, query: str):
        assert _is_read_only(query) is False

    def test_case_insensitive(self):
        assert _is_read_only("create (n:Test)") is False
        assert _is_read_only("Create (n:Test)") is False
        assert _is_read_only("CrEaTe (n:Test)") is False

    def test_allows_with_where_return(self):
        query = (
            "MATCH (t:Transaction) "
            "WITH t WHERE t.amount < 0 "
            "RETURN t.amount ORDER BY t.amount"
        )
        assert _is_read_only(query) is True


# ---------------------------------------------------------------------------
# make_execute_cypher – integration-style tests with a mocked driver
# ---------------------------------------------------------------------------


class TestMakeExecuteCypher:
    """Test the Cypher execution function with a mocked Neo4j driver."""

    def _mock_driver(self, records: list[dict] | None = None):
        """Return a mock driver whose session().run() yields *records*."""
        records = records or []
        mock_records = []
        for rec in records:
            mock_record = MagicMock()
            mock_record.__iter__ = lambda self: iter(self._items)
            mock_record._items = list(rec.items())
            mock_record.keys.return_value = list(rec.keys())
            mock_record.values.return_value = list(rec.values())
            # dict(record) needs to work
            mock_record.__getitem__ = lambda self, key: dict(self._items)[key]
            mock_record.__contains__ = lambda self, key: key in dict(self._items)
            # Make dict() conversion work via keys()
            mock_records.append(rec)  # just use dicts directly

        driver = MagicMock()
        session = MagicMock()
        result = MagicMock()
        result.__iter__ = lambda self: iter(mock_records)

        session.run.return_value = result
        driver.session.return_value.__enter__ = MagicMock(return_value=session)
        driver.session.return_value.__exit__ = MagicMock(return_value=False)

        return driver, session

    def test_read_query_returns_json(self):
        driver, session = self._mock_driver([{"name": "Tesco", "amount": -42.50}])
        execute = make_execute_cypher(driver)
        raw = execute("MATCH (n) RETURN n.name AS name, n.amount AS amount")
        data = json.loads(raw)
        assert isinstance(data, list)
        assert data[0]["name"] == "Tesco"

    def test_write_query_returns_error(self):
        driver, session = self._mock_driver()
        execute = make_execute_cypher(driver)
        raw = execute("CREATE (n:Test {name: 'x'})")
        data = json.loads(raw)
        assert "error" in data
        assert "Write operations" in data["error"]
        # Session.run should NOT have been called
        session.run.assert_not_called()

    def test_passes_params(self):
        driver, session = self._mock_driver([])
        execute = make_execute_cypher(driver)
        execute("MATCH (n) WHERE n.id = $id RETURN n", {"id": "123"})
        session.run.assert_called_once_with(
            "MATCH (n) WHERE n.id = $id RETURN n", {"id": "123"}
        )

    def test_empty_params_default(self):
        driver, session = self._mock_driver([])
        execute = make_execute_cypher(driver)
        execute("MATCH (n) RETURN n")
        session.run.assert_called_once_with("MATCH (n) RETURN n", {})


class TestFinanceStoryContext:
    """Graph context helpers used by summary-style agent tools."""

    def test_collects_transaction_context_for_spending_summary_filters(self):
        graph = Graph()
        txn = Node(graph, "t1", 1, ["Transaction"], {"id": "TXN1", "date": "2026-01-02"})
        merchant = Node(graph, "m1", 2, ["Merchant"], {"normalized_name": "Tesco"})
        rel = graph.relationship_type("AT_MERCHANT")(graph, "r1", 3, {})
        rel._start_node = txn
        rel._end_node = merchant

        class FakeSession:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def run(self, _query, _params):
                return [{"t": txn, "r1": rel, "m": merchant}]

        class FakeDriver:
            def session(self):
                return FakeSession()

        context = _collect_finance_story_context(
            FakeDriver(),
            period="2026-01",
            category=None,
            account_id=None,
            limit=10,
        )

        assert {item["elementId"] for item in context} == {"t1", "m1", "r1"}
