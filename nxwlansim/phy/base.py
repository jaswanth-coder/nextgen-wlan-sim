"""
PhyAbstraction — plugin interface for PHY backends.
All PHY backends (TGbe standalone, MATLAB) implement this ABC.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nxwlansim.mac.frame import Frame
    from nxwlansim.mac.mlo import LinkContext


@dataclass
class ChannelState:
    link_id: str
    snr_db: float
    interference_db: float
    bandwidth_mhz: int
    mcs_index: int
    path_loss_db: float = 0.0


@dataclass
class TxResult:
    success: bool
    duration_ns: int
    mcs_used: int
    bytes_sent: int
    link_id: str


@dataclass
class RxResult:
    success: bool
    snr_db: float
    per: float          # Packet Error Rate [0.0, 1.0]
    link_id: str


class PhyAbstraction(ABC):
    """
    Abstract PHY plugin interface.
    Implementations: TGbeChannel, MatlabWlanPhy.
    """

    @abstractmethod
    def request_tx(self, frame: "Frame", link: "LinkContext") -> TxResult:
        """Transmit frame on link. Returns transmission result."""
        ...

    @abstractmethod
    def request_rx(self, frame: "Frame", channel: ChannelState) -> RxResult:
        """Receive frame given channel state. Returns reception result."""
        ...

    @abstractmethod
    def get_channel_state(
        self, src_id: str, dst_id: str, link_id: str
    ) -> ChannelState:
        """Compute current channel state between src and dst on link."""
        ...
