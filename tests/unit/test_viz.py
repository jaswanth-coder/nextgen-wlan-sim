"""Unit tests for SimViz data collection and plot generation."""

import os
import pytest
import nxwlansim as nx
from nxwlansim.core.config import SimConfig
from nxwlansim.observe.viz import SimViz


class _MockConfig:
    class obs:
        output_dir = "/tmp/nxwlansim_viz_test"
        viz = True
        csv = False


def test_viz_on_sample_stores_data():
    cfg = _MockConfig()
    v = SimViz(cfg)
    v.on_sample("sta0", 10_000, 150.0, "6g")
    v.on_sample("sta0", 20_000, 160.0, "6g")
    v.on_sample("sta1", 10_000, 80.0, "5g")
    assert len(v._throughput["sta0"]) == 2
    assert len(v._throughput["sta1"]) == 1


def test_viz_on_link_state_stores_events():
    v = SimViz(_MockConfig())
    v.on_link_state(1000, "sta0", "6g", "TXOP_GRANTED")
    v.on_link_state(2000, "sta0", "6g", "TRANSMITTING")
    assert len(v._link_states) == 2


def test_viz_activate_sets_active_flag():
    v = SimViz(_MockConfig())
    v.activate()
    # matplotlib Agg backend should always succeed
    assert v._active is True


def test_viz_finalize_creates_throughput_png():
    v = SimViz(_MockConfig())
    v.activate()
    # Add some sample data
    for t in range(0, 100_000, 10_000):
        v.on_sample("sta0", t, 100.0 + t / 1000, "6g")
        v.on_sample("sta1", t, 50.0, "5g")

    out = "/tmp/nxwlansim_viz_unit"
    v.finalize(out)
    assert os.path.exists(os.path.join(out, "throughput_per_node.png"))


def test_viz_finalize_no_data_no_crash():
    """finalize() with empty data must not raise."""
    v = SimViz(_MockConfig())
    v.activate()
    v.finalize("/tmp/nxwlansim_viz_empty")


def test_viz_inactive_finalize_no_crash():
    """finalize() when matplotlib unavailable (inactive) must not raise."""
    v = SimViz(_MockConfig())
    v._active = False
    v.finalize("/tmp/nxwlansim_viz_inactive")


def test_viz_link_states_plot():
    v = SimViz(_MockConfig())
    v.activate()
    states = ["IDLE", "BACKOFF", "TXOP_GRANTED", "TRANSMITTING", "WAIT_BA", "IDLE"]
    for i, s in enumerate(states):
        v.on_link_state(i * 5000, "sta0", "6g", s)
        v.on_link_state(i * 5000, "sta0", "5g", s)

    out = "/tmp/nxwlansim_viz_link_states"
    v.finalize(out)
    assert os.path.exists(os.path.join(out, "link_states.png"))
