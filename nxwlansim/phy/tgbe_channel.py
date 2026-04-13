"""
TGbeChannel — Standalone PHY abstraction.
TGbe Model D (indoor office) and E (large open space) with log-normal shadowing.
Reference: IEEE 802.11-09/0308r1, ns-3 WifiPhy channel models.
"""

from __future__ import annotations

import math
import random
import logging
from typing import TYPE_CHECKING

import numpy as np

from nxwlansim.phy.base import PhyAbstraction, TxResult, RxResult, ChannelState

if TYPE_CHECKING:
    from nxwlansim.mac.frame import Frame
    from nxwlansim.mac.mlo import LinkContext
    from nxwlansim.core.config import PhyConfig

logger = logging.getLogger(__name__)

# TGbe model parameters (Model D / E)
_TGBE_PARAMS = {
    "D": {"exp": 3.0, "shadow_sigma_db": 4.0, "ref_dist_m": 1.0, "ref_loss_db": 40.1},
    "E": {"exp": 2.0, "shadow_sigma_db": 6.0, "ref_dist_m": 1.0, "ref_loss_db": 35.7},
}

# Band → center frequency (GHz)
_BAND_FREQ_GHZ = {"2g": 2.437, "5g": 5.500, "6g": 6.200}

# EHT MCS → min SNR (dB) required for ~10% PER (simplified)
_MCS_SNR_THRESH: list[float] = [
    3.0, 6.0, 9.5, 12.5, 16.5, 19.5, 22.5, 25.0,
    28.0, 30.0, 33.0, 36.0, 39.0, 42.0,
]

# Tx power default (dBm)
TX_POWER_DBM = 20.0
NOISE_FIGURE_DB = 7.0
THERMAL_NOISE_DBM_PER_HZ = -174.0   # kTB at 290 K


class TGbeChannel(PhyAbstraction):

    def __init__(self, config: "PhyConfig"):
        self._model = config.channel_model  # "D" or "E"
        self._rng = random.Random()
        self._params = _TGBE_PARAMS[self._model]
        # Cache node positions — injected by builder after nodes are created
        self._positions: dict[str, tuple[float, float]] = {}

    def register_node(self, node_id: str, position: tuple[float, float]) -> None:
        self._positions[node_id] = position

    # ------------------------------------------------------------------
    # PhyAbstraction interface
    # ------------------------------------------------------------------

    def get_channel_state(self, src_id: str, dst_id: str, link_id: str) -> ChannelState:
        snr_db = self._compute_snr(src_id, dst_id, link_id)
        bw = _link_bandwidth_mhz(link_id)
        mcs = self._snr_to_mcs(snr_db)
        return ChannelState(
            link_id=link_id,
            snr_db=snr_db,
            interference_db=0.0,   # inter-BSS interference: Phase 2
            bandwidth_mhz=bw,
            mcs_index=mcs,
        )

    def request_tx(self, frame: "Frame", link: "LinkContext") -> TxResult:
        ch = self.get_channel_state(frame.src, frame.dst, link.link_id)
        duration_ns = _tx_duration_ns(frame.size_bytes, ch.mcs_index, ch.bandwidth_mhz)
        return TxResult(
            success=True,
            duration_ns=duration_ns,
            mcs_used=ch.mcs_index,
            bytes_sent=frame.size_bytes,
            link_id=link.link_id,
        )

    def request_rx(self, frame: "Frame", channel: ChannelState) -> RxResult:
        per = self._compute_per(channel.snr_db, channel.mcs_index)
        success = self._rng.random() > per
        return RxResult(
            success=success,
            snr_db=channel.snr_db,
            per=per,
            link_id=channel.link_id,
        )

    # ------------------------------------------------------------------
    # Internal computations
    # ------------------------------------------------------------------

    def _compute_snr(self, src_id: str, dst_id: str, link_id: str) -> float:
        dist_m = self._distance(src_id, dst_id)
        dist_m = max(dist_m, 0.1)   # avoid log(0)
        freq_ghz = _BAND_FREQ_GHZ.get(link_id, 6.2)
        path_loss_db = self._path_loss(dist_m, freq_ghz)
        shadow_db = self._rng.gauss(0, self._params["shadow_sigma_db"])
        rx_power_dbm = TX_POWER_DBM - path_loss_db - shadow_db
        bw_mhz = _link_bandwidth_mhz(link_id)
        noise_dbm = THERMAL_NOISE_DBM_PER_HZ + 10 * math.log10(bw_mhz * 1e6) + NOISE_FIGURE_DB
        return rx_power_dbm - noise_dbm

    def _path_loss(self, dist_m: float, freq_ghz: float) -> float:
        p = self._params
        fspl = 20 * math.log10(4 * math.pi * p["ref_dist_m"] * freq_ghz * 1e9 / 3e8)
        return fspl + 10 * p["exp"] * math.log10(dist_m / p["ref_dist_m"])

    def _distance(self, src_id: str, dst_id: str) -> float:
        if src_id not in self._positions or dst_id not in self._positions:
            return 10.0   # default 10 m if positions unknown
        sx, sy = self._positions[src_id]
        dx, dy = self._positions[dst_id]
        return math.sqrt((sx - dx) ** 2 + (sy - dy) ** 2) or 0.1

    def _snr_to_mcs(self, snr_db: float) -> int:
        for mcs in range(len(_MCS_SNR_THRESH) - 1, -1, -1):
            if snr_db >= _MCS_SNR_THRESH[mcs]:
                return mcs
        return 0

    def _compute_per(self, snr_db: float, mcs: int) -> float:
        thresh = _MCS_SNR_THRESH[min(mcs, len(_MCS_SNR_THRESH) - 1)]
        delta = snr_db - thresh
        # Sigmoid-like PER curve
        if delta >= 5:
            return 0.0
        elif delta <= -5:
            return 1.0
        return 1.0 / (1.0 + math.exp(2.0 * delta))


def _link_bandwidth_mhz(link_id: str) -> int:
    """Default bandwidth per band. Configurable per-scenario in later phases."""
    return {"2g": 40, "5g": 160, "6g": 320}.get(link_id, 80)


def _tx_duration_ns(size_bytes: int, mcs: int, bw_mhz: int) -> int:
    """Compute PPDU transmission duration in nanoseconds."""
    # EHT PPDU overhead: ~100 µs preamble (simplified)
    _MCS_RATE_MBPS = [
        8.6, 17.2, 25.8, 34.4, 51.6, 68.8,
        77.4, 86.0, 103.2, 114.7, 129.0, 143.4, 154.9, 172.1,
    ]
    rate_mbps = _MCS_RATE_MBPS[min(mcs, 13)] * (bw_mhz / 20)
    data_ns = int(size_bytes * 8 / (rate_mbps * 1e6) * 1e9)
    preamble_ns = 100_000   # 100 µs EHT preamble overhead
    return preamble_ns + data_ns
