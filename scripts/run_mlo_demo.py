#!/usr/bin/env python3
"""
run_mlo_demo.py  —  Simple MLO (Multi-Link Operation) demo script
===================================================================

Scenario
--------
  1 AP + 3 STAs, all running IEEE 802.11be STR (Simultaneous Transmit & Receive)
  over two links: 5 GHz + 6 GHz.

  STA layout (ring, radius 8 m):
      sta0  →  AP  : 200 Mbps UDP/CBR  (Best Effort)
      sta1  →  AP  : 100 Mbps UDP/CBR  (Video)
      sta2  →  AP  :   0.064 Mbps VoIP (Voice)

  Simulation duration : 300 ms
  Output directory    : results/mlo_demo/

Outputs
-------
  - Console: per-node throughput table
  - results/mlo_demo/metrics.csv
  - results/mlo_demo/throughput_per_node.png
  - results/mlo_demo/topology.png
  - results/mlo_demo/link_states.png   (if link-state events fired)

Run
---
  python scripts/run_mlo_demo.py
"""

import logging
import os
import sys

# Make sure the package is importable when running from the repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nxwlansim.core.config import (
    SimConfig,
    SimulationConfig,
    PhyConfig,
    NetworkConfig,
    ObsConfig,
    NodeConfig,
    TrafficConfig,
)
from nxwlansim.core.engine import SimulationEngine

# ---------------------------------------------------------------------------
# Logging — INFO level so progress is visible on the terminal
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)

OUT_DIR = "results/mlo_demo"


def build_config() -> SimConfig:
    """Construct the simulation config for a 1-AP / 3-STA MLO-STR scenario."""

    nodes = [
        # AP at origin, two links, STR mode
        NodeConfig(
            id="ap0",
            type="ap",
            links=["5g", "6g"],
            mlo_mode="str",
            position=[0.0, 0.0],
        ),
        # Three STAs arranged in a triangle around the AP (radius 8 m)
        NodeConfig(
            id="sta0",
            type="sta",
            links=["5g", "6g"],
            mlo_mode="str",
            position=[8.0, 0.0],
        ),
        NodeConfig(
            id="sta1",
            type="sta",
            links=["5g", "6g"],
            mlo_mode="str",
            position=[-4.0, 6.93],
        ),
        NodeConfig(
            id="sta2",
            type="sta",
            links=["5g", "6g"],
            mlo_mode="str",
            position=[-4.0, -6.93],
        ),
    ]

    traffic = [
        TrafficConfig(src="sta0", dst="ap0", type="udp_cbr",  rate_mbps=200.0,  ac="BE"),
        TrafficConfig(src="sta1", dst="ap0", type="udp_cbr",  rate_mbps=100.0,  ac="VI"),
        TrafficConfig(src="sta2", dst="ap0", type="voip",     rate_mbps=0.064,  ac="VO"),
    ]

    return SimConfig(
        simulation=SimulationConfig(duration_us=300_000, seed=42),   # 300 ms
        phy=PhyConfig(backend="tgbe", channel_model="D"),
        network=NetworkConfig(mode="bss"),
        obs=ObsConfig(
            log=True,
            csv=True,
            pcap=False,
            viz=True,          # <-- enables PNG plots
            output_dir=OUT_DIR,
        ),
        nodes=nodes,
        traffic=traffic,
    )


def print_summary(results) -> None:
    """Pretty-print the results summary with a clear header/footer."""
    sep = "=" * 65
    print()
    print(sep)
    print("  MLO-STR Demo  —  Simulation Complete")
    print(sep)
    print(results.summary())
    print(sep)
    print()
    print(f"  Plots saved to : {OUT_DIR}/")
    print(f"    throughput_per_node.png")
    print(f"    topology.png")
    print(f"    link_states.png  (if link-state events were recorded)")
    print(sep)
    print()


def main() -> None:
    print()
    print("=" * 65)
    print("  nxwlansim  —  IEEE 802.11be MLO Demo")
    print("  Scenario : 1 AP + 3 STAs, STR mode, 5 GHz + 6 GHz, 300 ms")
    print("=" * 65)
    print()

    cfg = build_config()
    engine = SimulationEngine(cfg)

    print("  Running simulation …")
    results = engine.run()

    print_summary(results)


if __name__ == "__main__":
    main()
