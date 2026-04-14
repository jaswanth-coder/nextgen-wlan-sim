"""
MetricsCollector — periodic sampler for per-node, per-link throughput/latency.
Hooks into the DES engine as an observer and writes interval CSV rows.
"""

from __future__ import annotations

import csv
import os
import logging
from typing import TYPE_CHECKING

from nxwlansim.core.engine import OBSERVE

if TYPE_CHECKING:
    from nxwlansim.core.engine import SimulationEngine
    from nxwlansim.core.registry import NodeRegistry
    from nxwlansim.core.config import SimConfig

logger = logging.getLogger(__name__)

# Sampling interval: 10 ms default
DEFAULT_INTERVAL_NS = 10_000_000


class MetricsCollector:
    """
    Samples throughput, latency, retransmissions at fixed intervals.
    Writes one CSV row per node per interval.
    Pushes samples to SimViz if visualization is enabled.
    """

    def __init__(
        self,
        config: "SimConfig",
        registry: "NodeRegistry",
        interval_ns: int = DEFAULT_INTERVAL_NS,
        viz=None,
    ):
        self._config = config
        self._registry = registry
        self._interval_ns = interval_ns
        self._csv_path = os.path.join(config.obs.output_dir, "metrics.csv")
        self._csv_file = None
        self._csv_writer = None
        self._viz = viz   # SimViz instance or None

        # Per-node byte counters, reset each interval
        self._bytes_in_interval: dict[str, int] = {
            n.node_id: 0 for n in registry
        }
        self._frames_in_interval: dict[str, int] = {
            n.node_id: 0 for n in registry
        }
        self._npca_opportunities: dict[str, int] = {n.node_id: 0 for n in registry}
        self._npca_used: dict[str, int]          = {n.node_id: 0 for n in registry}
        self._npca_bytes_gained: dict[str, int]  = {n.node_id: 0 for n in registry}
        self._last_sample_ns: int = 0

        if config.obs.csv:
            os.makedirs(config.obs.output_dir, exist_ok=True)
            self._csv_file = open(self._csv_path, "w", newline="")
            self._csv_writer = csv.writer(self._csv_file)
            self._csv_writer.writerow([
                "time_us", "node_id", "node_type", "link_id",
                "throughput_mbps", "frames", "bytes",
                "mcs", "snr_db",
                "npca_opportunities", "npca_used", "npca_gain_mbps",
            ])

    def start(self, engine: "SimulationEngine") -> None:
        """Schedule the first periodic sample event."""
        engine.schedule_after(
            delay_ns=self._interval_ns,
            callback=self._sample,
            priority=OBSERVE,
            engine_ref=engine,
        )

    def record_tx_event(self, node_id: str, bytes_sent: int) -> None:
        """Called by TXOPEngine on each successful TX."""
        if node_id in self._bytes_in_interval:
            self._bytes_in_interval[node_id] += bytes_sent
            self._frames_in_interval[node_id] += 1

    def record_npca_event(self, node_id: str, used: bool, bytes_gained: int = 0) -> None:
        """Called by TXOPEngine when NPCA is evaluated."""
        if node_id in self._npca_opportunities:
            self._npca_opportunities[node_id] += 1
            if used:
                self._npca_used[node_id] += 1
                self._npca_bytes_gained[node_id] += bytes_gained

    def _sample(self, engine: "SimulationEngine", engine_ref, **_) -> None:
        now_us = engine.now_ns / 1_000.0
        interval_s = self._interval_ns / 1e9

        for node in self._registry:
            nid = node.node_id
            b = self._bytes_in_interval.get(nid, 0)
            f = self._frames_in_interval.get(nid, 0)
            tput_mbps = (b * 8) / interval_s / 1e6

            # Get current channel state for first link (summary metric)
            mcs, snr = "", ""
            if node.links and node.phy:
                try:
                    link_id = node.links[0]
                    peer = node.associated_ap if hasattr(node, "associated_ap") and node.associated_ap else "ap0"
                    ch = node.phy.get_channel_state(nid, peer, link_id)
                    mcs = ch.mcs_index
                    snr = f"{ch.snr_db:.1f}"
                except Exception:
                    pass

            if self._csv_writer and (b > 0 or f > 0):
                npca_opp  = self._npca_opportunities.get(nid, 0)
                npca_used = self._npca_used.get(nid, 0)
                npca_gain = self._npca_bytes_gained.get(nid, 0) * 8 / interval_s / 1e6
                self._csv_writer.writerow([
                    f"{now_us:.1f}", nid, node.node_type,
                    ",".join(node.links),
                    f"{tput_mbps:.3f}", f, b,
                    mcs, snr,
                    npca_opp, npca_used, f"{npca_gain:.3f}",
                ])
                self._csv_file.flush()

            # Push to viz
            if self._viz and tput_mbps > 0:
                self._viz.on_sample(
                    node_id=nid,
                    time_us=now_us,
                    throughput_mbps=tput_mbps,
                    link_id=",".join(node.links),
                )

            # Reset counters
            self._bytes_in_interval[nid] = 0
            self._frames_in_interval[nid] = 0

        self._last_sample_ns = engine.now_ns

        # Re-schedule next sample
        engine_ref.schedule_after(
            delay_ns=self._interval_ns,
            callback=self._sample,
            priority=OBSERVE,
            engine_ref=engine_ref,
        )

    def close(self) -> None:
        if self._csv_file:
            self._csv_file.close()
