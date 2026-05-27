"""Account API routes — list accounts, balance history."""

from fastapi import APIRouter, HTTPException, Query
from neo4j import Driver

router = APIRouter(prefix="/api/accounts", tags=["accounts"])
_driver: Driver | None = None


def init_accounts(driver: Driver):
    global _driver
    _driver = driver


@router.get("")
def list_accounts():
    """List accounts with holder, latest_balance, txn_count."""
    with _driver.session() as session:
        result = session.run(
            """MATCH (a:Account)
            OPTIONAL MATCH (p:Person)-[:OWNS]->(a)
            OPTIONAL MATCH (a)<-[:FROM_ACCOUNT]-(t:Transaction)
            WITH a, p.name AS holder,
                 count(t) AS txn_count,
                 sum(t.amount) AS net_balance
            RETURN a.id AS account_id,
                   a.institution AS institution,
                   a.account_type AS account_type,
                   holder,
                   round(net_balance, 2) AS latest_balance,
                   txn_count
            ORDER BY txn_count DESC""",
        )
        return {"accounts": [dict(r) for r in result]}


@router.get("/{account_id}/balance-history")
def balance_history(
    account_id: str,
    months: int = Query(12, ge=1, le=60),
):
    """Balance over time for an account."""
    with _driver.session() as session:
        # Check account exists
        exists = session.run(
            "MATCH (a:Account {id: $id}) RETURN a",
            {"id": account_id},
        ).single()
        if not exists:
            raise HTTPException(status_code=404, detail="Account not found")

        result = session.run(
            """MATCH (t:Transaction)-[:FROM_ACCOUNT]->(a:Account {id: $id}),
                  (t)-[:IN_PERIOD]->(tp:TimePeriod)
            WITH tp.label AS month, sum(t.amount) AS net
            RETURN month, round(net, 2) AS net
            ORDER BY month DESC
            LIMIT $months""",
            {"id": account_id, "months": months},
        )
        return {"account_id": account_id, "history": [dict(r) for r in result]}
