"""
TXOP Execution Engine — connects MAC state machine to DES event loop.

Flow per link per node:
  schedule_backoff_start()
    → _tick_backoff() every SLOT_NS (if channel idle & NAV clear)
      → backoff hits 0 → _attempt_txop()
        → check channel idle → TXOP_GRANTED
          → _transmit_ampdu()
            → PHY.request_tx() → schedule PHY_RESPONSE event
              → _on_phy_complete()
                → schedule BA_TIMEOUT or immediate BA
                  → _on_ba_received() / _on_ba_timeout()
                    → success: txop_success(), reschedule backoff
                    → fail:    collision(), reschedule backoff
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from nxwlansim.core.engine import MAC_DECISION, PHY_COMPLETE, TRAFFIC_GEN
from nxwlansim.mac.frame import (
    MPDUFrame, AMPDUFrame, SLOT_NS, SIFS_NS, DIFS_NS, aifs_ns
)
from nxwlansim.mac.mlo import LinkState
from nxwlansim.mac.ampdu import AmpduAggregator

if TYPE_CHECKING:
    from nxwlansim.core.engine import SimulationEngine
    from nxwlansim.core.node import Node
    from nxwlansim.mac.mlo import LinkContext
    from nxwlansim.mac.edca import ACQueue

logger = logging.getLogger(__name__)

# Default TXOP limits per AC (µs → ns); 0 = one A-MPDU per TXOP
_TXOP_LIMIT_NS = {
    "VO": 2_528_000,
    "VI": 4_096_000,
    "BE": 0,
    "BK": 0,
}
_DEFAULT_TXOP_NS = 5_484_000   # fallback max TXOP (5.484 ms)


class TXOPEngine:
    """
    Per-node TXOP execution engine.
    One TXOPEngine owns all links of a node and coordinates across them.
    """

    def __init__(self, node: "Node", engine: "SimulationEngine"):
        self.node = node
        self.engine = engine
        self.aggregator = AmpduAggregator(node, engine)
        # Track in-flight A-MPDUs awaiting BA: link_id → AMPDUFrame
        self._inflight: dict[str, AMPDUFrame] = {}

    # ------------------------------------------------------------------
    # Entry point — called once per link at sim start by builder
    # ------------------------------------------------------------------

    def start_link(self, link_id: str) -> None:
        """Bootstrap backoff process for a link."""
        self.engine.schedule_after(
            delay_ns=DIFS_NS,
            callback=self._tick_backoff,
            priority=MAC_DECISION,
            link_id=link_id,
        )

    # ------------------------------------------------------------------
    # Backoff countdown
    # ------------------------------------------------------------------

    def _tick_backoff(self, engine: "SimulationEngine", link_id: str, **_) -> None:
        ctx = self.node.mlo_manager.get_link(link_id)

        # Skip if link is transmitting or EMLSR-frozen
        if ctx.state in (LinkState.TRANSMITTING, LinkState.WAIT_BA, LinkState.TXOP_GRANTED):
            return

        # Check NAV / medium busy
        if ctx.is_nav_busy(engine.now_ns):
            # Re-schedule check after NAV clears
            engine.schedule_after(
                delay_ns=ctx.nav_expiry_ns - engine.now_ns + SLOT_NS,
                callback=self._tick_backoff,
                priority=MAC_DECISION,
                link_id=link_id,
            )
            return

        # EMLSR: only tick if this is the active link
        if self.node.mlo_mode == "emlsr":
            active = self.node.mlo_manager._emlsr_active_link
            if active is not None and active != link_id:
                return   # frozen

        # Decrement backoff on the highest-priority non-empty AC
        sched = self.node.edca_scheduler
        for ac_name in ("VO", "VI", "BE", "BK"):
            q = sched.queues[ac_name]
            if not q.empty and not q.frozen:
                remaining = q.decrement_backoff()
                if remaining == 0:
                    self._attempt_txop(engine, link_id, q)
                    return
                break   # only decrement one AC per slot

        # No ready AC or backoff > 0 — schedule next slot
        engine.schedule_after(
            delay_ns=SLOT_NS,
            callback=self._tick_backoff,
            priority=MAC_DECISION,
            link_id=link_id,
        )

    # ------------------------------------------------------------------
    # TXOP acquisition
    # ------------------------------------------------------------------

    def _attempt_txop(
        self,
        engine: "SimulationEngine",
        link_id: str,
        queue: "ACQueue",
    ) -> None:
        ctx = self.node.mlo_manager.get_link(link_id)

        # Final channel-idle check
        if ctx.is_nav_busy(engine.now_ns):
            queue.collision()
            engine.schedule_after(
                delay_ns=DIFS_NS,
                callback=self._tick_backoff,
                priority=MAC_DECISION,
                link_id=link_id,
            )
            return

        # Grant TXOP
        if self.node.mlo_mode == "str":
            self.node.mlo_manager.str_txop_granted(link_id)
        elif self.node.mlo_mode == "emlsr":
            self.node.mlo_manager.emlsr_trigger(link_id)
            return   # EMLSR will call back after transition delay
        # EMLMR handled by MLOLinkManager policy
        ctx.state = LinkState.TXOP_GRANTED

        txop_limit_ns = _TXOP_LIMIT_NS.get(queue.ac, 0) or _DEFAULT_TXOP_NS
        ctx.txop_end_ns = engine.now_ns + txop_limit_ns

        logger.debug(
            "[TXOP] %s granted on %s ac=%s txop=%.2f ms",
            self.node.node_id, link_id, queue.ac, txop_limit_ns / 1e6,
        )
        self._transmit_ampdu(engine, link_id, queue)

    # ------------------------------------------------------------------
    # Transmission
    # ------------------------------------------------------------------

    def _transmit_ampdu(
        self,
        engine: "SimulationEngine",
        link_id: str,
        queue: "ACQueue",
    ) -> None:
        ctx = self.node.mlo_manager.get_link(link_id)
        if ctx.state != LinkState.TXOP_GRANTED:
            return

        frames = []
        while not queue.empty:
            frames.append(queue.peek())
            if len(frames) >= 256:
                break
            queue.dequeue()

        if not frames:
            ctx.state = LinkState.IDLE
            self._restart_backoff(engine, link_id)
            return

        # Get channel state for MCS
        dst = frames[0].dst
        ch = self.node.phy.get_channel_state(self.node.node_id, dst, link_id)

        txop_remaining = max(0, ctx.txop_end_ns - engine.now_ns)
        ampdu = self.aggregator.build_ampdu(
            frames, link_id,
            txop_remaining_ns=txop_remaining,
            mcs=ch.mcs_index,
            bandwidth_mhz=ch.bandwidth_mhz,
        )

        # Put back frames that didn't fit
        not_sent = frames[ampdu.n_subframes:]
        for f in reversed(not_sent):
            queue._queue.insert(0, f)

        ctx.state = LinkState.TRANSMITTING
        self._inflight[link_id] = ampdu

        # Request PHY TX
        tx_result = self.node.phy.request_tx(frames[0], ctx)

        # Set NAV on other nodes (simplified: only self for now)
        nav_duration = tx_result.duration_ns + SIFS_NS

        logger.debug(
            "[TX] %s link=%s n_frames=%d mcs=%d bw=%d dur=%.1f µs",
            self.node.node_id, link_id, ampdu.n_subframes,
            tx_result.mcs_used, ch.bandwidth_mhz,
            tx_result.duration_ns / 1_000,
        )

        # Schedule PHY complete event
        engine.schedule_after(
            delay_ns=tx_result.duration_ns,
            callback=self._on_phy_complete,
            priority=PHY_COMPLETE,
            link_id=link_id,
            tx_result=tx_result,
            dst=dst,
        )

    def _on_phy_complete(
        self,
        engine: "SimulationEngine",
        link_id: str,
        tx_result,
        dst: str,
        **_,
    ) -> None:
        ctx = self.node.mlo_manager.get_link(link_id)
        ctx.state = LinkState.WAIT_BA

        # Simulate BA reception after SIFS
        engine.schedule_after(
            delay_ns=SIFS_NS,
            callback=self._on_ba_received,
            priority=PHY_COMPLETE,
            link_id=link_id,
            success=True,   # simplified: assume BA success for Phase 1
        )

        # Also schedule BA timeout as safety net
        from nxwlansim.mac.ampdu import BA_TIMEOUT_NS
        engine.schedule_after(
            delay_ns=BA_TIMEOUT_NS,
            callback=self._on_ba_timeout,
            priority=MAC_DECISION,
            link_id=link_id,
        )

    def _on_ba_received(
        self,
        engine: "SimulationEngine",
        link_id: str,
        success: bool,
        **_,
    ) -> None:
        ctx = self.node.mlo_manager.get_link(link_id)
        if ctx.state != LinkState.WAIT_BA:
            return   # timeout already fired

        ctx.state = LinkState.IDLE
        ampdu = self._inflight.pop(link_id, None)

        sched = self.node.edca_scheduler
        for ac_name in ("VO", "VI", "BE", "BK"):
            q = sched.queues[ac_name]
            if success:
                q.txop_success()
            else:
                q.collision()
            break

        if self.node.mlo_mode == "emlsr":
            self.node.mlo_manager.emlsr_release()

        logger.debug(
            "[BA] %s link=%s success=%s frames=%d",
            self.node.node_id, link_id, success,
            ampdu.n_subframes if ampdu else 0,
        )
        self._restart_backoff(engine, link_id)

    def _on_ba_timeout(
        self,
        engine: "SimulationEngine",
        link_id: str,
        **_,
    ) -> None:
        ctx = self.node.mlo_manager.get_link(link_id)
        if ctx.state != LinkState.WAIT_BA:
            return   # BA already received

        ctx.state = LinkState.IDLE
        self._inflight.pop(link_id, None)

        # Mark collision on all ACs
        for q in self.node.edca_scheduler.queues.values():
            q.collision()

        logger.warning(
            "[BA-TIMEOUT] %s link=%s — retransmitting", self.node.node_id, link_id
        )
        self._restart_backoff(engine, link_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _restart_backoff(self, engine: "SimulationEngine", link_id: str) -> None:
        engine.schedule_after(
            delay_ns=DIFS_NS,
            callback=self._tick_backoff,
            priority=MAC_DECISION,
            link_id=link_id,
        )
