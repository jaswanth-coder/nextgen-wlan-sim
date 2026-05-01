"""
TablePhy — pure-Python PHY using pre-computed MATLAB PER/SNR tables.
No matlab.engine dependency — CI-safe.
"""
from __future__ import annotations
import math
import random
import logging
import numpy as np
from typing import TYPE_CHECKING

from nxwlansim.phy.base import PhyAbstraction, ChannelState, TxResult, RxResult
from nxwlansim.phy.matlab.cache import TableSet

if TYPE_CHECKING:
    from nxwlansim.mac.frame import Frame
    from nxwlansim.mac.mlo import LinkContext

logger = logging.getLogger(__name__)

_BAND_BW_MHZ: dict[str, int] = {"2g": 20, "5g": 80, "6g": 160}
_MCS_RATE_20MHZ = [8.6, 17.2, 25.8, 34.4, 51.6, 68.8, 77.4,
                    86.0, 103.2, 114.7, 129.0, 143.4, 154.9, 172.1]
_TGBE_PARAMS = {
    "D": (3.0, 4.0, 1.0, 40.1),
    "E": (2.0, 6.0, 1.0, 35.7),
}
TX_POWER_DBM = 20.0
NOISE_FIGURE_DB = 7.0


class TablePhy(PhyAbstraction):
    """Interpolates PER and throughput from MATLAB-generated tables."""

    def __init__(
        self,
        tables: TableSet,
        channel_model: str = "D",
        per_threshold: float = 0.1,
        seed: int = 42,
    ):
        self._tables = tables
        self._model = channel_model
        self._per_threshold = per_threshold
        self._rng = random.Random(seed)
        self._positions: dict[str, tuple[float, float]] = {}
        exp, shadow, ref_d, ref_loss = _TGBE_PARAMS.get(channel_model, _TGBE_PARAMS["D"])
        self._exp = exp
        self._shadow_sigma = shadow
        self._ref_d = ref_d
        self._ref_loss = ref_loss

    def register_node(self, node_id: str, position: tuple[float, float]) -> None:
        self._positions[node_id] = position

    # ------------------------------------------------------------------
    # PhyAbstraction interface
    # ------------------------------------------------------------------

    def get_channel_state(self, src_id: str, dst_id: str, link_id: str) -> ChannelState:
        bw = _BAND_BW_MHZ.get(link_id, 80)
        snr = self._snr(src_id, dst_id, link_id)
        mcs, per, _ = self._best_mcs(snr, bw)
        return ChannelState(
            link_id=link_id,
            snr_db=snr,
            interference_db=0.0,
            bandwidth_mhz=bw,
            mcs_index=mcs,
            path_loss_db=self._path_loss(src_id, dst_id),
        )

    def request_tx(self, frame: "Frame", link: "LinkContext") -> TxResult:
        bw = _BAND_BW_MHZ.get(link.link_id, 80)
        snr = self._snr(frame.src, frame.dst, link.link_id)
        mcs, per, tput = self._best_mcs(snr, bw)
        success = self._rng.random() > per
        if tput <= 0:
            tput = _MCS_RATE_20MHZ[mcs] * (bw / 20)
        duration_ns = max(int(frame.size_bytes * 8 / (tput * 1e6) * 1e9), 1_000)
        return TxResult(
            success=success,
            duration_ns=duration_ns,
            mcs_used=mcs,
            bytes_sent=frame.size_bytes if success else 0,
            link_id=link.link_id,
        )

    def request_rx(self, frame: "Frame", channel: ChannelState) -> RxResult:
        _, per, _ = self._best_mcs(channel.snr_db, channel.bandwidth_mhz)
        success = self._rng.random() > per
        return RxResult(success=success, snr_db=channel.snr_db,
                        per=per, link_id=channel.link_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _path_loss(self, src: str, dst: str) -> float:
        p1 = self._positions.get(src, (0.0, 0.0))
        p2 = self._positions.get(dst, (0.0, 0.0))
        dist = max(math.dist(p1, p2), 0.1)
        shadow = self._rng.gauss(0, self._shadow_sigma)
        return self._ref_loss + 10 * self._exp * math.log10(dist / self._ref_d) + shadow

    def _snr(self, src: str, dst: str, link_id: str) -> float:
        bw = _BAND_BW_MHZ.get(link_id, 80)
        noise = -174 + 10 * math.log10(bw * 1e6) + NOISE_FIGURE_DB
        return TX_POWER_DBM - self._path_loss(src, dst) - noise

    def _best_mcs(self, snr: float, bw: int) -> tuple[int, float, float]:
        """Return (mcs, per, tput_mbps) for the highest MCS with PER < threshold."""
        for mcs in range(13, -1, -1):
            key = self._find_key(mcs, bw)
            if key is None:
                continue
            data = self._tables[key]
            per = float(np.interp(snr, data["snr_db"], data["per"]))
            if per < self._per_threshold:
                tput = float(np.interp(snr, data["snr_db"], data["tput_mbps"]))
                return mcs, per, tput
        # Fallback MCS 0
        key = self._find_key(0, bw)
        if key:
            data = self._tables[key]
            per = float(np.interp(snr, data["snr_db"], data["per"]))
            tput = float(np.interp(snr, data["snr_db"], data["tput_mbps"]))
            return 0, per, tput
        return 0, 1.0, _MCS_RATE_20MHZ[0] * (bw / 20)

    def _find_key(self, mcs: int, bw: int) -> tuple | None:
        """Find best matching key in tables for given mcs + bw."""
        exact = (self._model, bw, mcs, 1, 1)
        if exact in self._tables:
            return exact
        # Try any BW for same model + mcs
        for k in self._tables:
            if k[0] == self._model and k[2] == mcs:
                return k
        return None
