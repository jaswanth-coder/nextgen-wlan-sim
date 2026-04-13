"""
SimViz — real-time and post-sim visualization.

Two rendering modes:
  matplotlib : live updating plot during sim + final static PNG export
  flask      : local web dashboard (stub, Phase 2)

Wired to MetricsCollector: receives throughput samples every 10ms sim-time.
Also provides topology diagram and link-state diagrams.

Usage:
    viz = SimViz(config, registry)
    viz.activate()               # call before sim.run()
    # ... sim runs, viz.on_sample() called by MetricsCollector ...
    viz.finalize("results/")     # saves PNG + topology SVG after sim
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nxwlansim.core.config import SimConfig
    from nxwlansim.core.registry import NodeRegistry

logger = logging.getLogger(__name__)


class SimViz:
    """Visualization backend — matplotlib live plots + topology."""

    def __init__(self, config: "SimConfig", registry: "NodeRegistry | None" = None):
        self._config = config
        self._registry = registry
        self._mode = "matplotlib"

        # Time-series data: node_id → [(time_us, throughput_mbps)]
        self._throughput: dict[str, list[tuple[float, float]]] = {}
        # Link state snapshots: [(time_us, node_id, link_id, state)]
        self._link_states: list[tuple] = []

        self._fig = None
        self._axes = None
        self._active = False

    # ------------------------------------------------------------------
    # Activation
    # ------------------------------------------------------------------

    def activate(self) -> None:
        """Prepare matplotlib figure. Call before sim.run()."""
        try:
            import matplotlib
            matplotlib.use("Agg")   # non-interactive backend — safe in all envs
            import matplotlib.pyplot as plt
            self._plt = plt
            self._active = True
            logger.info("[Viz] matplotlib backend ready (Agg)")
        except ImportError:
            logger.warning("[Viz] matplotlib not installed — visualization disabled.")
            self._active = False

    # ------------------------------------------------------------------
    # Live data ingestion (called by MetricsCollector)
    # ------------------------------------------------------------------

    def on_sample(
        self,
        node_id: str,
        time_us: float,
        throughput_mbps: float,
        link_id: str = "",
    ) -> None:
        """Record a throughput sample point."""
        if node_id not in self._throughput:
            self._throughput[node_id] = []
        self._throughput[node_id].append((time_us, throughput_mbps))

    def on_link_state(self, time_us: float, node_id: str, link_id: str, state: str) -> None:
        """Record a link state change event."""
        self._link_states.append((time_us, node_id, link_id, state))

    # ------------------------------------------------------------------
    # Finalize — called after sim.run()
    # ------------------------------------------------------------------

    def finalize(self, output_dir: str | None = None) -> None:
        """
        Generate and save all plots to output_dir.
        Creates:
          - throughput_per_node.png
          - topology.png
          - link_states.png  (if state data available)
        """
        if not self._active:
            return

        out = output_dir or self._config.obs.output_dir
        os.makedirs(out, exist_ok=True)

        self._plot_throughput(out)
        if self._registry:
            self._plot_topology(out)
        if self._link_states:
            self._plot_link_states(out)

        logger.info("[Viz] Plots saved to %s", out)

    # ------------------------------------------------------------------
    # Throughput plot
    # ------------------------------------------------------------------

    def _plot_throughput(self, out: str) -> None:
        plt = self._plt
        fig, axes = plt.subplots(2, 1, figsize=(12, 8))
        fig.suptitle("nxwlansim — Per-Node Throughput", fontsize=14, fontweight="bold")

        ax_ts  = axes[0]   # time-series
        ax_bar = axes[1]   # aggregate bar chart

        colors = plt.cm.tab10.colors
        node_colors: dict[str, str] = {}

        # --- Time series ---
        ax_ts.set_xlabel("Simulation Time (ms)")
        ax_ts.set_ylabel("Throughput (Mbps)")
        ax_ts.set_title("Per-node throughput over time")
        ax_ts.grid(True, alpha=0.3)

        avg_tput: dict[str, float] = {}
        for i, (node_id, samples) in enumerate(sorted(self._throughput.items())):
            if not samples:
                continue
            color = colors[i % len(colors)]
            node_colors[node_id] = color
            times_ms = [t / 1000 for t, _ in samples]
            tputs = [tp for _, tp in samples]
            ax_ts.plot(times_ms, tputs, label=node_id, color=color, linewidth=1.5, alpha=0.85)
            avg_tput[node_id] = sum(tputs) / len(tputs) if tputs else 0.0

        if avg_tput:
            ax_ts.legend(loc="upper right", fontsize=8, ncol=2)

        # --- Bar chart ---
        ax_bar.set_xlabel("Node")
        ax_bar.set_ylabel("Average Throughput (Mbps)")
        ax_bar.set_title("Average throughput per node")
        ax_bar.grid(True, axis="y", alpha=0.3)

        if avg_tput:
            nodes = sorted(avg_tput.keys())
            values = [avg_tput[n] for n in nodes]
            bar_colors = [node_colors.get(n, "steelblue") for n in nodes]
            bars = ax_bar.bar(nodes, values, color=bar_colors, edgecolor="white", linewidth=0.5)
            for bar, val in zip(bars, values):
                ax_bar.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + max(values) * 0.01,
                    f"{val:.1f}",
                    ha="center", va="bottom", fontsize=8,
                )

        plt.tight_layout()
        path = os.path.join(out, "throughput_per_node.png")
        fig.savefig(path, dpi=120, bbox_inches="tight")
        plt.close(fig)
        logger.info("[Viz] Saved %s", path)

    # ------------------------------------------------------------------
    # Topology plot
    # ------------------------------------------------------------------

    def _plot_topology(self, out: str) -> None:
        plt = self._plt
        import math

        fig, ax = plt.subplots(figsize=(10, 8))
        ax.set_title("nxwlansim — Network Topology", fontsize=13, fontweight="bold")
        ax.set_xlabel("X position (m)")
        ax.set_ylabel("Y position (m)")
        ax.grid(True, alpha=0.2)
        ax.set_aspect("equal")

        aps  = self._registry.aps()
        stas = self._registry.stas()

        # Draw association lines first (behind nodes)
        for sta in stas:
            if sta.associated_ap:
                try:
                    ap = self._registry.get(sta.associated_ap)
                    ax.plot(
                        [sta.position[0], ap.position[0]],
                        [sta.position[1], ap.position[1]],
                        color="gray", linewidth=0.8, alpha=0.5, linestyle="--",
                    )
                except KeyError:
                    pass

        # Draw APs
        for ap in aps:
            ax.scatter(
                ap.position[0], ap.position[1],
                s=300, c="royalblue", zorder=5,
                marker="^", edgecolors="white", linewidths=1.5,
            )
            ax.annotate(
                ap.node_id,
                (ap.position[0], ap.position[1]),
                textcoords="offset points", xytext=(6, 6),
                fontsize=9, fontweight="bold", color="royalblue",
            )
            # Draw coverage circle (approximate)
            circle = plt.Circle(
                ap.position, 15, color="royalblue", fill=False,
                alpha=0.15, linestyle=":",
            )
            ax.add_patch(circle)

        # Draw STAs
        colors = plt.cm.tab10.colors
        for i, sta in enumerate(stas):
            color = colors[i % len(colors)]
            ax.scatter(
                sta.position[0], sta.position[1],
                s=150, c=[color], zorder=5,
                marker="o", edgecolors="white", linewidths=1.0,
            )
            label = f"{sta.node_id}\n({sta.mlo_mode})"
            ax.annotate(
                label,
                (sta.position[0], sta.position[1]),
                textcoords="offset points", xytext=(6, -12),
                fontsize=7, color="dimgray",
            )

        # Legend
        from matplotlib.lines import Line2D
        legend_elements = [
            Line2D([0], [0], marker="^", color="w", markerfacecolor="royalblue",
                   markersize=12, label="AP"),
            Line2D([0], [0], marker="o", color="w", markerfacecolor="gray",
                   markersize=10, label="STA"),
            Line2D([0], [0], color="gray", linestyle="--", label="Association"),
        ]
        ax.legend(handles=legend_elements, loc="upper left", fontsize=9)

        # MLO mode annotation
        mlo_modes = sorted({n.mlo_mode for n in list(aps) + list(stas)})
        ax.text(
            0.99, 0.01, f"MLO modes: {', '.join(mlo_modes)}",
            transform=ax.transAxes, fontsize=8, color="dimgray",
            ha="right", va="bottom",
        )

        plt.tight_layout()
        path = os.path.join(out, "topology.png")
        fig.savefig(path, dpi=120, bbox_inches="tight")
        plt.close(fig)
        logger.info("[Viz] Saved %s", path)

    # ------------------------------------------------------------------
    # Link state timeline
    # ------------------------------------------------------------------

    def _plot_link_states(self, out: str) -> None:
        plt = self._plt
        if not self._link_states:
            return

        # Group by (node_id, link_id)
        rows: dict[str, list] = {}
        for time_us, node_id, link_id, state in self._link_states:
            key = f"{node_id}/{link_id}"
            if key not in rows:
                rows[key] = []
            rows[key].append((time_us / 1000, state))   # ms

        state_color = {
            "IDLE": "lightgray",
            "BACKOFF": "khaki",
            "TXOP_GRANTED": "limegreen",
            "TRANSMITTING": "steelblue",
            "WAIT_BA": "salmon",
        }

        n_rows = len(rows)
        if n_rows == 0:
            return

        fig, ax = plt.subplots(figsize=(14, max(4, n_rows * 0.5 + 2)))
        ax.set_title("nxwlansim — Link State Timeline", fontsize=12, fontweight="bold")
        ax.set_xlabel("Simulation Time (ms)")
        ax.set_yticks(range(n_rows))
        ax.set_yticklabels(list(rows.keys()), fontsize=7)
        ax.grid(True, axis="x", alpha=0.3)

        for row_idx, (key, events) in enumerate(rows.items()):
            for j, (t_ms, state) in enumerate(events):
                t_end = events[j + 1][0] if j + 1 < len(events) else t_ms + 1
                width = max(t_end - t_ms, 0.05)
                color = state_color.get(state, "white")
                ax.barh(
                    row_idx, width, left=t_ms, height=0.6,
                    color=color, edgecolor="none", align="center",
                )

        # Legend
        from matplotlib.patches import Patch
        legend_patches = [
            Patch(color=c, label=s) for s, c in state_color.items()
        ]
        ax.legend(handles=legend_patches, loc="upper right", fontsize=8, ncol=3)

        plt.tight_layout()
        path = os.path.join(out, "link_states.png")
        fig.savefig(path, dpi=100, bbox_inches="tight")
        plt.close(fig)
        logger.info("[Viz] Saved %s", path)
