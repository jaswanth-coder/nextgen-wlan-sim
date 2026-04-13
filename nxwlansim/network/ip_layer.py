"""
IPLayer — multi-AP IP network mode.
Static routing table, UDP/TCP traffic sources, ideal wired DS.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nxwlansim.core.registry import NodeRegistry


class IPLayer:
    """
    Simple static-routing IP layer over multiple BSSs.
    DS (Distribution System) is modeled as zero-latency ideal backhaul.
    """

    def __init__(self, registry: "NodeRegistry"):
        self._registry = registry
        self._routes: dict[str, str] = {}   # dst_node_id → gateway_ap_id

    def add_route(self, dst_id: str, via_ap_id: str) -> None:
        self._routes[dst_id] = via_ap_id

    def build_default_routes(self) -> None:
        """Auto-build: each STA routes via its associated AP."""
        for sta in self._registry.stas():
            if sta.associated_ap:
                self._routes[sta.node_id] = sta.associated_ap

    def route(self, src_id: str, dst_id: str) -> list[str]:
        """Return hop list for src→dst."""
        if dst_id in self._routes:
            gw = self._routes[dst_id]
            return [src_id, gw, dst_id]
        return [src_id, dst_id]
