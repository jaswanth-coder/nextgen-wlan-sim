"""SimResults — collects and presents simulation output metrics."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nxwlansim.core.engine import SimulationEngine
    from nxwlansim.core.registry import NodeRegistry
    from nxwlansim.core.config import SimConfig


@dataclass
class NodeMetrics:
    node_id: str
    frames_tx: int = 0
    bytes_tx: int = 0
    frames_rx: int = 0
    bytes_rx: int = 0
    retransmissions: int = 0
    ba_timeouts: int = 0

    def throughput_mbps(self, duration_us: float) -> float:
        if duration_us <= 0:
            return 0.0
        return self.bytes_tx * 8 / (duration_us * 1e-6) / 1e6


class SimResults:
    def __init__(
        self,
        engine: "SimulationEngine",
        registry: "NodeRegistry",
        config: "SimConfig",
    ):
        self._engine = engine
        self._registry = registry
        self._config = config
        self._node_metrics: dict[str, NodeMetrics] = {
            n.node_id: NodeMetrics(n.node_id) for n in registry
        }

    def record_tx(self, node_id: str, bytes_sent: int) -> None:
        m = self._node_metrics.get(node_id)
        if m:
            m.frames_tx += 1
            m.bytes_tx += bytes_sent

    def record_ba_timeout(self, node_id: str) -> None:
        m = self._node_metrics.get(node_id)
        if m:
            m.ba_timeouts += 1

    def summary(self) -> str:
        dur_us = self._engine.clock_ns / 1_000.0
        aps = self._registry.aps()
        stas = self._registry.stas()
        lines = [
            "=== Simulation Results ===",
            f"Duration  : {dur_us / 1000:.3f} ms",
            f"Nodes     : {len(self._registry)} ({len(aps)} APs, {len(stas)} STAs)",
            "",
            f"{'Node':<12} {'Frames TX':>10} {'Bytes TX':>12} {'Tput (Mbps)':>12} {'BA timeouts':>12}",
            "-" * 62,
        ]
        for node_id, m in sorted(self._node_metrics.items()):
            tput = m.throughput_mbps(dur_us)
            lines.append(
                f"{node_id:<12} {m.frames_tx:>10} {m.bytes_tx:>12} {tput:>12.2f} {m.ba_timeouts:>12}"
            )
        return "\n".join(lines)

    def plot_throughput(self) -> None:
        import os
        csv_path = os.path.join(self._config.obs.output_dir, "metrics.csv")
        if not os.path.exists(csv_path):
            print("No CSV metrics found. Set obs.csv: true in config.")
            return
        try:
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots()
            ax.set_xlabel("Time (µs)")
            ax.set_ylabel("Throughput (Mbps)")
            ax.set_title("Per-node throughput — nxwlansim")
            plt.show()
        except ImportError:
            print("matplotlib not installed.")
