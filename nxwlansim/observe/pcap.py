"""
PCAPWriter — writes libpcap files with 802.11 radiotap headers.
One file per link. Wireshark-compatible.
"""

from __future__ import annotations

import struct
import os
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nxwlansim.mac.frame import Frame
    from nxwlansim.phy.base import TxResult

logger = logging.getLogger(__name__)

# libpcap global header constants
PCAP_MAGIC       = 0xA1B2C3D4
PCAP_VERSION_MAJ = 2
PCAP_VERSION_MIN = 4
PCAP_SNAPLEN     = 65535
PCAP_LINKTYPE    = 127   # LINKTYPE_IEEE802_11_RADIOTAP


class PCAPWriter:
    """Writes one PCAP file per radio link."""

    def __init__(self, output_dir: str):
        self._output_dir = output_dir
        self._files: dict[str, object] = {}
        os.makedirs(output_dir, exist_ok=True)

    def _get_file(self, link_id: str):
        if link_id not in self._files:
            path = os.path.join(self._output_dir, f"capture_{link_id}.pcap")
            f = open(path, "wb")
            # Write global header
            f.write(struct.pack(
                "<IHHiIII",
                PCAP_MAGIC, PCAP_VERSION_MAJ, PCAP_VERSION_MIN,
                0, 0, PCAP_SNAPLEN, PCAP_LINKTYPE,
            ))
            self._files[link_id] = f
            logger.info("[PCAP] Opened %s", path)
        return self._files[link_id]

    def write_frame(
        self,
        frame: "Frame",
        tx_result: "TxResult",
        timestamp_ns: int,
    ) -> None:
        f = self._get_file(frame.link_id)
        radiotap = _build_radiotap(tx_result.mcs_used, frame.link_id, tx_result)
        # Minimal 802.11 data frame header (24 bytes)
        dot11 = _build_dot11_header(frame)
        payload = bytes(min(frame.size_bytes, 1500))
        packet = radiotap + dot11 + payload
        ts_sec = timestamp_ns // 1_000_000_000
        ts_usec = (timestamp_ns % 1_000_000_000) // 1_000
        f.write(struct.pack("<IIII", ts_sec, ts_usec, len(packet), len(packet)))
        f.write(packet)

    def close_all(self) -> None:
        for f in self._files.values():
            f.close()
        self._files.clear()


def _build_radiotap(mcs: int, link_id: str, tx: "TxResult") -> bytes:
    """Minimal radiotap header with MCS and channel info."""
    bw_map = {"2g": 40, "5g": 160, "6g": 320}
    bw = bw_map.get(link_id, 80)
    # radiotap header: version(1) pad(1) len(2) present(4) mcs(3) = 12 bytes
    length = 12
    present = (1 << 19)  # MCS field present
    mcs_known = 0x07     # bandwidth + MCS index + guard interval known
    mcs_flags = 0x00
    header = struct.pack("<BBHI BBB",
        0, 0, length, present,
        mcs_known, mcs_flags, mcs & 0xFF,
    )
    return header


def _build_dot11_header(frame: "Frame") -> bytes:
    """Minimal 802.11 data frame FC + addresses (24 bytes)."""
    fc = struct.pack("<H", 0x0208)   # Data frame, ToDS=1
    dur = struct.pack("<H", 0)
    def mac_bytes(mac_str):
        return bytes(int(x, 16) for x in mac_str.split(":"))
    try:
        addr1 = mac_bytes(frame.dst[:17]) if ":" in frame.dst else bytes(6)
        addr2 = mac_bytes(frame.src[:17]) if ":" in frame.src else bytes(6)
    except Exception:
        addr1 = addr2 = bytes(6)
    addr3 = bytes(6)   # BSSID (placeholder)
    seq = struct.pack("<H", frame.seq_num & 0xFFF0)
    return fc + dur + addr1 + addr2 + addr3 + seq
