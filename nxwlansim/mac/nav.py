"""NAV (Network Allocation Vector) — virtual carrier sense. IEEE 802.11-2020 §10.3.2.4"""

from __future__ import annotations


class NAVController:
    """Per-node, per-link NAV manager."""

    def __init__(self):
        self._nav_expiry_ns: int = 0

    def set(self, duration_ns: int, now_ns: int) -> None:
        self._nav_expiry_ns = max(self._nav_expiry_ns, now_ns + duration_ns)

    def is_busy(self, now_ns: int) -> bool:
        return now_ns < self._nav_expiry_ns

    def remaining_ns(self, now_ns: int) -> int:
        return max(0, self._nav_expiry_ns - now_ns)

    def reset(self) -> None:
        self._nav_expiry_ns = 0
