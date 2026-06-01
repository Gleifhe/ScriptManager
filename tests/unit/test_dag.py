"""Unit tests for the DAG model."""
from __future__ import annotations

import pytest

from scriptmgr.workflows.dag import Dag, DagEdge, DagNode


def _dag(*edges: tuple[str, str, str]) -> Dag:
    node_ids = {nid for pair in edges for nid in pair[:2]}
    # assign fake script_ids
    nodes = [DagNode(id=nid, script_id=i + 1) for i, nid in enumerate(sorted(node_ids))]
    dag_edges = [DagEdge(from_node=f, to_node=t, on=on) for f, t, on in edges]
    return Dag(nodes=nodes, edges=dag_edges)


def test_roots_no_edges():
    dag = Dag(nodes=[DagNode(id="a", script_id=1), DagNode(id="b", script_id=2)], edges=[])
    assert {n.id for n in dag.roots()} == {"a", "b"}


def test_roots_linear_chain():
    dag = _dag(("a", "b", "success"), ("b", "c", "success"))
    assert [n.id for n in dag.roots()] == ["a"]


def test_successors_success():
    dag = _dag(("a", "b", "success"), ("a", "c", "failure"))
    succ = [n.id for n in dag.successors("a", "success")]
    assert "b" in succ
    assert "c" not in succ


def test_successors_failure():
    dag = _dag(("a", "b", "success"), ("a", "c", "failure"))
    succ = [n.id for n in dag.successors("a", "failure")]
    assert "c" in succ
    assert "b" not in succ


def test_successors_always():
    dag = _dag(("a", "b", "always"))
    assert [n.id for n in dag.successors("a", "success")] == ["b"]
    assert [n.id for n in dag.successors("a", "failure")] == ["b"]


def test_predecessors():
    dag = _dag(("a", "c", "success"), ("b", "c", "success"))
    preds = set(dag.predecessors("c"))
    assert preds == {"a", "b"}


def test_from_dict():
    d = {
        "nodes": [{"id": "n1", "script_id": 10}, {"id": "n2", "script_id": 11}],
        "edges": [{"from": "n1", "to": "n2", "on": "success"}],
    }
    dag = Dag.from_dict(d)
    assert len(dag.nodes) == 2
    assert dag.edges[0].from_node == "n1"
    assert dag.edges[0].on == "success"
