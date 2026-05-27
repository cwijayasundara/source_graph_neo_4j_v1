"""Dashboard analytics service backed by Neo4j."""

from neo4j import Driver


class DashboardService:
    def __init__(self, driver: Driver):
        self.driver = driver

    def get_summary(self, period: str | None = None) -> dict:
        period_filter = "AND t.month = $period" if period else ""
        params = {"period": period} if period else {}
        with self.driver.session() as session:
            result = session.run(
                f"""MATCH (t:Transaction) WHERE true {period_filter}
                RETURN sum(CASE WHEN t.amount > 0 THEN t.amount ELSE 0 END) AS total_in,
                    sum(CASE WHEN t.amount < 0 THEN abs(t.amount) ELSE 0 END) AS total_out,
                    sum(t.amount) AS net, count(t) AS transaction_count""",
                params,
            ).single()
            top_cat = session.run(
                f"""MATCH (t:Transaction)-[:IN_CATEGORY]->(c:Category)
                WHERE t.amount < 0 {period_filter}
                RETURN c.name AS category, sum(abs(t.amount)) AS total
                ORDER BY total DESC LIMIT 1""",
                params,
            ).single()
            top_merch = session.run(
                f"""MATCH (t:Transaction)-[:AT_MERCHANT]->(m:Merchant)
                WHERE t.amount < 0 {period_filter}
                RETURN m.normalized_name AS merchant, sum(abs(t.amount)) AS total
                ORDER BY total DESC LIMIT 1""",
                params,
            ).single()
        return {
            "total_in": float(result["total_in"] or 0),
            "total_out": float(result["total_out"] or 0),
            "net": float(result["net"] or 0),
            "transaction_count": result["transaction_count"],
            "top_category": dict(top_cat) if top_cat else None,
            "top_merchant": dict(top_merch) if top_merch else None,
        }

    def get_trends(self, months: int = 6, category: str | None = None) -> list[dict]:
        cat_filter = "AND c.name = $category" if category else ""
        params: dict = {}
        if category:
            params["category"] = category
        with self.driver.session() as session:
            result = session.run(
                f"""MATCH (t:Transaction)-[:IN_PERIOD]->(tp:TimePeriod), (t)-[:IN_CATEGORY]->(c:Category)
                WHERE true {cat_filter}
                WITH tp.label AS month,
                     sum(CASE WHEN t.amount > 0 THEN t.amount ELSE 0 END) AS total_in,
                     sum(CASE WHEN t.amount < 0 THEN abs(t.amount) ELSE 0 END) AS total_out,
                     sum(t.amount) AS net
                RETURN month, total_in, total_out, net
                ORDER BY month DESC LIMIT $months""",
                {**params, "months": months},
            )
            return [dict(r) for r in result]

    def get_categories(
        self, period: str | None = None, account_id: str | None = None
    ) -> list[dict]:
        conditions = ["t.amount < 0"]
        params: dict = {}
        if period:
            conditions.append("t.month = $period")
            params["period"] = period
        if account_id:
            conditions.append("a.id = $account_id")
            params["account_id"] = account_id
        where = " AND ".join(conditions)
        with self.driver.session() as session:
            total_result = session.run(
                f"""MATCH (t:Transaction)-[:FROM_ACCOUNT]->(a:Account) WHERE {where}
                RETURN sum(abs(t.amount)) AS grand_total""",
                params,
            ).single()
            grand_total = float(total_result["grand_total"] or 1)
            result = session.run(
                f"""MATCH (t:Transaction)-[:IN_CATEGORY]->(c:Category), (t)-[:FROM_ACCOUNT]->(a:Account),
                      (t)-[:AT_MERCHANT]->(m:Merchant)
                WHERE {where}
                WITH c.name AS category, m.normalized_name AS merchant,
                     sum(abs(t.amount)) AS merchant_total, count(t) AS txn_count
                ORDER BY merchant_total DESC
                WITH category, sum(merchant_total) AS total, sum(txn_count) AS transaction_count,
                     collect(merchant)[0] AS top_merchant
                RETURN category, round(total, 2) AS total,
                       round(total * 100.0 / $grand_total, 1) AS percentage,
                       transaction_count, top_merchant
                ORDER BY total DESC""",
                {**params, "grand_total": grand_total},
            )
            return [dict(r) for r in result]
