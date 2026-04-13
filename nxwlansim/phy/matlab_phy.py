"""
MatlabWlanPhy — Optional MATLAB WLAN Toolbox PHY backend.

Modes:
  loose  — uses pre-exported CSV lookup tables (no MATLAB at runtime)
  medium — starts MATLAB engine once, calls WLAN Toolbox at runtime

Falls back to TGbeChannel if matlab.engine is not installed.
"""

from __future__ import annotations

import logging
import os
import csv
from typing import TYPE_CHECKING

from nxwlansim.phy.base import PhyAbstraction, TxResult, RxResult, ChannelState

if TYPE_CHECKING:
    from nxwlansim.mac.frame import Frame
    from nxwlansim.mac.mlo import LinkContext
    from nxwlansim.core.config import PhyConfig

logger = logging.getLogger(__name__)

_MATLAB_TABLES_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "configs", "matlab_tables"
)


class MatlabWlanPhy(PhyAbstraction):

    def __init__(self, config: "PhyConfig"):
        self._config = config
        self._mode = config.matlab_mode
        self._engine = None
        self._lookup: dict[tuple, int] = {}   # (snr_rounded, bw) → mcs
        self._positions: dict[str, tuple[float, float]] = {}

        if self._mode == "medium":
            self._start_engine()
        elif self._mode == "loose":
            self._load_tables()

    def register_node(self, node_id: str, position: tuple[float, float]) -> None:
        self._positions[node_id] = position

    # ------------------------------------------------------------------
    # PhyAbstraction interface
    # ------------------------------------------------------------------

    def get_channel_state(self, src_id: str, dst_id: str, link_id: str) -> ChannelState:
        if self._mode == "medium" and self._engine:
            return self._matlab_channel_state(src_id, dst_id, link_id)
        return self._lookup_channel_state(src_id, dst_id, link_id)

    def request_tx(self, frame: "Frame", link: "LinkContext") -> TxResult:
        ch = self.get_channel_state(frame.src, frame.dst, link.link_id)
        from nxwlansim.phy.tgbe_channel import _tx_duration_ns
        duration_ns = _tx_duration_ns(frame.size_bytes, ch.mcs_index, ch.bandwidth_mhz)
        return TxResult(
            success=True,
            duration_ns=duration_ns,
            mcs_used=ch.mcs_index,
            bytes_sent=frame.size_bytes,
            link_id=link.link_id,
        )

    def request_rx(self, frame: "Frame", channel: ChannelState) -> RxResult:
        import random, math
        thresh_map = [3,6,9.5,12.5,16.5,19.5,22.5,25,28,30,33,36,39,42]
        thresh = thresh_map[min(channel.mcs_index, len(thresh_map)-1)]
        delta = channel.snr_db - thresh
        per = 0.0 if delta >= 5 else (1.0 if delta <= -5 else 1/(1+math.exp(2*delta)))
        return RxResult(
            success=random.random() > per,
            snr_db=channel.snr_db,
            per=per,
            link_id=channel.link_id,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _start_engine(self) -> None:
        try:
            import matlab.engine
            logger.info("[MATLAB] Starting MATLAB engine...")
            self._engine = matlab.engine.start_matlab()
            logger.info("[MATLAB] Engine ready.")
        except ImportError:
            logger.warning(
                "[MATLAB] matlab.engine not found — falling back to table lookup."
            )
            self._mode = "loose"
            self._load_tables()

    def _load_tables(self) -> None:
        table_path = os.path.join(_MATLAB_TABLES_DIR, "snr_mcs_eht.csv")
        if not os.path.exists(table_path):
            logger.warning(
                "[MATLAB] Table file not found: %s — using TGbe fallback.", table_path
            )
            return
        with open(table_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = (int(float(row["snr_db"])), int(row["bw_mhz"]))
                self._lookup[key] = int(row["mcs_index"])
        logger.info("[MATLAB] Loaded %d SNR→MCS table entries.", len(self._lookup))

    def _lookup_channel_state(self, src_id: str, dst_id: str, link_id: str) -> ChannelState:
        # Fallback to TGbe computation if no tables
        from nxwlansim.phy.tgbe_channel import TGbeChannel
        from nxwlansim.core.config import PhyConfig
        fallback = TGbeChannel(PhyConfig(channel_model=self._config.channel_model))
        fallback._positions = self._positions
        return fallback.get_channel_state(src_id, dst_id, link_id)

    def _matlab_channel_state(self, src_id: str, dst_id: str, link_id: str) -> ChannelState:
        """Call MATLAB WLAN Toolbox at runtime."""
        import math
        # Positions
        sp = self._positions.get(src_id, (0.0, 0.0))
        dp = self._positions.get(dst_id, (10.0, 0.0))
        dist = max(math.dist(sp, dp), 0.1)
        bw_map = {"2g": 40, "5g": 160, "6g": 320}
        bw = bw_map.get(link_id, 80)
        try:
            snr = float(self._engine.eval(
                f"nxwlansim_snr({dist}, {bw}, '{self._config.channel_model}')",
                nargout=1,
            ))
        except Exception as e:
            logger.warning("[MATLAB] Runtime call failed (%s) — using fallback.", e)
            return self._lookup_channel_state(src_id, dst_id, link_id)
        from nxwlansim.phy.tgbe_channel import TGbeChannel
        mcs = TGbeChannel.__new__(TGbeChannel)
        mcs._params = {}
        mcs._rng = __import__("random").Random()
        mcs_idx = mcs._snr_to_mcs(snr) if hasattr(mcs, '_snr_to_mcs') else 7
        return ChannelState(
            link_id=link_id, snr_db=snr, interference_db=0.0,
            bandwidth_mhz=bw, mcs_index=mcs_idx,
        )

    def shutdown(self) -> None:
        if self._engine:
            self._engine.quit()
            self._engine = None
