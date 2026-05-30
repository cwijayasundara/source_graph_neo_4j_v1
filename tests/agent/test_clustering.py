from __future__ import annotations

from code_context_graph.agent.clustering import Subsystem, detect_subsystems


def test_two_disconnected_groups_become_two_subsystems():
    nodes = ["a1", "a2", "b1", "b2"]
    edges = [("a1", "a2"), ("b1", "b2")]
    subs = detect_subsystems(nodes, edges, max_clusters=12)
    assert len(subs) == 2
    members = sorted(sorted(s.members) for s in subs)
    assert members == [["a1", "a2"], ["b1", "b2"]]


def test_connected_component_is_one_subsystem():
    nodes = ["a", "b", "c"]
    edges = [("a", "b"), ("b", "c")]
    subs = detect_subsystems(nodes, edges, max_clusters=12)
    assert len(subs) == 1
    assert sorted(subs[0].members) == ["a", "b", "c"]


def test_isolated_node_is_its_own_subsystem():
    subs = detect_subsystems(["solo"], [], max_clusters=12)
    assert len(subs) == 1 and subs[0].members == ["solo"]


def test_merges_down_to_cap_keeping_largest():
    # 5 singletons, cap of 3 -> 2 largest kept singleton + remainder merged = <=3
    nodes = ["a", "b", "c", "d", "e"]
    subs = detect_subsystems(nodes, [], max_clusters=3)
    assert len(subs) <= 3
    # every original node still appears exactly once
    all_members = sorted(m for s in subs for m in s.members)
    assert all_members == ["a", "b", "c", "d", "e"]


def test_subsystem_has_a_stable_name():
    subs = detect_subsystems(["pkg.aaa", "pkg.aab"], [("pkg.aaa", "pkg.aab")], max_clusters=12)
    assert isinstance(subs[0].name, str) and subs[0].name


from code_context_graph.agent.deps import GraphDeps
from code_context_graph.agent import graph_ops as ops


def test_list_subsystems_op_pulls_and_clusters(seeded, tmp_path):
    seeded.when(lambda q, p: "RETURN e.qualified_name AS qn" in q,
                [{"qn": "a"}, {"qn": "b"}, {"qn": "c"}])
    seeded.when(lambda q, p: "RETURN a.qualified_name AS src" in q,
                [{"src": "a", "dst": "b"}])
    deps = GraphDeps(client=seeded, repo_id="r", repo_path=tmp_path)
    out = ops.list_subsystems(deps, max_clusters=12)
    names = sorted(sorted(s["members"]) for s in out["subsystems"])
    assert names == [["a", "b"], ["c"]]
