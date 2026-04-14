"""
802.11be frame dataclasses.
All sizes in bytes, all durations in nanoseconds.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal


FrameType = Literal["data", "mgmt", "ctrl", "null"]
AccessCategoryType = Literal["BE", "BK", "VI", "VO"]


@dataclass
class Frame:
    frame_id: int
    src: str
    dst: str
    frame_type: FrameType = "data"
    size_bytes: int = 1500
    tid: int = 0                          # Traffic Identifier (0–15)
    ac: AccessCategoryType = "BE"
    link_id: str = "6g"
    seq_num: int = 0
    retry: bool = False
    timestamp_ns: int = 0                 # when injected into MAC queue


@dataclass
class MPDUFrame(Frame):
    msdu_payload: bytes = field(default_factory=bytes)


@dataclass
class AMPDUFrame:
    """Aggregated MPDU container."""
    subframes: list[MPDUFrame] = field(default_factory=list)
    link_id: str = "6g"
    total_size_bytes: int = 0
    duration_ns: int = 0                  # computed TXOP duration
    punctured_mask: int = 0       # bitmask of punctured 80 MHz sub-channels
    effective_bw_mhz: float = 0.0 # TX bandwidth after puncturing

    def add(self, mpdu: MPDUFrame) -> None:
        self.subframes.append(mpdu)
        self.total_size_bytes += mpdu.size_bytes

    @property
    def n_subframes(self) -> int:
        return len(self.subframes)


@dataclass
class ManagementFrame(Frame):
    """Mgmt frames: AddBA, DelBA, EMLSR trigger, MLO probe, etc."""
    mgmt_subtype: str = "generic"


# 802.11be timing constants (nanoseconds) — 6 GHz band default
SIFS_NS    = 16_000
DIFS_NS    = 34_000
SLOT_NS    =  9_000
AIFSN = {"VO": 2, "VI": 2, "BE": 3, "BK": 7}

def aifs_ns(ac: AccessCategoryType) -> int:
    return SIFS_NS + AIFSN[ac] * SLOT_NS
