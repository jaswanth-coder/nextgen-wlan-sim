"""
Node hierarchy: Node → APNode / STANode
Each node owns a MLOLinkManager and an EDCAScheduler.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nxwlansim.core.engine import SimulationEngine
    from nxwlansim.core.config import NodeConfig


class Node:
    """Base class for all network nodes (AP or STA)."""

    def __init__(self, config: "NodeConfig"):
        self.node_id: str = config.id
        self.node_type: str = config.type
        self.links: list[str] = config.links
        self.mlo_mode: str = config.mlo_mode
        self.position: tuple[float, float] = tuple(config.position)
        self.mac_address: str = _generate_mac(config.id)

        # Attached after engine build
        self._engine: "SimulationEngine | None" = None
        self.mlo_manager = None      # set by builder: MLOLinkManager
        self.edca_scheduler = None   # set by builder: EDCAScheduler
        self.txop_engine = None      # set by builder: TXOPEngine
        self.rx_processor = None     # set by builder: RXProcessor
        self.phy = None              # set by builder: PhyAbstraction instance

    def attach(self, engine: "SimulationEngine") -> None:
        self._engine = engine

    def __repr__(self) -> str:
        return f"<{self.node_type.upper()} id={self.node_id} links={self.links} mlo={self.mlo_mode}>"


class APNode(Node):
    """Access Point node."""

    def __init__(self, config: "NodeConfig"):
        super().__init__(config)
        self.associated_stas: list[str] = []

    def associate(self, sta_id: str) -> None:
        if sta_id not in self.associated_stas:
            self.associated_stas.append(sta_id)


class STANode(Node):
    """Station node."""

    def __init__(self, config: "NodeConfig"):
        super().__init__(config)
        self.emlsr_transition_delay_ns: int = config.emlsr_transition_delay_us * 1_000
        self.emlmr_n_radios: int = config.emlmr_n_radios
        self.associated_ap: str | None = None


def _generate_mac(node_id: str) -> str:
    """Deterministic MAC address from node_id string."""
    h = hash(node_id) & 0xFFFFFFFFFFFF
    b = h.to_bytes(6, "big")
    return ":".join(f"{x:02x}" for x in b)
