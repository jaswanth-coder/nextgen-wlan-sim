"""Unit tests for NPCA coordination — secondary NAV propagation."""
from unittest.mock import MagicMock
import pytest
from nxwlansim.mac.mlo import LinkContext
from nxwlansim.mac.npca import NPCAEngine, N_SUBCHANNELS


def _make_node(node_id, link_ids=("6g",)):
    ctx_map = {}
    for lid in link_ids:
        class _FakeNode:
            pass
        ctx = LinkContext(lid, _FakeNode())
        ctx_map[lid] = ctx
    node = MagicMock()
    node.node_id = node_id
    node.mlo_manager.links = ctx_map
    return node, ctx_map


def test_coordinate_sets_secondary_nav_on_neighbours():
    sender, _ = _make_node("sta0", ("6g",))
    neighbour, n_ctx = _make_node("sta1", ("6g",))

    engine = MagicMock()
    engine.now_ns = 0
    engine._registry = [sender, neighbour]

    npca = NPCAEngine(sender)
    npca.coordinate("6g", duration_ns=5_000_000, engine=engine)

    # Secondary subchannels (1,2,3) should be blocked on neighbour
    free_after = n_ctx["6g"].free_subchannels(now_ns=1_000_000, n_subchannels=4)
    assert 0 in free_after        # primary unaffected
    assert 1 not in free_after    # secondary blocked
    assert 2 not in free_after
    assert 3 not in free_after


def test_coordinate_does_not_block_sender_itself():
    sender, s_ctx = _make_node("sta0", ("6g",))
    engine = MagicMock()
    engine.now_ns = 0
    engine._registry = [sender]

    npca = NPCAEngine(sender)
    npca.coordinate("6g", duration_ns=5_000_000, engine=engine)
    # Sender's own context is not touched
    free = s_ctx["6g"].free_subchannels(now_ns=1_000_000, n_subchannels=4)
    assert free == [0, 1, 2, 3]


def test_secondary_nav_expires():
    sender, _ = _make_node("sta0", ("6g",))
    neighbour, n_ctx = _make_node("sta1", ("6g",))
    engine = MagicMock()
    engine.now_ns = 0
    engine._registry = [sender, neighbour]

    NPCAEngine(sender).coordinate("6g", duration_ns=1_000_000, engine=engine)

    free_during = n_ctx["6g"].free_subchannels(now_ns=500_000)
    free_after  = n_ctx["6g"].free_subchannels(now_ns=2_000_000)
    assert 1 not in free_during
    assert 1 in free_after
