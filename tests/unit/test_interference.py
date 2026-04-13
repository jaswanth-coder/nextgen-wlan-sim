"""Unit tests for InterferenceTracker and SINR computation."""

import pytest
from nxwlansim.phy.interference import InterferenceTracker, reset_tracker, get_tracker


def make_tracker():
    return InterferenceTracker()


def test_no_interference_returns_low_value():
    t = make_tracker()
    result = t.get_interference_dbm(
        link_id="6g", now_ns=100,
        exclude_node_id="ap0", dst_id="sta0",
        positions={"ap0": (0, 0), "sta0": (5, 0)},
    )
    assert result < -100   # effectively zero


def test_single_interferer_detected():
    t = make_tracker()
    t.register_tx("sta1", "6g", tx_power_dbm=20.0, start_ns=0, end_ns=500_000, dst_id="ap0")
    result = t.get_interference_dbm(
        link_id="6g", now_ns=100,
        exclude_node_id="ap0", dst_id="sta0",
        positions={"ap0": (0, 0), "sta0": (5, 0), "sta1": (3, 0)},
    )
    assert result > -150   # some interference detected


def test_expired_tx_not_counted():
    t = make_tracker()
    t.register_tx("sta1", "6g", tx_power_dbm=20.0, start_ns=0, end_ns=1000, dst_id="ap0")
    result = t.get_interference_dbm(
        link_id="6g", now_ns=5000,   # after TX ended
        exclude_node_id="ap0", dst_id="sta0",
        positions={"ap0": (0, 0), "sta0": (5, 0), "sta1": (3, 0)},
    )
    assert result < -100


def test_different_link_not_counted():
    t = make_tracker()
    t.register_tx("sta1", "5g", tx_power_dbm=20.0, start_ns=0, end_ns=500_000, dst_id="ap0")
    result = t.get_interference_dbm(
        link_id="6g", now_ns=100,
        exclude_node_id="ap0", dst_id="sta0",
        positions={"ap0": (0, 0), "sta0": (5, 0), "sta1": (3, 0)},
    )
    assert result < -100   # different link — no interference


def test_excluded_node_not_counted():
    t = make_tracker()
    t.register_tx("ap0", "6g", tx_power_dbm=20.0, start_ns=0, end_ns=500_000, dst_id="sta0")
    result = t.get_interference_dbm(
        link_id="6g", now_ns=100,
        exclude_node_id="ap0",   # excluded
        dst_id="sta0",
        positions={"ap0": (0, 0), "sta0": (5, 0)},
    )
    assert result < -100


def test_reset_clears_state():
    reset_tracker()
    t = get_tracker()
    t.register_tx("sta1", "6g", tx_power_dbm=20.0, start_ns=0, end_ns=999_999_999, dst_id="ap0")
    reset_tracker()
    t2 = get_tracker()
    result = t2.get_interference_dbm(
        link_id="6g", now_ns=100,
        exclude_node_id="ap0", dst_id="sta0",
        positions={"ap0": (0, 0), "sta0": (5, 0), "sta1": (3, 0)},
    )
    assert result < -100


def test_closer_interferer_stronger():
    t = make_tracker()
    t.register_tx("close", "6g", tx_power_dbm=20.0, start_ns=0, end_ns=500_000, dst_id="ap0")
    t2 = make_tracker()
    t2.register_tx("far", "6g", tx_power_dbm=20.0, start_ns=0, end_ns=500_000, dst_id="ap0")

    r_close = t.get_interference_dbm(
        "6g", 100, "ap0", "sta0",
        {"ap0": (0, 0), "sta0": (5, 0), "close": (1, 0)},
    )
    r_far = t2.get_interference_dbm(
        "6g", 100, "ap0", "sta0",
        {"ap0": (0, 0), "sta0": (5, 0), "far": (50, 0)},
    )
    assert r_close > r_far
