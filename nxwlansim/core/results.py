"""SimResults — collects and presents simulation output metrics."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nxwlansim.core.engine import SimulationEngine
    from nxwlansim.core.registry import NodeRegistry
    from nxwlansim.core.config import SimConfig


class SimResults:
    def __init__(self, engine: "SimulationEngine", registry: "NodeRegistry", config: "SimConfig"):
        self._engine = engine
        self._registry = registry
        self._config = config

    def summary(self) -> str:
        lines = [
            f"=== Simulation Results ===",
            f"Duration : {self._engine.clock_ns / 1e6:.3f} ms",
            f"Nodes    : {len(self._registry)} "
            f"({len(self._registry.aps())} APs, {len(self._registry.stas())} STAs)",
        ]
        # Throughput per node will be populated by observer metrics in later phases
        return "\n".join(lines)

    def plot_throughput(self) -> None:
        """Plot per-STA throughput (requires obs.csv=True and matplotlib)."""
        import os
        csv_path = os.path.join(self._config.obs.output_dir, "metrics.csv")
        if not os.path.exists(csv_path):
            print("No CSV metrics found. Set obs.csv: true in config.")
            return
        import csv
        import matplotlib.pyplot as plt
        # Placeholder — will be populated in Phase 1 implementation
        print(f"[plot_throughput] Reading from {csv_path}")
