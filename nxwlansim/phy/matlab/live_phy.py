"""
MatlabLivePhy — delegates to TablePhy if tables available, else bare defaults.
Used only when custom channel not yet in cache.
"""
from __future__ import annotations
import logging
from typing import TYPE_CHECKING

from nxwlansim.phy.base import PhyAbstraction, ChannelState, TxResult, RxResult
from nxwlansim.phy.matlab.table_phy import TablePhy, _BAND_BW_MHZ, _MCS_RATE_20MHZ

if TYPE_CHECKING:
    from nxwlansim.mac.frame import Frame
    from nxwlansim.mac.mlo import LinkContext

logger = logging.getLogger(__name__)


class MatlabLivePhy(PhyAbstraction):
    """Thin wrapper — calls TablePhy if tables loaded, otherwise safe defaults."""

    def __init__(self, table_phy: TablePhy | None = None):
        self._phy = table_phy
        self._positions: dict[str, tuple] = {}

    def register_node(self, node_id: str, position: tuple) -> None:
        self._positions[node_id] = position
        if self._phy:
            self._phy.register_node(node_id, position)

    def get_channel_state(self, src_id: str, dst_id: str, link_id: str) -> ChannelState:
        if self._phy:
            return self._phy.get_channel_state(src_id, dst_id, link_id)
        bw = _BAND_BW_MHZ.get(link_id, 80)
        return ChannelState(link_id=link_id, snr_db=20.0, interference_db=0.0,
                            bandwidth_mhz=bw, mcs_index=7, path_loss_db=60.0)

    def request_tx(self, frame: "Frame", link: "LinkContext") -> TxResult:
        if self._phy:
            return self._phy.request_tx(frame, link)
        bw = _BAND_BW_MHZ.get(link.link_id, 80)
        tput = _MCS_RATE_20MHZ[7] * (bw / 20)
        dur = max(int(frame.size_bytes * 8 / (tput * 1e6) * 1e9), 1_000)
        return TxResult(success=True, duration_ns=dur, mcs_used=7,
                        bytes_sent=frame.size_bytes, link_id=link.link_id)

    def request_rx(self, frame: "Frame", channel: ChannelState) -> RxResult:
        if self._phy:
            return self._phy.request_rx(frame, channel)
        return RxResult(success=True, snr_db=channel.snr_db, per=0.01, link_id=channel.link_id)
