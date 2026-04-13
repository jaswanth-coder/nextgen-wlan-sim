"""
A-MPDU Aggregation and Block Acknowledgement session.
IEEE 802.11-2020 §10.12 (A-MPDU), §10.24 (BA).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from nxwlansim.mac.frame import MPDUFrame, AMPDUFrame

if TYPE_CHECKING:
    from nxwlansim.core.engine import SimulationEngine

logger = logging.getLogger(__name__)

MAX_AMPDU_SUBFRAMES = 256        # 802.11be max
BA_BITMAP_SIZE      = 256        # bits
BA_TIMEOUT_NS       = 10_000_000 # 10 ms default


@dataclass
class BlockAckSession:
    """Scoreboard BA session between two peers on one TID and link."""
    peer_mac: str
    tid: int
    link_id: str
    win_start: int = 0
    bitmap: int = 0              # 256-bit integer bitmask
    timeout_ns: int = BA_TIMEOUT_NS
    active: bool = True

    def mark_received(self, seq_num: int) -> None:
        offset = (seq_num - self.win_start) % 4096
        if 0 <= offset < BA_BITMAP_SIZE:
            self.bitmap |= (1 << offset)

    def is_received(self, seq_num: int) -> bool:
        offset = (seq_num - self.win_start) % 4096
        return bool(self.bitmap & (1 << offset))

    def advance_window(self) -> None:
        """Slide BA window past consecutively received frames."""
        while self.bitmap & 1:
            self.bitmap >>= 1
            self.win_start = (self.win_start + 1) % 4096

    def missing_seqs(self) -> list[int]:
        """Return sequence numbers not yet acknowledged."""
        missing = []
        for i in range(BA_BITMAP_SIZE):
            if not (self.bitmap & (1 << i)):
                missing.append((self.win_start + i) % 4096)
        return missing[:16]  # limit retransmit burst


class AmpduAggregator:
    """
    Builds A-MPDU frames from per-AC EDCA queue output.
    Respects TXOP duration limit and per-link MCS/bandwidth.
    """

    def __init__(self, node, engine: "SimulationEngine"):
        self.node = node
        self.engine = engine
        self._ba_sessions: dict[tuple, BlockAckSession] = {}
        self._seq_counter: dict[str, int] = {}  # per AC

    def build_ampdu(
        self,
        frames: list[MPDUFrame],
        link_id: str,
        txop_remaining_ns: int,
        mcs: int,
        bandwidth_mhz: int,
    ) -> AMPDUFrame:
        """Aggregate frames into an A-MPDU fitting within TXOP."""
        ampdu = AMPDUFrame(link_id=link_id)
        byte_budget = _txop_bytes(txop_remaining_ns, mcs, bandwidth_mhz)
        for frame in frames[:MAX_AMPDU_SUBFRAMES]:
            if ampdu.total_size_bytes + frame.size_bytes > byte_budget:
                break
            frame.seq_num = self._next_seq(frame.ac)
            ampdu.add(frame)
        return ampdu

    def get_or_create_ba_session(
        self, peer_mac: str, tid: int, link_id: str
    ) -> BlockAckSession:
        key = (peer_mac, tid, link_id)
        if key not in self._ba_sessions:
            self._ba_sessions[key] = BlockAckSession(
                peer_mac=peer_mac, tid=tid, link_id=link_id
            )
            logger.debug(
                "[BA] New session: peer=%s tid=%d link=%s", peer_mac, tid, link_id
            )
        return self._ba_sessions[key]

    def _next_seq(self, ac: str) -> int:
        self._seq_counter[ac] = (self._seq_counter.get(ac, 0) + 1) % 4096
        return self._seq_counter[ac]


def _txop_bytes(txop_ns: int, mcs: int, bw_mhz: int) -> int:
    """Approximate max bytes transmittable in txop_ns at given MCS/BW."""
    # Simplified: use MCS→rate table (Mbps), convert to bytes
    # Full table will be populated in Phase 1 implementation
    _MCS_RATE_MBPS = {
        0: 8.6, 1: 17.2, 2: 25.8, 3: 34.4, 4: 51.6, 5: 68.8,
        6: 77.4, 7: 86.0, 8: 103.2, 9: 114.7, 10: 129.0,
        11: 143.4, 12: 154.9, 13: 172.1,   # EHT MCS 0-13 @ 20 MHz
    }
    rate_mbps = _MCS_RATE_MBPS.get(mcs, 86.0) * (bw_mhz / 20)
    bytes_per_ns = rate_mbps * 1e6 / 8 / 1e9
    return int(bytes_per_ns * txop_ns)
