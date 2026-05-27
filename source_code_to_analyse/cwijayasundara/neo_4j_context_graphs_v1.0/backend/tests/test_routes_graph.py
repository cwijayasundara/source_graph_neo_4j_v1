"""Tests for graph visualization routes."""

from neo4j.graph import Graph, Node

from app import routes_graph
from app.main import app


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def run(self, query, parameters=None):
        self.queries.append((query, parameters or {}))
        return self.responses.pop(0)


class FakeDriver:
    def __init__(self, session):
        self._session = session

    def session(self):
        return self._session


def typed_relationship(graph, rel_type, element_id, id_, start_node, end_node):
    rel = graph.relationship_type(rel_type)(graph, element_id, id_, {})
    rel._start_node = start_node
    rel._end_node = end_node
    return rel


def test_finance_overview_returns_connected_graph_and_legacy_results():
    graph = Graph()
    person = Node(graph, "p1", 1, ["Person"], {"name": "Alex"})
    account = Node(graph, "a1", 2, ["Account"], {"id": "ACC1"})
    rel = typed_relationship(graph, "OWNS", "r1", 3, person, account)
    orphan = Node(graph, "s1", 4, ["Statement"], {"id": "STMT1"})
    session = FakeSession([
        [{"source": person, "rel": rel, "target": account}],
        [{"node": person}, {"node": account}, {"node": orphan}],
    ])

    routes_graph.init_graph(FakeDriver(session))

    response = routes_graph.finance_overview()

    assert len(response["nodes"]) == 3
    assert len(response["relationships"]) == 1
    assert len(response["results"]) == 4
    assert {tuple(node["labels"]) for node in response["nodes"]} == {
        ("Person",),
        ("Account",),
        ("Statement",),
    }
    assert response["relationships"][0] == {
        "elementId": "r1",
        "type": "OWNS",
        "startNodeElementId": "p1",
        "endNodeElementId": "a1",
    }


def test_graph_story_returns_preset_slice_with_stats():
    graph = Graph()
    person = Node(graph, "p1", 1, ["Person"], {"name": "Alex"})
    account = Node(graph, "a1", 2, ["Account"], {"id": "ACC1"})
    statement = Node(graph, "s1", 3, ["Statement"], {"id": "STMT1"})
    owns = typed_relationship(graph, "OWNS", "r1", 4, person, account)
    has_statement = typed_relationship(graph, "HAS_STATEMENT", "r2", 5, account, statement)
    session = FakeSession([
        [
            {"source": person, "rel": owns, "target": account},
            {"source": account, "rel": has_statement, "target": statement},
        ],
    ])

    routes_graph.init_graph(FakeDriver(session))

    response = routes_graph.graph_story(preset="overview", limit=10)

    assert response["preset"] == "overview"
    assert len(response["nodes"]) == 3
    assert len(response["relationships"]) == 2
    assert len(response["results"]) == 5
    assert response["stats"] == {
        "nodes": 3,
        "relationships": 2,
        "people": 1,
        "accounts": 1,
        "statements": 1,
        "transactions": 0,
        "merchants": 0,
        "categories": 0,
        "time_periods": 0,
    }


def test_finance_overview_route_precedes_generic_graph_entity_route():
    paths = [
        route.path
        for route in app.routes
        if getattr(route, "path", "") in {
            "/api/graph/finance-overview",
            "/api/graph/story",
            "/api/graph/{entity_name}",
        }
    ]

    assert paths.index("/api/graph/finance-overview") < paths.index("/api/graph/{entity_name}")
    assert paths.index("/api/graph/story") < paths.index("/api/graph/{entity_name}")
