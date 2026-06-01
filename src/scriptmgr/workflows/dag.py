"""DAG model: nodes, edges, traversal helpers."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class DagNode(BaseModel):
    id: str
    script_id: int
    retry: int = 0
    timeout_sec: int = 0
    label: str = ""


class DagEdge(BaseModel):
    from_node: str
    to_node: str
    on: Literal["success", "failure", "always"] = "success"


class Dag(BaseModel):
    nodes: list[DagNode]
    edges: list[DagEdge]

    @property
    def _node_map(self) -> dict[str, DagNode]:
        return {n.id: n for n in self.nodes}

    def roots(self) -> list[DagNode]:
        """Nodes with no incoming edges (entry points of the DAG)."""
        targets = {e.to_node for e in self.edges}
        return [n for n in self.nodes if n.id not in targets]

    def successors(
        self, node_id: str, outcome: Literal["success", "failure"]
    ) -> list[DagNode]:
        """Return nodes reachable from *node_id* given *outcome*."""
        nm = self._node_map
        return [
            nm[e.to_node]
            for e in self.edges
            if e.from_node == node_id and e.on in (outcome, "always") and e.to_node in nm
        ]

    def predecessors(self, node_id: str) -> list[str]:
        return [e.from_node for e in self.edges if e.to_node == node_id]

    @classmethod
    def from_dict(cls, d: dict) -> "Dag":
        nodes = [DagNode(**n) for n in d.get("nodes", [])]
        edges = [
            DagEdge(from_node=e["from"], to_node=e["to"], on=e.get("on", "success"))
            for e in d.get("edges", [])
        ]
        return cls(nodes=nodes, edges=edges)
