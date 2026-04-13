"""
PCAPHook — integrates PCAPWriter into the TXOPEngine event flow.
Installed per-node by builder when obs.pcap=True.
Captures every A-MPDU transmission as a radiotap/802.11 PCAP record.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nxwlansim.core.engine import SimulationEngine
    from nxwlansim.mac.ampdu import AMPDUFrame
    from nxwlansim.phy.base import TxResult, ChannelState
    from nxwlansim.observe.pcap import PCAPWriter

logger = logging.getLogger(__name__)


class PCAPHook:
    """
    Attached to each node. Called by TXOPEngine after PHY TX completes.
    Writes one PCAP record per subframe in the A-MPDU.
    """

    def __init__(self, node_id: str, writer: "PCAPWriter"):
        self.node_id = node_id
        self._writer = writer

    def on_tx_complete(
        self,
        ampdu: "AMPDUFrame",
        tx_result: "TxResult",
        channel: "ChannelState",
        timestamp_ns: int,
    ) -> None:
        """Write each subframe of an A-MPDU to PCAP."""
        for subframe in ampdu.subframes:
            try:
                self._writer.write_frame(
                    frame=subframe,
                    tx_result=tx_result,
                    timestamp_ns=timestamp_ns,
                )
            except Exception as e:
                logger.warning("[PCAP] Write failed for %s: %s", self.node_id, e)
