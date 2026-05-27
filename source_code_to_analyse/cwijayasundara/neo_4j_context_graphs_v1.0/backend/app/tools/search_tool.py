"""Fuzzy merchant search tool."""

import json
from neo4j import Driver


def make_search_merchants(driver: Driver):
    """Create a fuzzy merchant search function bound to *driver*."""

    def search_merchants(name: str) -> str:
        """Fuzzy search for a merchant by name.

        Returns matching merchant nodes with their categories.
        """
        with driver.session() as session:
            result = session.run(
                "MATCH (m:Merchant) "
                "WHERE toLower(m.normalized_name) CONTAINS toLower($name) "
                "   OR toLower(m.name) CONTAINS toLower($name) "
                "OPTIONAL MATCH (m)-[:BELONGS_TO]->(c:Category) "
                "RETURN m.normalized_name AS merchant, c.name AS category "
                "LIMIT 10",
                name=name,
            )
            matches = [
                {"merchant": r["merchant"], "category": r["category"]}
                for r in result
            ]

        if not matches:
            return json.dumps({"message": f"No merchants found matching '{name}'"})
        return json.dumps(matches)

    return search_merchants
