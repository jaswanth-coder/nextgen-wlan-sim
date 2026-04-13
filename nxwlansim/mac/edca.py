"""
EDCAScheduler — IEEE 802.11-2020 §10.22 Enhanced Distributed Channel Access.

Implements per-AC queue management, backoff countdown, AIFS/DIFS/SIFS timing,
and TXOP grant. Cycle-accurate: each backoff slot is a DES event.
"""

from __future__ import annotations

import random
import logging
from enum import Enum, auto
from typing import TYPE_CHECKING

from nxwlansim.mac.frame import Frame, AccessCategoryType, SLOT_NS, aifs_ns, SIFS_NS

if TYPE_CHECKING:
    from nxwlansim.core.engine import SimulationEngine
    from nxwlansim.core.node import Node

logger = logging.getLogger(__name__)


class AccessCategory(Enum):
    VO = 0   # Voice — highest priority
    VI = 1   # Video
    BE = 2   # Best Effort
    BK = 3   # Background — lowest priority


# 802.11be EDCA parameters per AC (CWmin, CWmax, TXOP limit µs)
EDCA_PARAMS: dict[str, tuple[int, int, int]] = {
    "VO": (3,    7,   2_528),
    "VI": (7,   15,   4_096),
    "BE": (15, 1023,      0),   # 0 = unlimited (one AMPDU)
    "BK": (15, 1023,      0),
}


class ACQueue:
    """Single Access Category queue with backoff state."""

    def __init__(self, ac: str, seed: int = 0):
        self.ac = ac
        self.cw_min, self.cw_max, self.txop_limit_us = EDCA_PARAMS[ac]
        self._cw = self.cw_min
        self._backoff: int = 0
        self._queue: list[Frame] = []
        self._rng = random.Random(seed)
        self.frozen: bool = False     # True when EMLSR link is paused

    def enqueue(self, frame: Frame) -> None:
        self._queue.append(frame)
        if self._backoff == 0 and not self.frozen:
            self._backoff = self._rng.randint(0, self._cw)

    def peek(self) -> Frame | None:
        return self._queue[0] if self._queue else None

    def dequeue(self) -> Frame | None:
        return self._queue.pop(0) if self._queue else None

    def decrement_backoff(self) -> int:
        """Decrement backoff by one slot. Returns remaining backoff."""
        if not self.frozen and self._backoff > 0:
            self._backoff -= 1
        return self._backoff

    def collision(self) -> None:
        """Double CW on collision (binary exponential backoff)."""
        self._cw = min(self._cw * 2 + 1, self.cw_max)
        self._backoff = self._rng.randint(0, self._cw)

    def txop_success(self) -> None:
        """Reset CW after successful TXOP."""
        self._cw = self.cw_min
        self._backoff = self._rng.randint(0, self._cw) if self._queue else 0

    @property
    def backoff(self) -> int:
        return self._backoff

    @property
    def empty(self) -> bool:
        return len(self._queue) == 0


class EDCAScheduler:
    """
    Manages 4 AC queues for a node. Schedules DES events for
    each backoff slot decrement on a given link.
    """

    def __init__(self, node: "Node", engine: "SimulationEngine"):
        self.node = node
        self.engine = engine
        self.queues: dict[str, ACQueue] = {
            ac: ACQueue(ac, seed=hash(node.node_id + ac) & 0xFFFF)
            for ac in ("VO", "VI", "BE", "BK")
        }

    def enqueue(self, frame: Frame) -> None:
        self.queues[frame.ac].enqueue(frame)

    def freeze_link(self, link_id: str) -> None:
        """Freeze all AC queues on this link (EMLSR non-active link)."""
        for q in self.queues.values():
            q.frozen = True

    def unfreeze_link(self, link_id: str) -> None:
        for q in self.queues.values():
            q.frozen = False

    def highest_priority_ready(self) -> ACQueue | None:
        """Return highest-priority non-empty AC with backoff == 0."""
        for ac in ("VO", "VI", "BE", "BK"):
            q = self.queues[ac]
            if not q.empty and q.backoff == 0 and not q.frozen:
                return q
        return None
