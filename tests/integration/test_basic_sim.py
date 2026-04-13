"""
Integration tests: full YAML → sim run → assert basic invariants.
These run without MATLAB and validate the DES engine, node build, and output.
"""

import os
import pytest
import nxwlansim as nx
from nxwlansim.core.config import SimConfig


EXAMPLES_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "configs", "examples"
)


def test_str_basic_runs():
    cfg = SimConfig.from_yaml(os.path.join(EXAMPLES_DIR, "mlo_str_basic.yaml"))
    cfg.simulation.duration_us = 10_000   # short run for CI
    cfg.obs.csv = False
    sim = nx.Simulation(cfg)
    results = sim.run()
    assert results is not None
    summary = results.summary()
    assert "Duration" in summary
    assert "APs" in summary


def test_emlsr_basic_runs():
    cfg = SimConfig.from_yaml(os.path.join(EXAMPLES_DIR, "mlo_emlsr_2sta.yaml"))
    cfg.simulation.duration_us = 10_000
    cfg.obs.csv = False
    cfg.obs.pcap = False
    sim = nx.Simulation(cfg)
    results = sim.run()
    assert results is not None


def test_emlmr_multiap_runs():
    cfg = SimConfig.from_yaml(os.path.join(EXAMPLES_DIR, "mlo_emlmr_multiap.yaml"))
    cfg.simulation.duration_us = 10_000
    cfg.obs.csv = False
    cfg.obs.pcap = False
    sim = nx.Simulation(cfg)
    results = sim.run()
    assert results is not None


def test_quick_scenario_api():
    sim = nx.quick_scenario(mode="str", n_links=2, n_stas=3, duration_us=5_000)
    results = sim.run()
    assert results is not None


@pytest.mark.matlab
def test_matlab_fallback_when_unavailable():
    """If matlab.engine not installed, TGbeChannel fallback should be silent."""
    import warnings
    cfg = SimConfig.quick_build(duration_us=5_000)
    cfg.phy.backend = "matlab"
    cfg.phy.matlab_mode = "medium"
    sim = nx.Simulation(cfg)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        results = sim.run()
    assert results is not None
    # Either ran fine with MATLAB or fell back gracefully
