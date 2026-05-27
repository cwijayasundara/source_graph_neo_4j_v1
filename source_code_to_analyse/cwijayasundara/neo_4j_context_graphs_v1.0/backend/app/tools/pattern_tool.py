"""Spending pattern detection tool."""

import json
from neo4j import Driver


def make_detect_patterns(driver: Driver):
    """Create a pattern detection function bound to *driver*."""

    def detect_patterns(
        category: str | None = None, lookback_months: int = 6
    ) -> str:
        """Detect spending patterns: recurring payments, trends, and anomalies."""
        params: dict = {"lookback": lookback_months}
        cat_filter = ""
        if category:
            cat_filter = "AND c.name = $category"
            params["category"] = category

        with driver.session() as session:
            recurring = session.run(
                "MATCH (t:Transaction)-[:AT_MERCHANT]->(m:Merchant), "
                "(t)-[:IN_CATEGORY]->(c:Category) "
                f"WHERE t.amount < 0 {cat_filter} "
                "WITH m, c, count(DISTINCT t.month) AS months_present, "
                "     avg(abs(t.amount)) AS avg_amount, "
                "     stDev(abs(t.amount)) AS amount_stddev, "
                "     count(t) AS total_txns "
                "WHERE months_present >= 3 "
                "RETURN m.normalized_name AS merchant, c.name AS category, "
                "       months_present, round(avg_amount, 2) AS avg_monthly, "
                "       round(amount_stddev, 2) AS variability, total_txns "
                "ORDER BY avg_amount DESC",
                params,
            )
            recurring_payments = [dict(r) for r in recurring]

            trends = session.run(
                "MATCH (t:Transaction)-[:IN_PERIOD]->(tp:TimePeriod), "
                "(t)-[:IN_CATEGORY]->(c:Category) "
                f"WHERE t.amount < 0 {cat_filter} "
                "RETURN tp.label AS month, c.name AS category, "
                "       sum(abs(t.amount)) AS total, count(t) AS count "
                "ORDER BY tp.label",
                params,
            )
            monthly_trends = [dict(r) for r in trends]

        return json.dumps(
            {
                "recurring_payments": recurring_payments,
                "monthly_trends": monthly_trends,
            },
            default=str,
        )

    return detect_patterns
