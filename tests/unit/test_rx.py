"""Unit tests for RX processor and TID-to-link mapping."""

import pytest
from nxwlansim.mac.rx import RXProcessor, prop_delay_ns
from nxwlansim.mac.tid_link_map import (
    TIDLinkMap, default_map, voip_optimized_map, load_balance_map, TID_TO_AC
)


# --- Propagation delay ---

def test_prop_delay_minimum():
    assert prop_delay_ns(0) >= 1

def test_prop_delay_scales_with_distance():
    assert prop_delay_ns(10) > prop_delay_ns(1)

def test_prop_delay_10m():
    # ~33 ns for 10 m
    d = prop_delay_ns(10)
    assert 30 <= d <= 40


# --- TID-to-link mapping ---

def test_default_map_no_restriction():
    m = default_map()
    links = ["5g", "6g"]
    for tid in range(16):
        assert m.get_links_for_tid(tid, links) == links

def test_restrict_tid_to_link():
    m = TIDLinkMap()
    m.set_tid_links(6, ["6g"], preferred="6g")
    assert m.get_links_for_tid(6, ["5g", "6g"]) == ["6g"]
    assert m.get_preferred_link(6, ["5g", "6g"]) == "6g"

def test_voip_map_routes_vo_to_6g():
    m = voip_optimized_map(voip_link="6g")
    # TID 6 (VO) → 6g only
    assert m.get_links_for_tid(6, ["5g", "6g"]) == ["6g"]
    assert m.get_preferred_link(6, ["5g", "6g"]) == "6g"

def test_voip_map_vi_uses_data_links():
    m = voip_optimized_map(voip_link="6g", data_links=["5g", "6g"])
    vi_links = m.get_links_for_tid(4, ["5g", "6g"])
    assert "5g" in vi_links or "6g" in vi_links

def test_load_balance_map_distributes_tids():
    m = load_balance_map(["5g", "6g"])
    # Even TIDs → 5g preferred, odd → 6g (round-robin)
    pref_0 = m.get_preferred_link(0, ["5g", "6g"])
    pref_1 = m.get_preferred_link(1, ["5g", "6g"])
    assert pref_0 != pref_1   # distributed across links

def test_restrict_ac_to_link():
    m = TIDLinkMap()
    m.restrict_ac_to_link("VO", "6g")
    for tid, ac in TID_TO_AC.items():
        if ac == "VO":
            assert "6g" in m.get_links_for_tid(tid, ["5g", "6g"])

def test_no_available_links_returns_none():
    m = TIDLinkMap()
    m.set_tid_links(0, ["6g"])
    # 6g not in available
    result = m.get_preferred_link(0, ["5g"])
    assert result is None or result == "5g"   # graceful fallback
