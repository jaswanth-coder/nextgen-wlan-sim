"""SimViz — matplotlib live plot + optional Flask dashboard stub."""

from __future__ import annotations
import logging

logger = logging.getLogger(__name__)


class SimViz:
    """
    Visualization backend.
    activate() starts matplotlib live update or Flask dashboard.
    """

    def __init__(self, mode: str = "matplotlib"):
        self._mode = mode
        self._throughput_data: dict[str, list] = {}

    def activate(self) -> None:
        if self._mode == "matplotlib":
            self._start_matplotlib()
        elif self._mode == "flask":
            self._start_flask()

    def record_throughput(self, node_id: str, time_us: float, mbps: float) -> None:
        if node_id not in self._throughput_data:
            self._throughput_data[node_id] = []
        self._throughput_data[node_id].append((time_us, mbps))

    def _start_matplotlib(self) -> None:
        try:
            import matplotlib.pyplot as plt
            self._fig, self._ax = plt.subplots()
            self._ax.set_xlabel("Time (µs)")
            self._ax.set_ylabel("Throughput (Mbps)")
            self._ax.set_title("Per-STA Throughput — nxwlansim")
            plt.ion()
            plt.show()
        except ImportError:
            logger.warning("matplotlib not installed — visualization disabled.")

    def _start_flask(self) -> None:
        logger.info("[Viz] Flask dashboard: Phase 1 stub — not yet implemented.")

    def finalize(self) -> None:
        """Plot final throughput after simulation ends."""
        try:
            import matplotlib.pyplot as plt
            for node_id, data in self._throughput_data.items():
                if data:
                    times, mbps = zip(*data)
                    self._ax.plot(times, mbps, label=node_id)
            self._ax.legend()
            plt.ioff()
            plt.show()
        except Exception as e:
            logger.warning("[Viz] Could not render: %s", e)
