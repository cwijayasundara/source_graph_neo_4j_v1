"""Graph schema introspection tool."""

import json
from neo4j import Driver


def make_get_graph_schema(driver: Driver):
    """Create a function that returns the graph schema."""

    def get_graph_schema() -> str:
        """Return the graph schema: node labels, relationship types, property keys, and category hierarchy."""
        with driver.session() as session:
            labels = session.run(
                "CALL db.labels() YIELD label RETURN collect(label) AS labels"
            )
            label_list = labels.single()["labels"]

            rels = session.run(
                "CALL db.relationshipTypes() YIELD relationshipType "
                "RETURN collect(relationshipType) AS types"
            )
            rel_list = rels.single()["types"]

            cats = session.run(
                "MATCH (c:Category) "
                "OPTIONAL MATCH (c)-[:SUBCATEGORY_OF]->(parent:Category) "
                "RETURN c.name AS category, parent.name AS parent_category "
                "ORDER BY parent_category, category"
            )
            category_hierarchy = [
                {"name": r["category"], "parent": r["parent_category"]}
                for r in cats
            ]

        return json.dumps(
            {
                "node_labels": label_list,
                "relationship_types": rel_list,
                "category_hierarchy": category_hierarchy,
                "notes": (
                    "Transactions have: id, date, amount, balance, raw_description, "
                    "payment_method, year, month. Merchants have: normalized_name. "
                    "Use IN_PERIOD to filter by time. Negative amounts are expenses, "
                    "positive are income."
                ),
            },
            indent=2,
        )

    return get_graph_schema
