"""NodeRegistry — central lookup for all nodes in the simulation."""

from __future__ import annotations
from typing import Iterator
from nxwlansim.core.node import Node, APNode, STANode


class NodeRegistry:
    def __init__(self):
        self._nodes: dict[str, Node] = {}

    def register(self, node: Node) -> None:
        if node.node_id in self._nodes:
            raise ValueError(f"Duplicate node id: {node.node_id}")
        self._nodes[node.node_id] = node

    def get(self, node_id: str) -> Node:
        return self._nodes[node_id]

    def aps(self) -> list[APNode]:
        return [n for n in self._nodes.values() if isinstance(n, APNode)]

    def stas(self) -> list[STANode]:
        return [n for n in self._nodes.values() if isinstance(n, STANode)]

    @property
    def nodes(self) -> list[Node]:
        return list(self._nodes.values())

    def __iter__(self) -> Iterator[Node]:
        return iter(self._nodes.values())

    def __len__(self) -> int:
        return len(self._nodes)
