"""Transaction API routes — list, search, detail."""

from fastapi import APIRouter, HTTPException, Query
from neo4j import Driver

router = APIRouter(prefix="/api/transactions", tags=["transactions"])
_driver: Driver | None = None


def init_transactions(driver: Driver):
    global _driver
    _driver = driver


@router.get("")
def list_transactions(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    category: str | None = Query(None),
    account_id: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    sort_by: str = Query("date", pattern="^(date|amount)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
):
    """Paginated transaction list with optional filters."""
    conditions = ["true"]
    params: dict = {}
    if category:
        conditions.append("c.name = $category")
        params["category"] = category
    if account_id:
        conditions.append("a.id = $account_id")
        params["account_id"] = account_id
    if date_from:
        conditions.append("t.date >= $date_from")
        params["date_from"] = date_from
    if date_to:
        conditions.append("t.date <= $date_to")
        params["date_to"] = date_to

    where = " AND ".join(conditions)
    skip = (page - 1) * per_page
    order_field = "t.date" if sort_by == "date" else "t.amount"
    order_dir = "DESC" if sort_order == "desc" else "ASC"

    with _driver.session() as session:
        count_result = session.run(
            f"""MATCH (t:Transaction)-[:IN_CATEGORY]->(c:Category),
                  (t)-[:FROM_ACCOUNT]->(a:Account)
            WHERE {where}
            RETURN count(t) AS total""",
            params,
        ).single()
        total = count_result["total"]

        result = session.run(
            f"""MATCH (t:Transaction)-[:IN_CATEGORY]->(c:Category),
                  (t)-[:FROM_ACCOUNT]->(a:Account),
                  (t)-[:AT_MERCHANT]->(m:Merchant)
            WHERE {where}
            RETURN t.id AS id, t.date AS date, t.amount AS amount,
                   t.raw_description AS description,
                   m.normalized_name AS merchant,
                   c.name AS category, a.id AS account_id
            ORDER BY {order_field} {order_dir}
            SKIP $skip LIMIT $per_page""",
            {**params, "skip": skip, "per_page": per_page},
        )
        transactions = [dict(r) for r in result]

    return {
        "transactions": transactions,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if total else 0,
    }


@router.get("/search")
def search_transactions(q: str = Query(..., min_length=1)):
    """Free-text search on raw_description and merchant name."""
    with _driver.session() as session:
        result = session.run(
            """MATCH (t:Transaction)-[:AT_MERCHANT]->(m:Merchant),
                  (t)-[:IN_CATEGORY]->(c:Category)
            WHERE toLower(t.raw_description) CONTAINS toLower($q)
               OR toLower(m.normalized_name) CONTAINS toLower($q)
            RETURN t.id AS id, t.date AS date, t.amount AS amount,
                   t.raw_description AS description,
                   m.normalized_name AS merchant,
                   c.name AS category
            ORDER BY t.date DESC LIMIT 50""",
            {"q": q},
        )
        return {"results": [dict(r) for r in result]}


@router.get("/{transaction_id}")
def get_transaction(transaction_id: str):
    """Single transaction detail with merchant, category, account, person."""
    with _driver.session() as session:
        result = session.run(
            """MATCH (t:Transaction {id: $id})
            OPTIONAL MATCH (t)-[:AT_MERCHANT]->(m:Merchant)
            OPTIONAL MATCH (t)-[:IN_CATEGORY]->(c:Category)
            OPTIONAL MATCH (t)-[:FROM_ACCOUNT]->(a:Account)
            OPTIONAL MATCH (t)-[:PAID_TO]->(p:Person)
            RETURN t.id AS id, t.date AS date, t.amount AS amount,
                   t.raw_description AS description,
                   t.payment_method AS payment_method,
                   m.normalized_name AS merchant,
                   c.name AS category,
                   a.id AS account_id,
                   p.name AS person""",
            {"id": transaction_id},
        ).single()
        if not result:
            raise HTTPException(status_code=404, detail="Transaction not found")
        return dict(result)
