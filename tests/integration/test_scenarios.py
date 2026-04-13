"""
Scenario integration tests — runs each example YAML config.
Validates that all scenarios load, run, and produce correct output structure.
"""

import os
import pytest
import nxwlansim as nx
from nxwlansim.core.config import SimConfig

EXAMPLES = os.path.join(os.path.dirname(__file__), "..", "..", "configs", "examples")


def _run_scenario(filename: str, duration_us: int = 20_000) -> "SimResults":
    cfg = SimConfig.from_yaml(os.path.join(EXAMPLES, filename))
    cfg.simulation.duration_us = duration_us   # short run for CI
    cfg.obs.csv = False
    cfg.obs.pcap = False
    cfg.obs.viz = False
    return nx.Simulation(cfg).run()


# ------------------------------------------------------------------
# All example scenarios must run without exception
# ------------------------------------------------------------------

def test_mlo_str_basic():
    r = _run_scenario("mlo_str_basic.yaml")
    assert r is not None

def test_mlo_emlsr_2sta():
    r = _run_scenario("mlo_emlsr_2sta.yaml")
    assert r is not None

def test_mlo_emlmr_multiap():
    r = _run_scenario("mlo_emlmr_multiap.yaml")
    assert r is not None

def test_hidden_node():
    r = _run_scenario("hidden_node.yaml")
    assert r is not None

def test_heavy_load_str():
    r = _run_scenario("heavy_load_str.yaml")
    assert r is not None

def test_mixed_ac_priority():
    r = _run_scenario("mixed_ac_priority.yaml")
    assert r is not None

def test_emlsr_vs_str_comparison():
    r = _run_scenario("emlsr_vs_str_comparison.yaml")
    assert r is not None

def test_voip_tid_steering():
    r = _run_scenario("voip_tid_steering.yaml")
    assert r is not None

def test_multiap_roaming():
    r = _run_scenario("multiap_roaming.yaml")
    assert r is not None


# ------------------------------------------------------------------
# Scenario-specific invariants
# ------------------------------------------------------------------

def test_mixed_ac_has_4_access_categories():
    """mixed_ac_priority.yaml defines 4 distinct AC types."""
    cfg = SimConfig.from_yaml(os.path.join(EXAMPLES, "mixed_ac_priority.yaml"))
    acs = {t.ac for t in cfg.traffic}
    assert acs == {"VO", "VI", "BE", "BK"}


def test_hidden_node_has_2_stas_same_link():
    """hidden_node.yaml: both STAs use the same links → contention."""
    cfg = SimConfig.from_yaml(os.path.join(EXAMPLES, "hidden_node.yaml"))
    stas = [n for n in cfg.nodes if n.type == "sta"]
    assert len(stas) == 2
    assert stas[0].links == stas[1].links


def test_multiap_has_2_aps():
    cfg = SimConfig.from_yaml(os.path.join(EXAMPLES, "multiap_roaming.yaml"))
    aps = [n for n in cfg.nodes if n.type == "ap"]
    assert len(aps) == 2


def test_emlsr_vs_str_has_all_3_mlo_modes():
    cfg = SimConfig.from_yaml(os.path.join(EXAMPLES, "emlsr_vs_str_comparison.yaml"))
    modes = {n.mlo_mode for n in cfg.nodes if n.type == "sta"}
    assert "str" in modes
    assert "emlsr" in modes
    assert "emlmr" in modes


def test_voip_tid_steering_has_vo_traffic():
    cfg = SimConfig.from_yaml(os.path.join(EXAMPLES, "voip_tid_steering.yaml"))
    vo_flows = [t for t in cfg.traffic if t.ac == "VO"]
    assert len(vo_flows) >= 1


# ------------------------------------------------------------------
# Viz output integration
# ------------------------------------------------------------------

def test_viz_creates_png_files():
    """When obs.viz=True, throughput_per_node.png must be created."""
    cfg = SimConfig.from_yaml(os.path.join(EXAMPLES, "mixed_ac_priority.yaml"))
    cfg.simulation.duration_us = 50_000
    cfg.obs.viz = True
    cfg.obs.csv = False
    cfg.obs.pcap = False
    cfg.obs.output_dir = "/tmp/nxwlansim_scenario_viz"
    nx.Simulation(cfg).run()
    assert os.path.exists(os.path.join(cfg.obs.output_dir, "throughput_per_node.png"))


def test_topology_png_created_with_registry():
    """Topology plot requires registry — verify it's saved."""
    cfg = SimConfig.from_yaml(os.path.join(EXAMPLES, "mlo_str_basic.yaml"))
    cfg.simulation.duration_us = 20_000
    cfg.obs.viz = True
    cfg.obs.csv = False
    cfg.obs.pcap = False
    cfg.obs.output_dir = "/tmp/nxwlansim_topo_viz"
    nx.Simulation(cfg).run()
    assert os.path.exists(os.path.join(cfg.obs.output_dir, "topology.png"))
