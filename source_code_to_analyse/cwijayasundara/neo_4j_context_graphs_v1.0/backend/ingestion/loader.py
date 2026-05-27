"""Neo4j graph loader for the FinanceGraph ingestion pipeline.

Creates and links nodes for accounts, transactions, merchants, time
periods, statements, and persons using idempotent MERGE operations.
"""

from neo4j import Driver


class GraphLoader:
    """Load normalized financial data into a Neo4j graph."""

    def __init__(self, driver: Driver):
        self.driver = driver

    def load_time_periods(self, transactions: list[dict]):
        """Create TimePeriod nodes for each distinct (year, month) pair."""
        periods = {(t["year"], t["month"]) for t in transactions}
        with self.driver.session() as session:
            for year, month in periods:
                quarter = f"Q{(int(month.split('-')[1]) - 1) // 3 + 1}"
                session.run(
                    "MERGE (tp:TimePeriod {label: $label}) "
                    "SET tp.year = $year, tp.month = $month, tp.quarter = $quarter",
                    label=month,
                    year=year,
                    month=month,
                    quarter=quarter,
                )

    def load_accounts(self, accounts: list[dict]):
        """Create Account and Institution nodes with AT_INSTITUTION edges."""
        with self.driver.session() as session:
            for acct in accounts:
                session.run(
                    """MERGE (a:Account {id: $id})
                    SET a.type = $type, a.institution = $institution
                    MERGE (inst:Institution {name: $institution})
                    SET inst.type = 'bank'
                    MERGE (a)-[:AT_INSTITUTION]->(inst)""",
                    id=acct["account_id"],
                    type=acct.get("account_type", "current"),
                    institution=acct["institution"],
                )

    def load_persons(self, persons: list[dict]):
        """Create Person nodes with role properties."""
        with self.driver.session() as session:
            for person in persons:
                session.run(
                    "MERGE (p:Person {name: $name}) SET p.role = $role",
                    name=person["name"],
                    role=person["role"],
                )

    def load_merchants(self, merchants_with_categories: dict):
        """Create Merchant nodes and link them to Category nodes."""
        with self.driver.session() as session:
            for merchant_name, cat_info in merchants_with_categories.items():
                session.run(
                    """MERGE (m:Merchant {normalized_name: $name})
                    SET m.name = $name, m.id = $name
                    WITH m
                    MATCH (c:Category {name: $subcategory})
                    MERGE (m)-[:BELONGS_TO]->(c)""",
                    name=merchant_name,
                    subcategory=cat_info["subcategory"],
                )

    def load_statements(self, statements: list[dict]):
        """Create Statement nodes and link to their Account."""
        with self.driver.session() as session:
            for stmt in statements:
                session.run(
                    """MERGE (s:Statement {id: $id})
                    SET s.period_start = $period_start, s.period_end = $period_end
                    WITH s
                    MATCH (a:Account {id: $account_id})
                    MERGE (a)-[:HAS_STATEMENT]->(s)""",
                    id=stmt["statement_id"],
                    period_start=stmt.get("period_start", ""),
                    period_end=stmt.get("period_end", ""),
                    account_id=stmt["account_id"],
                )

    def load_transactions(self, transactions: list[dict]):
        """Create Transaction nodes with all relationship edges."""
        with self.driver.session() as session:
            for txn in transactions:
                session.run(
                    """MERGE (t:Transaction {id: $id})
                    SET t.date = $date, t.amount = $amount, t.balance = $balance,
                        t.raw_description = $raw_description, t.payment_method = $payment_method,
                        t.year = $year, t.month = $month
                    WITH t
                    MATCH (a:Account {id: $account_id}) MERGE (t)-[:FROM_ACCOUNT]->(a)
                    WITH t
                    MATCH (s:Statement {id: $statement_id}) MERGE (s)-[:CONTAINS]->(t)
                    WITH t
                    MATCH (m:Merchant {normalized_name: $merchant}) MERGE (t)-[:AT_MERCHANT]->(m)
                    WITH t
                    MATCH (c:Category {name: $category}) MERGE (t)-[:IN_CATEGORY]->(c)
                    WITH t
                    MATCH (tp:TimePeriod {label: $month}) MERGE (t)-[:IN_PERIOD]->(tp)""",
                    id=txn["id"],
                    date=txn["date"],
                    amount=txn["amount"],
                    balance=txn["balance"],
                    raw_description=txn["raw_description"],
                    payment_method=txn.get("payment_method"),
                    year=txn["year"],
                    month=txn["month"],
                    account_id=txn["account_id"],
                    statement_id=txn["statement_id"],
                    merchant=txn["normalized_merchant"],
                    category=txn["category"],
                )

    def load_person_links(self, transactions: list[dict]):
        """Create PAID_TO edges between Transactions and Persons."""
        with self.driver.session() as session:
            for txn in transactions:
                if txn.get("person"):
                    session.run(
                        """MATCH (t:Transaction {id: $txn_id})
                        MATCH (p:Person {name: $person_name})
                        MERGE (t)-[:PAID_TO]->(p)""",
                        txn_id=txn["id"],
                        person_name=txn["person"]["name"],
                    )

    def load_account_owners(self, owner_name: str, account_ids: list[str]):
        """Create OWNS edges between a Person and their Accounts."""
        with self.driver.session() as session:
            session.run(
                "MERGE (p:Person {name: $name}) SET p.role = 'account_holder'",
                name=owner_name,
            )
            for acct_id in account_ids:
                session.run(
                    """MATCH (p:Person {name: $name})
                    MATCH (a:Account {id: $acct_id})
                    MERGE (p)-[:OWNS]->(a)""",
                    name=owner_name,
                    acct_id=acct_id,
                )
