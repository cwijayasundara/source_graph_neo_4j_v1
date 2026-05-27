"""Spending summary tool."""

import json
from neo4j import Driver


def make_get_spending_summary(driver: Driver):
    """Create a spending summary function bound to *driver*."""

    def get_spending_summary(
        period: str | None = None,
        category: str | None = None,
        account_id: str | None = None,
    ) -> str:
        """Get a spending summary.

        Filter by period (e.g. '2025-01'), category, and/or account_id.
        """
        conditions: list[str] = []
        params: dict = {}

        if period:
            conditions.append("t.month = $period")
            params["period"] = period
        if category:
            conditions.append("c.name = $category")
            params["category"] = category
        if account_id:
            conditions.append("a.id = $account_id")
            params["account_id"] = account_id

        where_clause = " AND ".join(conditions) if conditions else "true"

        query = (
            "MATCH (t:Transaction)-[:FROM_ACCOUNT]->(a:Account), "
            "(t)-[:IN_CATEGORY]->(c:Category) "
            f"WHERE {where_clause} "
            "RETURN sum(CASE WHEN t.amount > 0 THEN t.amount ELSE 0 END) AS total_in, "
            "       sum(CASE WHEN t.amount < 0 THEN abs(t.amount) ELSE 0 END) AS total_out, "
            "       sum(t.amount) AS net, "
            "       count(t) AS transaction_count"
        )

        with driver.session() as session:
            result = session.run(query, params).single()
            summary = dict(result)

            top_merchants = session.run(
                "MATCH (t:Transaction)-[:AT_MERCHANT]->(m:Merchant), "
                "(t)-[:FROM_ACCOUNT]->(a:Account), "
                "(t)-[:IN_CATEGORY]->(c:Category) "
                f"WHERE {where_clause} AND t.amount < 0 "
                "RETURN m.normalized_name AS merchant, "
                "       sum(abs(t.amount)) AS total, count(t) AS count "
                "ORDER BY total DESC LIMIT 5",
                params,
            )
            summary["top_merchants"] = [dict(r) for r in top_merchants]

        return json.dumps(summary, default=str)

    return get_spending_summary
