"""
SimulationEngine — Discrete-Event Simulation (DES) core.

Clock resolution: nanoseconds (int64).
Event queue: heapq priority queue sorted by (time_ns, priority, seq).
"""

from __future__ import annotations

import heapq
import itertools
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Event priority tiers — lower = higher priority at same timestamp
PHY_COMPLETE   = 0
MAC_DECISION   = 1
TRAFFIC_GEN    = 2
OBSERVE        = 3

# Re-export for convenience
__all__ = ["SimulationEngine", "Event", "PHY_COMPLETE", "MAC_DECISION", "TRAFFIC_GEN", "OBSERVE"]


@dataclass(order=True)
class Event:
    time_ns: int
    priority: int
    seq: int = field(compare=True)
    callback: Callable = field(compare=False)
    kwargs: dict = field(default_factory=dict, compare=False)


class SimulationEngine:
    """
    Core DES engine.

    Usage:
        engine = SimulationEngine(config)
        engine.schedule(time_ns=1000, priority=MAC_DECISION, callback=my_fn, node=node)
        results = engine.run()
    """

    def __init__(self, config):
        self.config = config
        self.clock_ns: int = 0
        self._queue: list[Event] = []
        self._seq = itertools.count()
        self._registry = None   # set by engine.run() after node build
        self._results = None    # set by engine.run(): SimResults instance
        self._observers: list[Callable] = []
        self._running = False

        # Dashboard hook slots — set by SimBridge; None = no-op
        self.on_tx: "Callable | None" = None
        self.on_state: "Callable | None" = None
        self.on_metrics: "Callable | None" = None
        self.on_log: "Callable | None" = None

        # Pause / speed control
        self._paused = False
        self._speed_multiplier: float = 0.0  # 0.0 = max speed (no throttle)
        self._pause_event = threading.Event()
        self._pause_event.set()  # set = running (clear = paused)

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------

    def schedule(
        self,
        time_ns: int,
        callback: Callable,
        priority: int = MAC_DECISION,
        **kwargs: Any,
    ) -> None:
        """Schedule an event at an absolute simulation time (nanoseconds)."""
        if time_ns < self.clock_ns:
            raise ValueError(
                f"Cannot schedule event in the past: "
                f"requested={time_ns} ns, current={self.clock_ns} ns"
            )
        ev = Event(
            time_ns=time_ns,
            priority=priority,
            seq=next(self._seq),
            callback=callback,
            kwargs=kwargs,
        )
        heapq.heappush(self._queue, ev)

    def pause(self) -> None:
        self._paused = True
        self._pause_event.clear()

    def resume(self) -> None:
        self._paused = False
        self._pause_event.set()

    def schedule_after(
        self,
        delay_ns: int,
        callback: Callable,
        priority: int = MAC_DECISION,
        **kwargs: Any,
    ) -> None:
        """Schedule an event delay_ns nanoseconds from now."""
        self.schedule(self.clock_ns + delay_ns, callback, priority, **kwargs)

    # ------------------------------------------------------------------
    # Run loop
    # ------------------------------------------------------------------

    def run(self):
        """
        Execute the simulation.
        Runs until event queue is empty or duration_ns exceeded.
        Returns a SimResults object.
        """
        from nxwlansim.core.builder import build_simulation
        from nxwlansim.observe.logger import SimLogger

        duration_ns = self.config.simulation.duration_us * 1_000
        self._registry = build_simulation(self)
        sim_logger = SimLogger(self.config, engine=self)
        self._observers.append(sim_logger.on_event)

        from nxwlansim.core.results import SimResults
        from nxwlansim.observe.metrics import MetricsCollector
        from nxwlansim.observe.viz import SimViz
        from nxwlansim.phy.interference import reset_tracker
        reset_tracker()   # clear state from any previous sim run
        self._results = SimResults(engine=self, registry=self._registry, config=self.config)

        # Set up visualization
        self._viz = None
        if self.config.obs.viz:
            self._viz = SimViz(self.config, self._registry)
            self._viz.activate()

        self._metrics = MetricsCollector(
            self.config, self._registry, viz=self._viz
        )
        self._metrics.start(self)

        logger.info(
            "Simulation start: duration=%.3f ms, nodes=%d",
            duration_ns / 1e6,
            len(self._registry.nodes),
        )
        self._running = True
        event_count = 0
        _prev_ns: int = 0

        while self._queue:
            self._pause_event.wait()  # blocks while paused
            if not self._running:
                break
            ev = heapq.heappop(self._queue)
            if ev.time_ns > duration_ns:
                break
            # Wall-clock throttle: sleep proportional to sim-time delta
            if self._speed_multiplier > 0:
                import time as _time
                delta_s = (ev.time_ns - _prev_ns) / 1e9 / self._speed_multiplier
                if delta_s > 0:
                    _time.sleep(min(delta_s, 0.1))  # cap at 100ms per event
            _prev_ns = ev.time_ns
            self.clock_ns = ev.time_ns
            ev.callback(engine=self, **ev.kwargs)
            for obs in self._observers:
                obs(ev)
            event_count += 1

        self._running = False
        self._metrics.close()
        if hasattr(self, "_pcap_writer"):
            self._pcap_writer.close_all()
        if self._viz:
            self._viz.finalize(self.config.obs.output_dir)
        logger.info(
            "Simulation end: clock=%.3f ms, events_processed=%d",
            self.clock_ns / 1e6,
            event_count,
        )
        return self._results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def now_ns(self) -> int:
        return self.clock_ns

    @property
    def now_us(self) -> float:
        return self.clock_ns / 1_000.0

    def add_observer(self, fn: Callable) -> None:
        self._observers.append(fn)
