"""Tests for the Neo4j graph loader."""

from unittest.mock import MagicMock, call

import pytest
from ingestion.loader import GraphLoader


@pytest.fixture
def mock_driver():
    """Create a mock Neo4j driver with a mock session."""
    driver = MagicMock()
    session = MagicMock()
    driver.session.return_value.__enter__ = MagicMock(return_value=session)
    driver.session.return_value.__exit__ = MagicMock(return_value=False)
    return driver, session


@pytest.fixture
def loader(mock_driver):
    """Create a GraphLoader backed by a mock driver."""
    driver, _ = mock_driver
    return GraphLoader(driver)


class TestLoadTimePeriods:
    """Tests for load_time_periods()."""

    def test_deduplicates_periods(self, mock_driver):
        """Duplicate (year, month) pairs produce only one MERGE each."""
        driver, session = mock_driver
        loader = GraphLoader(driver)
        transactions = [
            {"year": 2025, "month": "2025-01"},
            {"year": 2025, "month": "2025-01"},
            {"year": 2025, "month": "2025-02"},
        ]
        loader.load_time_periods(transactions)
        # Should be called exactly 2 times (Jan + Feb), not 3
        assert session.run.call_count == 2

    def test_quarter_calculation(self, mock_driver):
        """Quarter is derived correctly from the month string."""
        driver, session = mock_driver
        loader = GraphLoader(driver)
        transactions = [{"year": 2025, "month": "2025-04"}]
        loader.load_time_periods(transactions)
        session.run.assert_called_once()
        _, kwargs = session.run.call_args
        assert kwargs["quarter"] == "Q2"

    def test_quarter_q1(self, mock_driver):
        driver, session = mock_driver
        loader = GraphLoader(driver)
        loader.load_time_periods([{"year": 2025, "month": "2025-03"}])
        _, kwargs = session.run.call_args
        assert kwargs["quarter"] == "Q1"

    def test_quarter_q3(self, mock_driver):
        driver, session = mock_driver
        loader = GraphLoader(driver)
        loader.load_time_periods([{"year": 2025, "month": "2025-09"}])
        _, kwargs = session.run.call_args
        assert kwargs["quarter"] == "Q3"

    def test_quarter_q4(self, mock_driver):
        driver, session = mock_driver
        loader = GraphLoader(driver)
        loader.load_time_periods([{"year": 2025, "month": "2025-12"}])
        _, kwargs = session.run.call_args
        assert kwargs["quarter"] == "Q4"


class TestLoadAccounts:
    """Tests for load_accounts()."""

    def test_merge_creates_account_and_institution(self, mock_driver):
        """Each account triggers a MERGE with AT_INSTITUTION relationship."""
        driver, session = mock_driver
        loader = GraphLoader(driver)
        accounts = [
            {"account_id": "ACC1", "institution": "Halifax", "account_type": "current"},
        ]
        loader.load_accounts(accounts)
        session.run.assert_called_once()
        cypher = session.run.call_args[0][0]
        assert "MERGE" in cypher
        assert "AT_INSTITUTION" in cypher

    def test_default_account_type(self, mock_driver):
        """Missing account_type defaults to 'current'."""
        driver, session = mock_driver
        loader = GraphLoader(driver)
        accounts = [{"account_id": "ACC1", "institution": "Halifax"}]
        loader.load_accounts(accounts)
        _, kwargs = session.run.call_args
        assert kwargs["type"] == "current"

    def test_multiple_accounts(self, mock_driver):
        driver, session = mock_driver
        loader = GraphLoader(driver)
        accounts = [
            {"account_id": "ACC1", "institution": "Halifax", "account_type": "current"},
            {"account_id": "ACC2", "institution": "Monzo", "account_type": "savings"},
        ]
        loader.load_accounts(accounts)
        assert session.run.call_count == 2


class TestLoadMerchants:
    """Tests for load_merchants()."""

    def test_creates_belongs_to_relationship(self, mock_driver):
        """Merchant nodes get a BELONGS_TO edge to their Category."""
        driver, session = mock_driver
        loader = GraphLoader(driver)
        merchants = {
            "Tesco": {"category": "Essentials", "subcategory": "Groceries"},
        }
        loader.load_merchants(merchants)
        session.run.assert_called_once()
        cypher = session.run.call_args[0][0]
        assert "BELONGS_TO" in cypher
        _, kwargs = session.run.call_args
        assert kwargs["name"] == "Tesco"
        assert kwargs["subcategory"] == "Groceries"

    def test_multiple_merchants(self, mock_driver):
        driver, session = mock_driver
        loader = GraphLoader(driver)
        merchants = {
            "Tesco": {"category": "Essentials", "subcategory": "Groceries"},
            "Shell": {"category": "Transport", "subcategory": "Fuel"},
        }
        loader.load_merchants(merchants)
        assert session.run.call_count == 2


class TestLoadTransactions:
    """Tests for load_transactions()."""

    def test_creates_all_relationships(self, mock_driver):
        """A single transaction creates edges to Account, Statement,
        Merchant, Category, and TimePeriod."""
        driver, session = mock_driver
        loader = GraphLoader(driver)
        transactions = [
            {
                "id": "ACC1-2025-01-01--28.74-0",
                "date": "2025-01-01",
                "amount": -28.74,
                "balance": 5000.0,
                "raw_description": "TESCO STORES 3372 (DEB)",
                "payment_method": "DEB",
                "year": 2025,
                "month": "2025-01",
                "account_id": "ACC1",
                "statement_id": "ACC1-2025-01",
                "normalized_merchant": "Tesco",
                "category": "Groceries",
            },
        ]
        loader.load_transactions(transactions)
        session.run.assert_called_once()
        cypher = session.run.call_args[0][0]
        assert "FROM_ACCOUNT" in cypher
        assert "CONTAINS" in cypher
        assert "AT_MERCHANT" in cypher
        assert "IN_CATEGORY" in cypher
        assert "IN_PERIOD" in cypher

    def test_transaction_parameters(self, mock_driver):
        """Verify the correct parameters are passed to the Cypher query."""
        driver, session = mock_driver
        loader = GraphLoader(driver)
        transactions = [
            {
                "id": "ACC1-2025-01-01--28.74-0",
                "date": "2025-01-01",
                "amount": -28.74,
                "balance": 5000.0,
                "raw_description": "TESCO STORES 3372 (DEB)",
                "payment_method": "DEB",
                "year": 2025,
                "month": "2025-01",
                "account_id": "ACC1",
                "statement_id": "ACC1-2025-01",
                "normalized_merchant": "Tesco",
                "category": "Groceries",
            },
        ]
        loader.load_transactions(transactions)
        _, kwargs = session.run.call_args
        assert kwargs["id"] == "ACC1-2025-01-01--28.74-0"
        assert kwargs["amount"] == -28.74
        assert kwargs["merchant"] == "Tesco"
        assert kwargs["category"] == "Groceries"


class TestLoadPersonLinks:
    """Tests for load_person_links()."""

    def test_creates_paid_to_edge(self, mock_driver):
        driver, session = mock_driver
        loader = GraphLoader(driver)
        transactions = [
            {"id": "TXN1", "person": {"name": "Pepper Potts", "role": "payee"}},
        ]
        loader.load_person_links(transactions)
        session.run.assert_called_once()
        cypher = session.run.call_args[0][0]
        assert "PAID_TO" in cypher

    def test_skips_transactions_without_person(self, mock_driver):
        driver, session = mock_driver
        loader = GraphLoader(driver)
        transactions = [
            {"id": "TXN1"},
            {"id": "TXN2", "person": None},
        ]
        loader.load_person_links(transactions)
        session.run.assert_not_called()


class TestLoadAccountOwners:
    """Tests for load_account_owners()."""

    def test_creates_owns_edges(self, mock_driver):
        driver, session = mock_driver
        loader = GraphLoader(driver)
        loader.load_account_owners("Tony Stark", ["ACC1", "ACC2"])
        # 1 person MERGE + 2 OWNS edges = 3 calls
        assert session.run.call_count == 3

    def test_owner_role_set(self, mock_driver):
        driver, session = mock_driver
        loader = GraphLoader(driver)
        loader.load_account_owners("Tony Stark", ["ACC1"])
        first_call_kwargs = session.run.call_args_list[0][1]
        assert first_call_kwargs["name"] == "Tony Stark"


class TestLoadPersons:
    """Tests for load_persons()."""

    def test_creates_person_nodes(self, mock_driver):
        driver, session = mock_driver
        loader = GraphLoader(driver)
        persons = [
            {"name": "Acme Industries", "role": "employer"},
            {"name": "Pepper Potts", "role": "payee"},
        ]
        loader.load_persons(persons)
        assert session.run.call_count == 2


class TestLoadStatements:
    """Tests for load_statements()."""

    def test_creates_has_statement_edge(self, mock_driver):
        driver, session = mock_driver
        loader = GraphLoader(driver)
        statements = [
            {
                "statement_id": "ACC1-2025-01",
                "account_id": "ACC1",
                "period_start": "2025-01-01",
                "period_end": "2025-01-31",
            },
        ]
        loader.load_statements(statements)
        session.run.assert_called_once()
        cypher = session.run.call_args[0][0]
        assert "HAS_STATEMENT" in cypher
