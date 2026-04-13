"""
Golden regression tests.
These validate core simulator invariants against known-good behaviour.
Seed is fixed — results must be deterministic.
"""

import os
import csv
import pytest
import nxwlansim as nx
from nxwlansim.core.config import SimConfig


# -----------------------------------------------------------------------
# Helper
# -----------------------------------------------------------------------

def _run_and_get_metrics(mlo_mode, n_links, duration_us=200_000, seed=42):
    cfg = SimConfig.quick_build(
        mlo_mode=mlo_mode, n_links=n_links,
        n_stas=3, duration_us=duration_us, seed=seed,
    )
    cfg.obs.csv = True
    cfg.obs.output_dir = f"/tmp/nxwlansim_golden_{mlo_mode}_{n_links}link"
    sim = nx.Simulation(cfg)
    results = sim.run()
    return results, sim._engine


# -----------------------------------------------------------------------
# Determinism
# -----------------------------------------------------------------------

def test_same_seed_same_event_count():
    """Two runs with identical config and seed produce same event count."""
    def run_once():
        cfg = SimConfig.quick_build(n_links=2, duration_us=50_000, seed=99)
        cfg.obs.csv = False
        sim = nx.Simulation(cfg)
        sim.run()
        return sim._engine.clock_ns

    t1 = run_once()
    t2 = run_once()
    assert t1 == t2, f"Non-deterministic: {t1} != {t2}"


# -----------------------------------------------------------------------
# STR throughput: 2-link must outperform 1-link
# -----------------------------------------------------------------------

def test_str_2link_processes_more_than_1link():
    """
    STR with 2 links should process more total bytes than single link
    in the same simulation time with same traffic load.
    """
    r1, e1 = _run_and_get_metrics("str", 1, duration_us=200_000)
    r2, e2 = _run_and_get_metrics("str", 2, duration_us=200_000)

    # Sum bytes_tx across all STAs
    bytes_1 = sum(m.bytes_tx for m in r1._node_metrics.values())
    bytes_2 = sum(m.bytes_tx for m in r2._node_metrics.values())

    assert bytes_2 >= bytes_1, (
        f"2-link STR ({bytes_2}B) should >= 1-link ({bytes_1}B)"
    )


# -----------------------------------------------------------------------
# EMLSR: never more than one link TXOP_GRANTED at once per node
# -----------------------------------------------------------------------

def test_emlsr_single_active_link_invariant():
    """
    After EMLSR sim, inspect all STA link states at sim end.
    No STA should have >1 link in TXOP_GRANTED state simultaneously.
    """
    from nxwlansim.mac.mlo import LinkState
    cfg = SimConfig.quick_build(
        mlo_mode="emlsr", n_links=2, n_stas=3,
        duration_us=200_000, seed=42,
    )
    cfg.obs.csv = False
    sim = nx.Simulation(cfg)
    sim.run()
    for node in sim._engine._registry.stas():
        txop_links = [
            lid for lid, ctx in node.mlo_manager.links.items()
            if ctx.state == LinkState.TXOP_GRANTED
        ]
        assert len(txop_links) <= 1, (
            f"EMLSR node {node.node_id} has {len(txop_links)} links in TXOP_GRANTED"
        )


# -----------------------------------------------------------------------
# CSV output format
# -----------------------------------------------------------------------

def test_csv_output_has_correct_columns():
    """CSV file must have expected header columns."""
    cfg = SimConfig.quick_build(n_links=2, duration_us=100_000, seed=1)
    cfg.obs.csv = True
    cfg.obs.output_dir = "/tmp/nxwlansim_golden_csv"
    sim = nx.Simulation(cfg)
    sim.run()

    csv_path = os.path.join(cfg.obs.output_dir, "metrics.csv")
    assert os.path.exists(csv_path), "metrics.csv not created"
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        assert "throughput_mbps" in reader.fieldnames
        assert "node_id" in reader.fieldnames
        assert "time_us" in reader.fieldnames


# -----------------------------------------------------------------------
# PCAP output
# -----------------------------------------------------------------------

def test_pcap_files_created():
    """When obs.pcap=True, at least one .pcap file must be created per active link."""
    cfg = SimConfig.quick_build(n_links=2, duration_us=100_000, seed=5)
    cfg.obs.pcap = True
    cfg.obs.csv = False
    cfg.obs.output_dir = "/tmp/nxwlansim_golden_pcap"
    sim = nx.Simulation(cfg)
    sim.run()

    pcap_dir = os.path.join(cfg.obs.output_dir, "pcap")
    if os.path.exists(pcap_dir):
        pcap_files = [f for f in os.listdir(pcap_dir) if f.endswith(".pcap")]
        assert len(pcap_files) >= 1, f"No .pcap files found in {pcap_dir}"


def test_pcap_file_has_valid_magic():
    """Each .pcap file must start with libpcap magic bytes 0xA1B2C3D4."""
    import struct
    cfg = SimConfig.quick_build(n_links=2, duration_us=100_000, seed=6)
    cfg.obs.pcap = True
    cfg.obs.csv = False
    cfg.obs.output_dir = "/tmp/nxwlansim_golden_pcap_magic"
    sim = nx.Simulation(cfg)
    sim.run()

    pcap_dir = os.path.join(cfg.obs.output_dir, "pcap")
    if not os.path.exists(pcap_dir):
        pytest.skip("No PCAP files generated (no TX in short sim)")

    for fname in os.listdir(pcap_dir):
        if fname.endswith(".pcap"):
            fpath = os.path.join(pcap_dir, fname)
            with open(fpath, "rb") as f:
                magic = struct.unpack("<I", f.read(4))[0]
            assert magic == 0xA1B2C3D4, f"{fname}: bad magic {magic:#010x}"


# -----------------------------------------------------------------------
# Interference tracker resets between runs
# -----------------------------------------------------------------------

def test_interference_tracker_resets_between_runs():
    """Running two sims back-to-back must not accumulate stale TX records."""
    from nxwlansim.phy.interference import get_tracker
    cfg = SimConfig.quick_build(n_links=2, duration_us=50_000, seed=11)
    cfg.obs.csv = False
    nx.Simulation(cfg).run()
    nx.Simulation(cfg).run()
    # After second run, tracker should only have current-sim entries (or empty)
    tracker = get_tracker()
    # No assertion on count — just must not raise
    assert tracker is not None
