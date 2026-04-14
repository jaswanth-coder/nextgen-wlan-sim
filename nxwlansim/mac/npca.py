"""
NPCAEngine — Non-Primary Channel Access per IEEE 802.11be §35.3.3.
Preamble puncturing, per-subchannel NAV, coordinated secondary-channel access.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nxwlansim.core.engine import SimulationEngine
    from nxwlansim.core.node import Node

logger = logging.getLogger(__name__)

N_SUBCHANNELS = 4       # 4 × 80 MHz = 320 MHz total
SUBCHANNEL_BW = 80      # MHz per subchannel
_ALL_MASK = (1 << N_SUBCHANNELS) - 1   # 0b1111


@dataclass
class NPCADecision:
    use_npca: bool
    free_mask: int          # bitmask: bit i set if subchannel i is free
    punctured_mask: int     # bitmask: bit i set if subchannel i is punctured
    effective_bw_mhz: float
    total_bw_mhz: float = float(N_SUBCHANNELS * SUBCHANNEL_BW)


class NPCAEngine:
    """Per-node NPCA controller. One instance per node, attached by builder."""

    def __init__(self, node: "Node"):
        self.node = node

    def evaluate(self, link_id: str, now_ns: int) -> NPCADecision:
        """
        Decide whether to use NPCA on link_id.
        Primary subchannel = index 0.
        Returns NPCADecision with puncturing info.
        """
        ctx = self.node.mlo_manager.links.get(link_id)
        if ctx is None:
            return NPCADecision(use_npca=False, free_mask=_ALL_MASK,
                                punctured_mask=0,
                                effective_bw_mhz=N_SUBCHANNELS * SUBCHANNEL_BW)

        free = ctx.free_subchannels(now_ns, N_SUBCHANNELS)
        free_mask = sum(1 << i for i in free)
        primary_free = 0 in free

        if primary_free:
            return NPCADecision(use_npca=False, free_mask=free_mask,
                                punctured_mask=0,
                                effective_bw_mhz=N_SUBCHANNELS * SUBCHANNEL_BW)

        # Primary busy — try secondary subchannels
        secondary_free = [i for i in free if i != 0]
        if not secondary_free:
            return NPCADecision(use_npca=False, free_mask=0,
                                punctured_mask=_ALL_MASK, effective_bw_mhz=0.0)

        punctured = _ALL_MASK & ~free_mask   # busy subchannels are punctured
        eff_bw = float(len(secondary_free) * SUBCHANNEL_BW)
        logger.debug("[NPCA] %s link=%s primary=BUSY secondaries=%s bw=%.0fMHz",
                     self.node.node_id, link_id, secondary_free, eff_bw)
        return NPCADecision(use_npca=True, free_mask=free_mask,
                            punctured_mask=punctured, effective_bw_mhz=eff_bw)

    def coordinate(self, link_id: str, duration_ns: int,
                   engine: "SimulationEngine") -> None:
        """
        Propagate secondary subchannel NAV to all neighbours.
        Prevents collision on secondary channels from other STAs.
        """
        if not engine._registry:
            return
        for other in engine._registry:
            if other.node_id == self.node.node_id:
                continue
            ctx = other.mlo_manager.links.get(link_id)
            if ctx is None:
                continue
            for sc in range(1, N_SUBCHANNELS):   # secondary subchannels only
                ctx.set_sub_nav(sc, duration_ns, engine.now_ns)
