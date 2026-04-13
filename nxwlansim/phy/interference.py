"""
InterferenceTracker — tracks simultaneous active transmissions per link.
Used by TGbeChannel to compute SINR instead of raw SNR when
multiple nodes are transmitting on the same link at the same time.

Model:
  SINR = signal_power - 10*log10( noise_power + sum(interferer_powers) )

Each active TX is registered with its tx_power_dbm, start_ns, end_ns.
Any overlapping TX on the same link contributes interference.
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class ActiveTX:
    node_id: str
    link_id: str
    tx_power_dbm: float
    start_ns: int
    end_ns: int
    dst_id: str


class InterferenceTracker:
    """
    Global singleton per simulation.
    Tracks all currently active transmissions.
    """

    def __init__(self):
        self._active: list[ActiveTX] = []

    def register_tx(
        self,
        node_id: str,
        link_id: str,
        tx_power_dbm: float,
        start_ns: int,
        end_ns: int,
        dst_id: str,
    ) -> None:
        self._active.append(ActiveTX(
            node_id=node_id, link_id=link_id,
            tx_power_dbm=tx_power_dbm,
            start_ns=start_ns, end_ns=end_ns,
            dst_id=dst_id,
        ))
        # Prune completed TXs
        self._active = [tx for tx in self._active if tx.end_ns > start_ns]

    def get_interference_dbm(
        self,
        link_id: str,
        now_ns: int,
        exclude_node_id: str,
        dst_id: str,
        positions: dict[str, tuple],
    ) -> float:
        """
        Compute aggregate interference power (dBm) at dst_id on link_id
        from all active transmitters except exclude_node_id.
        """
        interferers = [
            tx for tx in self._active
            if (
                tx.link_id == link_id
                and tx.node_id != exclude_node_id
                and tx.start_ns <= now_ns <= tx.end_ns
            )
        ]
        if not interferers:
            return -200.0   # effectively zero interference

        total_interference_mw = 0.0
        dst_pos = positions.get(dst_id, (0.0, 0.0))

        for tx in interferers:
            src_pos = positions.get(tx.node_id, (0.0, 0.0))
            dist_m = max(math.dist(src_pos, dst_pos), 0.1)
            # Free-space path loss for interferer
            path_loss = 20 * math.log10(dist_m) + 20 * math.log10(6.2e9) - 147.55
            rx_power_dbm = tx.tx_power_dbm - path_loss
            total_interference_mw += 10 ** (rx_power_dbm / 10)

        if total_interference_mw <= 0:
            return -200.0
        return 10 * math.log10(total_interference_mw)

    def clear_expired(self, now_ns: int) -> None:
        self._active = [tx for tx in self._active if tx.end_ns > now_ns]


# Module-level singleton — shared across all PHY instances in a simulation
_tracker = InterferenceTracker()


def get_tracker() -> InterferenceTracker:
    return _tracker


def reset_tracker() -> None:
    """Call between simulations to clear state."""
    global _tracker
    _tracker = InterferenceTracker()
