"""Merchant API routes — list, detail, category override."""

import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from neo4j import Driver
from pydantic import BaseModel

router = APIRouter(prefix="/api/merchants", tags=["merchants"])
_driver: Driver | None = None


def init_merchants(driver: Driver):
    global _driver
    _driver = driver


class CategoryOverride(BaseModel):
    category: str
    subcategory: str


@router.get("")
def list_merchants(
    limit: int = Query(100, ge=1, le=500),
):
    """List all merchants with categories, transaction_count, total_spent."""
    with _driver.session() as session:
        result = session.run(
            """MATCH (m:Merchant)<-[:AT_MERCHANT]-(t:Transaction)
            OPTIONAL MATCH (m)-[:IN_CATEGORY]->(c:Category)
            WITH m.normalized_name AS merchant, c.name AS category,
                 count(t) AS transaction_count,
                 sum(abs(t.amount)) AS total_spent
            RETURN merchant, category, transaction_count,
                   round(total_spent, 2) AS total_spent
            ORDER BY total_spent DESC
            LIMIT $limit""",
            {"limit": limit},
        )
        return {"merchants": [dict(r) for r in result]}


@router.get("/{merchant_name}")
def get_merchant(merchant_name: str):
    """Merchant detail with avg_transaction, active_months."""
    with _driver.session() as session:
        result = session.run(
            """MATCH (m:Merchant {normalized_name: $name})<-[:AT_MERCHANT]-(t:Transaction)
            OPTIONAL MATCH (m)-[:IN_CATEGORY]->(c:Category)
            OPTIONAL MATCH (t)-[:IN_PERIOD]->(tp:TimePeriod)
            WITH m, c.name AS category,
                 count(t) AS transaction_count,
                 sum(abs(t.amount)) AS total_spent,
                 avg(abs(t.amount)) AS avg_transaction,
                 collect(DISTINCT tp.label) AS active_months
            RETURN m.normalized_name AS merchant, category,
                   transaction_count,
                   round(total_spent, 2) AS total_spent,
                   round(avg_transaction, 2) AS avg_transaction,
                   active_months""",
            {"name": merchant_name},
        ).single()
        if not result:
            raise HTTPException(status_code=404, detail="Merchant not found")
        return dict(result)


@router.patch("/{merchant_name}/category")
def override_category(merchant_name: str, body: CategoryOverride):
    """Override merchant category in graph AND merchant_categories.json cache."""
    # Update Neo4j graph
    with _driver.session() as session:
        # Check merchant exists
        exists = session.run(
            "MATCH (m:Merchant {normalized_name: $name}) RETURN m",
            {"name": merchant_name},
        ).single()
        if not exists:
            raise HTTPException(status_code=404, detail="Merchant not found")

        # Remove old category relationship and create new one
        session.run(
            """MATCH (m:Merchant {normalized_name: $name})
            OPTIONAL MATCH (m)-[r:IN_CATEGORY]->()
            DELETE r
            WITH m
            MERGE (c:Category {name: $subcategory})
            MERGE (m)-[:IN_CATEGORY]->(c)""",
            {"name": merchant_name, "subcategory": body.subcategory},
        )

        # Also update transactions linked to this merchant
        session.run(
            """MATCH (t:Transaction)-[:AT_MERCHANT]->(m:Merchant {normalized_name: $name})
            OPTIONAL MATCH (t)-[r:IN_CATEGORY]->()
            DELETE r
            WITH t
            MATCH (c:Category {name: $subcategory})
            MERGE (t)-[:IN_CATEGORY]->(c)""",
            {"name": merchant_name, "subcategory": body.subcategory},
        )

    # Update local JSON cache
    cache_path = Path(
        os.environ.get("MERCHANT_CACHE_PATH", "./data/merchant_categories.json")
    )
    if cache_path.exists():
        cache = json.loads(cache_path.read_text())
    else:
        cache = {}
    cache[merchant_name] = {
        "category": body.category,
        "subcategory": body.subcategory,
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=2))

    return {
        "merchant": merchant_name,
        "category": body.category,
        "subcategory": body.subcategory,
        "status": "updated",
    }
