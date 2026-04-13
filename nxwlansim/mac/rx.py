"""
RX Path — destination node receives A-MPDU, scores BA bitmap, sends BA frame.

Flow:
  TXOPEngine._on_phy_complete()
    → schedules RXProcessor.receive() on destination node after prop_delay
      → PHY.request_rx() → per-subframe success/fail
        → update BA scoreboard
        → schedule BA_RESPONSE event back to sender after SIFS
          → sender TXOPEngine._on_ba_received(success=True/False)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from nxwlansim.core.engine import PHY_COMPLETE, MAC_DECISION
from nxwlansim.mac.frame import SIFS_NS
from nxwlansim.mac.mlo import LinkState

if TYPE_CHECKING:
    from nxwlansim.core.engine import SimulationEngine
    from nxwlansim.core.node import Node
    from nxwlansim.mac.ampdu import AMPDUFrame, BlockAckSession
    from nxwlansim.phy.base import ChannelState

logger = logging.getLogger(__name__)

# Propagation delay model: 1 ns per 30 cm (speed of light), min 1 ns
_PROP_SPEED_NS_PER_M = 3.336   # ~1/c in ns/m


def prop_delay_ns(dist_m: float) -> int:
    return max(1, int(dist_m * _PROP_SPEED_NS_PER_M))


class RXProcessor:
    """
    Per-node receive processor.
    Installed on every node by the builder.
    """

    def __init__(self, node: "Node", engine: "SimulationEngine"):
        self.node = node
        self.engine = engine
        # BA scoreboards keyed by (src_mac, tid, link_id) for received sessions
        self._rx_sessions: dict[tuple, "BlockAckSession"] = {}
        # Reorder buffer: (src_mac, tid) → {seq: frame}
        self._reorder: dict[tuple, dict] = {}

    # ------------------------------------------------------------------
    # Called by sender's TXOPEngine after PHY TX completes
    # ------------------------------------------------------------------

    def schedule_receive(
        self,
        ampdu: "AMPDUFrame",
        channel: "ChannelState",
        sender_id: str,
        dist_m: float,
    ) -> None:
        """Schedule receive event on this node after propagation delay."""
        delay = prop_delay_ns(dist_m)
        self.engine.schedule_after(
            delay_ns=delay,
            callback=self._receive,
            priority=PHY_COMPLETE,
            ampdu=ampdu,
            channel=channel,
            sender_id=sender_id,
        )

    def _receive(
        self,
        engine: "SimulationEngine",
        ampdu: "AMPDUFrame",
        channel: "ChannelState",
        sender_id: str,
        **_,
    ) -> None:
        """Process received A-MPDU: score each subframe, build BA bitmap."""
        link_id = ampdu.link_id

        # Set NAV from received PPDU duration (virtual carrier sense)
        ctx = self.node.mlo_manager.links.get(link_id)
        if ctx:
            ctx.set_nav(duration_ns=SIFS_NS * 2, now_ns=engine.now_ns)

        received_seqs = []
        failed_seqs = []
        total_bytes = 0

        for subframe in ampdu.subframes:
            rx_result = self.node.phy.request_rx(subframe, channel)
            if rx_result.success:
                received_seqs.append(subframe.seq_num)
                total_bytes += subframe.size_bytes
                self._buffer_msdu(sender_id, subframe.tid, subframe)
            else:
                failed_seqs.append(subframe.seq_num)

        # Update BA scoreboard
        key = (sender_id, ampdu.subframes[0].tid if ampdu.subframes else 0, link_id)
        session = self._get_rx_session(sender_id, key[1], link_id)
        for seq in received_seqs:
            session.mark_received(seq)
        session.advance_window()

        success_rate = len(received_seqs) / max(len(ampdu.subframes), 1)
        overall_success = success_rate >= 0.5   # BA success if >50% subframes received

        logger.debug(
            "[RX] %s ← %s link=%s rx=%d/%d bytes=%d",
            self.node.node_id, sender_id, link_id,
            len(received_seqs), len(ampdu.subframes), total_bytes,
        )

        # Send BA back to sender after SIFS
        engine.schedule_after(
            delay_ns=SIFS_NS,
            callback=self._send_ba,
            priority=PHY_COMPLETE,
            sender_id=sender_id,
            link_id=link_id,
            success=overall_success,
            received_seqs=received_seqs,
        )

    def _send_ba(
        self,
        engine: "SimulationEngine",
        sender_id: str,
        link_id: str,
        success: bool,
        received_seqs: list,
        **_,
    ) -> None:
        """Deliver BA result back to sender's TXOPEngine."""
        try:
            sender = engine._registry.get(sender_id)
        except KeyError:
            return

        # Deliver to sender's TXOPEngine
        engine.schedule_after(
            delay_ns=prop_delay_ns(10),   # small BA frame propagation
            callback=sender.txop_engine._on_ba_received,
            priority=PHY_COMPLETE,
            link_id=link_id,
            success=success,
        )

    # ------------------------------------------------------------------
    # Reorder buffer (simplified — delivers in-order MSDUs)
    # ------------------------------------------------------------------

    def _buffer_msdu(self, src_id: str, tid: int, frame) -> None:
        key = (src_id, tid)
        if key not in self._reorder:
            self._reorder[key] = {}
        self._reorder[key][frame.seq_num] = frame

    def _get_rx_session(self, src_id: str, tid: int, link_id: str) -> "BlockAckSession":
        from nxwlansim.mac.ampdu import BlockAckSession
        key = (src_id, tid, link_id)
        if key not in self._rx_sessions:
            self._rx_sessions[key] = BlockAckSession(
                peer_mac=src_id, tid=tid, link_id=link_id
            )
        return self._rx_sessions[key]

    @property
    def total_bytes_received(self) -> int:
        return sum(
            f.size_bytes
            for buf in self._reorder.values()
            for f in buf.values()
        )
