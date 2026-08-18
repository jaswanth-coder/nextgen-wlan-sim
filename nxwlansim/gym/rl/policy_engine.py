"""
PolicyInjectableEngine — SimulationEngine subclass that injects an EMLMR
link-selection policy into every applicable STA right after the node graph
is built, before the DES event loop starts.

Why a subclass instead of editing core/engine.py:
SimulationEngine.run() calls build_simulation() and starts the event loop
in a single method, with no hook in between the two. Rather than modify
that file, this subclass duplicates the (short) run() body and adds one
injection step right after the build. If nxwlansim later grows an official
`on_built` hook, everything in nxwlansim/gym/rl/ can switch to it and this
file can be deleted — nothing outside this subpackage depends on it.
"""

from __future__ import annotations

import heapq
import logging
from typing import Callable

from nxwlansim.core.engine import SimulationEngine

logger = logging.getLogger(__name__)


class PolicyInjectableEngine(SimulationEngine):
    def __init__(self, config, policy_factory: Callable[[], object]):
        """
        policy_factory: zero-arg callable returning a fresh
        nxwlansim.mac.mlo.LinkSelectionPolicy instance, e.g.
        `lambda: RLLinkSelectionPolicy(weights)`. Called once per EMLMR STA.
        """
        super().__init__(config)
        self._policy_factory = policy_factory

    def run(self):
        from nxwlansim.core.builder import build_simulation
        from nxwlansim.observe.logger import SimLogger
        from nxwlansim.core.results import SimResults
        from nxwlansim.observe.metrics import MetricsCollector
        from nxwlansim.observe.viz import SimViz
        from nxwlansim.phy.interference import reset_tracker

        duration_ns = self.config.simulation.duration_us * 1_000
        self._registry = build_simulation(self)

        # --- injection point: the only behavioral addition vs. the base
        # SimulationEngine.run() implementation ---
        self._inject_policies()
        # -------------------------------------------------------------

        sim_logger = SimLogger(self.config)
        self._observers.append(sim_logger.on_event)

        reset_tracker()
        self._results = SimResults(engine=self, registry=self._registry, config=self.config)

        self._viz = None
        if self.config.obs.viz:
            self._viz = SimViz(self.config, self._registry)
            self._viz.activate()

        self._metrics = MetricsCollector(self.config, self._registry, viz=self._viz)
        self._metrics.start(self)

        logger.info(
            "Simulation start (policy-injected): duration=%.3f ms, nodes=%d",
            duration_ns / 1e6,
            len(self._registry.nodes),
        )
        self._running = True
        event_count = 0

        while self._queue:
            ev = heapq.heappop(self._queue)
            if ev.time_ns > duration_ns:
                break
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

    def _inject_policies(self) -> None:
        for sta in self._registry.stas():
            if sta.mlo_mode == "emlmr" and sta.mlo_manager is not None:
                sta.mlo_manager.set_emlmr_policy(self._policy_factory())
