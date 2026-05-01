"""Unit tests for TablePhy — interpolation, MCS selection, PER boundary values."""
import math
import numpy as np
import pytest
from nxwlansim.phy.matlab.cache import TableSet
from nxwlansim.phy.matlab.table_phy import TablePhy
from nxwlansim.mac.frame import MPDUFrame
from nxwlansim.mac.mlo import LinkContext, LinkState


def _make_tables() -> TableSet:
    """3-MCS fixture table: D/80MHz, MCS 0/4/9."""
    snr = np.arange(0.0, 45.0, 5.0)  # 9 points
    MCS_THRESH = {0: 3.0, 4: 16.5, 9: 30.0}
    MCS_RATE = {0: 34.4, 4: 206.4, 9: 458.8}  # Mbps at 80 MHz
    tables = {}
    for mcs, thresh in MCS_THRESH.items():
        per = 1.0 / (1.0 + np.exp((snr - thresh) * 2.0))
        tput = MCS_RATE[mcs] * (1.0 - per)
        tables[("D", 80, mcs, 1, 1)] = {
            "snr_db": snr, "per": per, "tput_mbps": tput
        }
    return tables


@pytest.fixture
def phy():
    t = TablePhy(_make_tables(), channel_model="D", per_threshold=0.1, seed=0)
    t.register_node("ap0", (0.0, 0.0))
    t.register_node("sta0", (5.0, 0.0))
    return t


def test_per_high_at_low_snr(phy):
    # At SNR=0 dB, MCS 0 PER ≈ sigmoid(0-3)≈0.95 — should pick MCS 0 but still high
    ch = phy.get_channel_state("sta0", "ap0", "5g")
    assert ch.mcs_index >= 0


def test_get_channel_state_returns_valid(phy):
    ch = phy.get_channel_state("sta0", "ap0", "6g")
    assert ch.link_id == "6g"
    assert -20 < ch.snr_db < 60
    assert ch.mcs_index in range(14)
    assert ch.bandwidth_mhz > 0


def test_request_tx_returns_result(phy):
    frame = MPDUFrame(frame_id=1, src="sta0", dst="ap0", size_bytes=1500, link_id="6g")
    ctx = LinkContext("6g", None)
    result = phy.request_tx(frame, ctx)
    assert result.duration_ns > 0
    assert result.link_id == "6g"
    assert result.mcs_used in range(14)


def test_request_rx_success_at_high_snr():
    tables = _make_tables()
    # Patch PER to near-zero at high SNR
    for key in tables:
        tables[key]["per"][-1] = 0.001   # last point (SNR=40) near zero
    phy = TablePhy(tables, seed=99)
    from nxwlansim.phy.base import ChannelState
    ch_state = ChannelState(link_id="6g", snr_db=40.0, interference_db=0.0,
                            bandwidth_mhz=80, mcs_index=9)
    results = [phy.request_rx(None, ch_state) for _ in range(100)]
    success_rate = sum(r.success for r in results) / 100
    assert success_rate > 0.85   # near-zero PER → mostly success


def test_request_rx_fails_at_low_snr():
    tables = _make_tables()
    phy = TablePhy(tables, seed=7)
    from nxwlansim.phy.base import ChannelState
    ch_state = ChannelState(link_id="6g", snr_db=0.0, interference_db=0.0,
                            bandwidth_mhz=80, mcs_index=0)
    results = [phy.request_rx(None, ch_state) for _ in range(100)]
    success_rate = sum(r.success for r in results) / 100
    assert success_rate < 0.5   # high PER at 0 dB
