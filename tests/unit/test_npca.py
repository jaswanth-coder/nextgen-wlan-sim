"""Unit tests for NPCA — sub-channel NAV and NPCAEngine decisions."""
import pytest
from nxwlansim.mac.mlo import LinkContext, LinkState


# ---- LinkContext sub-NAV tests ----

def _ctx(link_id="6g"):
    class _FakeNode:
        node_id = "sta0"
        mlo_mode = "str"
    return LinkContext(link_id, _FakeNode())


def test_all_subchannels_free_initially():
    ctx = _ctx()
    free = ctx.free_subchannels(now_ns=0, n_subchannels=4)
    assert free == [0, 1, 2, 3]


def test_set_sub_nav_blocks_subchannel():
    ctx = _ctx()
    ctx.set_sub_nav(subchannel_id=0, duration_ns=1_000_000, now_ns=0)
    free = ctx.free_subchannels(now_ns=500_000, n_subchannels=4)
    assert 0 not in free
    assert 1 in free


def test_sub_nav_clears_after_expiry():
    ctx = _ctx()
    ctx.set_sub_nav(subchannel_id=1, duration_ns=1_000_000, now_ns=0)
    free_during = ctx.free_subchannels(now_ns=500_000, n_subchannels=4)
    free_after = ctx.free_subchannels(now_ns=2_000_000, n_subchannels=4)
    assert 1 not in free_during
    assert 1 in free_after


def test_sub_nav_max_of_two_calls():
    ctx = _ctx()
    ctx.set_sub_nav(0, 1_000_000, now_ns=0)
    ctx.set_sub_nav(0, 5_000_000, now_ns=0)   # longer one should win
    free = ctx.free_subchannels(now_ns=2_000_000, n_subchannels=4)
    assert 0 not in free


# ---- NPCAEngine tests ----
from unittest.mock import MagicMock
from nxwlansim.mac.npca import NPCAEngine, NPCADecision


def _node_with_link(link_id="6g", now_ns=0, busy_subchannels=None):
    """Create a fake node whose LinkContext has specified subchannels busy."""
    ctx = _ctx(link_id)
    busy = busy_subchannels or []
    for sc in busy:
        ctx.set_sub_nav(sc, duration_ns=10_000_000, now_ns=now_ns)

    node = MagicMock()
    node.node_id = "sta0"
    node.mlo_manager.links = {link_id: ctx}
    return node


def test_no_npca_when_primary_free():
    node = _node_with_link("6g", busy_subchannels=[])
    engine = NPCAEngine(node)
    decision = engine.evaluate("6g", now_ns=0)
    assert decision.use_npca is False
    assert decision.punctured_mask == 0


def test_npca_triggered_when_primary_busy():
    node = _node_with_link("6g", busy_subchannels=[0])  # primary busy
    engine = NPCAEngine(node)
    decision = engine.evaluate("6g", now_ns=0)
    assert decision.use_npca is True
    assert decision.punctured_mask & 1   # subchannel 0 punctured
    assert decision.effective_bw_mhz > 0


def test_no_npca_when_all_busy():
    node = _node_with_link("6g", busy_subchannels=[0, 1, 2, 3])
    engine = NPCAEngine(node)
    decision = engine.evaluate("6g", now_ns=0)
    assert decision.use_npca is False
    assert decision.effective_bw_mhz == 0.0


def test_effective_bw_proportional_to_free_secondaries():
    node = _node_with_link("6g", busy_subchannels=[0, 1])  # 2 busy, 2 free
    engine = NPCAEngine(node)
    decision = engine.evaluate("6g", now_ns=0)
    assert decision.use_npca is True
    assert decision.effective_bw_mhz == 2 * 80   # 2 free × 80 MHz
