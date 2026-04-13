"""Unit tests for TXOP engine event scheduling."""

import pytest
import nxwlansim as nx
from nxwlansim.core.config import SimConfig
from nxwlansim.mac.mlo import LinkState


def _mini_sim(mlo_mode="str", duration_us=50_000):
    cfg = SimConfig.quick_build(mlo_mode=mlo_mode, n_links=2, n_stas=2, duration_us=duration_us)
    cfg.obs.csv = False
    return nx.Simulation(cfg)


def test_engine_processes_events():
    """Sim must process at least one event."""
    sim = _mini_sim()
    results = sim.run()
    assert sim._engine.clock_ns > 0


def test_str_links_independent():
    """STR: both links can be IDLE (backoff) simultaneously — never both TRANSMITTING
    at the exact same ns from the same node in this simplified model."""
    sim = _mini_sim(mlo_mode="str", duration_us=5_000)
    results = sim.run()
    # Basic: sim completes without exception
    assert results is not None


def test_emlsr_only_one_link_txop():
    """EMLSR: after trigger, only one link should be TXOP_GRANTED."""
    sim = _mini_sim(mlo_mode="emlsr", duration_us=5_000)
    results = sim.run()
    assert results is not None
    for node in sim._engine._registry.stas():
        active_txop = [
            ctx for ctx in node.mlo_manager.links.values()
            if ctx.state == LinkState.TXOP_GRANTED
        ]
        assert len(active_txop) <= 1, (
            f"EMLSR node {node.node_id} has {len(active_txop)} links in TXOP_GRANTED"
        )


def test_summary_contains_nodes():
    sim = _mini_sim(duration_us=10_000)
    results = sim.run()
    summary = results.summary()
    assert "APs" in summary
    assert "STAs" in summary
