"""
MLO Link Manager — IEEE 802.11be §35.3.4/5/6
Manages LinkContext state machines for STR, EMLSR, EMLMR.
"""

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nxwlansim.core.engine import SimulationEngine
    from nxwlansim.core.node import Node

from nxwlansim.core.engine import MAC_DECISION, PHY_COMPLETE

logger = logging.getLogger(__name__)


class LinkState(Enum):
    IDLE         = auto()
    BACKOFF      = auto()
    TXOP_GRANTED = auto()
    TRANSMITTING = auto()
    WAIT_BA      = auto()


class LinkContext:
    """Per-link state for one radio band (2g / 5g / 6g)."""

    def __init__(self, link_id: str, node: "Node"):
        self.link_id = link_id
        self.node = node
        self.state = LinkState.IDLE
        self.nav_expiry_ns: int = 0       # NAV expiry timestamp
        self.txop_end_ns: int = 0         # TXOP end timestamp
        self.current_frame = None         # frame currently in flight
        self.ba_session = None            # BlockAckSession — set by AmpduAggregator

    def is_nav_busy(self, now_ns: int) -> bool:
        return now_ns < self.nav_expiry_ns

    def set_nav(self, duration_ns: int, now_ns: int) -> None:
        self.nav_expiry_ns = max(self.nav_expiry_ns, now_ns + duration_ns)

    def __repr__(self) -> str:
        return f"<LinkContext {self.link_id} state={self.state.name}>"


class LinkSelectionPolicy:
    """Base class for EMLMR link selection policies."""
    def select(self, contexts: list[LinkContext], n_radios: int) -> list[LinkContext]:
        raise NotImplementedError


class RoundRobinPolicy(LinkSelectionPolicy):
    def __init__(self):
        self._idx = 0

    def select(self, contexts: list[LinkContext], n_radios: int) -> list[LinkContext]:
        idle = [c for c in contexts if c.state == LinkState.IDLE]
        selected = []
        for _ in range(min(n_radios, len(idle))):
            selected.append(idle[self._idx % len(idle)])
            self._idx += 1
        return selected


class LoadBalancePolicy(LinkSelectionPolicy):
    def select(self, contexts: list[LinkContext], n_radios: int) -> list[LinkContext]:
        """Select idle links ordered by ascending total queue depth (least-loaded first)."""
        idle = [c for c in contexts if c.state == LinkState.IDLE]
        if not idle:
            return []

        def _queue_depth(ctx: LinkContext) -> int:
            sched = getattr(ctx.node, "edca_scheduler", None)
            if sched is None:
                return 0
            return sum(len(q._queue) for q in sched.queues.values())

        idle.sort(key=_queue_depth)
        return idle[:n_radios]


class MLOLinkManager:
    """
    Owns N LinkContext objects (one per link/band).
    Implements STR, EMLSR, EMLMR link coordination.
    """

    def __init__(self, node: "Node", engine: "SimulationEngine"):
        self.node = node
        self.engine = engine
        self.links: dict[str, LinkContext] = {
            link_id: LinkContext(link_id, node)
            for link_id in node.links
        }
        self.mlo_mode: str = node.mlo_mode
        # EMLSR: tracks active radio link
        self._emlsr_active_link: str | None = None
        # EMLMR: link selection policy
        self._emlmr_policy: LinkSelectionPolicy = RoundRobinPolicy()
        # EMLMR: n radios (from node config)
        self._n_radios: int = getattr(node, "emlmr_n_radios", 2)
        # TID-to-link mapping
        from nxwlansim.mac.tid_link_map import TIDLinkMap, default_map
        self.tid_link_map: TIDLinkMap = default_map()

    # ------------------------------------------------------------------
    # STR — all links fully independent
    # ------------------------------------------------------------------

    def str_txop_granted(self, link_id: str) -> None:
        ctx = self.links[link_id]
        ctx.state = LinkState.TXOP_GRANTED
        logger.debug("[STR] TXOP granted on %s for %s", link_id, self.node.node_id)

    # ------------------------------------------------------------------
    # EMLSR — single radio, link switching on trigger frame
    # ------------------------------------------------------------------

    def emlsr_trigger(self, trigger_link_id: str) -> None:
        """
        Called when an EMLSR trigger frame is received on trigger_link_id.
        Freezes all other links, schedules transition delay, then activates.
        """
        if self._emlsr_active_link == trigger_link_id:
            return   # already active on this link

        # Freeze all non-trigger links
        for lid, ctx in self.links.items():
            if lid != trigger_link_id:
                ctx.state = LinkState.IDLE
                self.node.edca_scheduler.freeze_link(lid)

        transition_ns = getattr(self.node, "emlsr_transition_delay_ns", 64_000)
        self.engine.schedule_after(
            delay_ns=transition_ns,
            callback=self._emlsr_activate,
            priority=MAC_DECISION,
            link_id=trigger_link_id,
        )
        logger.debug(
            "[EMLSR] Trigger on %s, transition in %d µs",
            trigger_link_id, transition_ns // 1000,
        )

    def _emlsr_activate(self, engine, link_id: str) -> None:
        self._emlsr_active_link = link_id
        ctx = self.links[link_id]
        ctx.state = LinkState.TXOP_GRANTED
        self.node.edca_scheduler.unfreeze_link(link_id)
        logger.debug("[EMLSR] Activated on %s for %s", link_id, self.node.node_id)

    def emlsr_release(self) -> None:
        """Release EMLSR — let all links resume backoff."""
        self._emlsr_active_link = None
        for lid in self.links:
            self.node.edca_scheduler.unfreeze_link(lid)

    # ------------------------------------------------------------------
    # EMLMR — N radios, policy-driven link assignment
    # ------------------------------------------------------------------

    def emlmr_assign(self) -> list[LinkContext]:
        """Assign radios to links using the current policy."""
        contexts = list(self.links.values())
        assigned = self._emlmr_policy.select(contexts, self._n_radios)
        for ctx in assigned:
            ctx.state = LinkState.TXOP_GRANTED
        return assigned

    def set_emlmr_policy(self, policy: LinkSelectionPolicy) -> None:
        self._emlmr_policy = policy

    # ------------------------------------------------------------------
    # Common helpers
    # ------------------------------------------------------------------

    def get_link(self, link_id: str) -> LinkContext:
        return self.links[link_id]

    def active_links(self) -> list[LinkContext]:
        return [c for c in self.links.values() if c.state == LinkState.TRANSMITTING]

    def idle_links(self) -> list[LinkContext]:
        return [c for c in self.links.values() if c.state == LinkState.IDLE]

    def select_link_for_tid(self, tid: int) -> str | None:
        """
        Return the preferred link for a given TID based on TID-to-link mapping.
        Falls back to first idle link.
        """
        available = [
            lid for lid, ctx in self.links.items()
            if ctx.state == LinkState.IDLE
        ]
        if not available:
            available = list(self.links.keys())
        preferred = self.tid_link_map.get_preferred_link(tid, available)
        return preferred or (available[0] if available else None)

    def set_tid_link_map(self, tid_map) -> None:
        self.tid_link_map = tid_map
