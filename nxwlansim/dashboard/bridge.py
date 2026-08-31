"""
SimBridge — hooks into engine event slots, queues payloads,
drains them to SocketIO at ≤60 events/s via a background thread.
"""
from __future__ import annotations

import collections
import logging
import threading
import time
from typing import TYPE_CHECKING

from nxwlansim.dashboard.events import (
    EVT_TX, EVT_LINK_STATE, EVT_METRICS, EVT_LOG,
    EVT_SIM_TICK, EVT_SIM_STATUS, EVT_SESSION_SAVED,
    EVT_NODE_ADDED, EVT_NODE_REMOVED,
)

if TYPE_CHECKING:
    from nxwlansim.core.engine import SimulationEngine

logger = logging.getLogger(__name__)

_MAX_RATE = 60        # max events per second pushed to browser
_MIN_INTERVAL = 1.0 / _MAX_RATE


class SimBridge:
    """
    Connects SimulationEngine event hooks to a SocketIO instance.
    Thread-safe: engine calls hooks from its sim thread; drain runs in
    a separate background thread.
    """

    def __init__(self, socketio, maxlen: int = 10_000):
        self._sio = socketio
        self._queue: collections.deque = collections.deque(maxlen=maxlen)
        self._draining = False
        self._drain_thread: threading.Thread | None = None

    def attach(self, engine: "SimulationEngine") -> None:
        engine.on_tx      = self.on_tx
        engine.on_state   = self.on_state
        engine.on_metrics = self.on_metrics
        engine.on_log     = self.on_log

    def detach(self, engine: "SimulationEngine") -> None:
        engine.on_tx = engine.on_state = engine.on_metrics = engine.on_log = None

    # ------------------------------------------------------------------
    # Engine hook callbacks — called from sim thread
    # ------------------------------------------------------------------

    def on_tx(self, node_id: str, link_id: str, bytes_tx: int,
              mcs: int, time_ns: int, **kwargs) -> None:
        self._enqueue(EVT_TX, {
            "node_id": node_id,
            "link_id": link_id,
            "bytes_tx": bytes_tx,
            "mcs": mcs,
            "time_ns": time_ns,
        })

    def on_state(self, node_id: str, link_id: str, state: str,
                 time_ns: int = 0, **kwargs) -> None:
        self._enqueue(EVT_LINK_STATE, {
            "node_id": node_id,
            "link_id": link_id,
            "state": state,
            "time_ns": time_ns,
        })

    def on_metrics(self, node_id: str, time_us: float, throughput_mbps: float,
                   frames: int = 0, bytes_tx: int = 0, mcs=None,
                   snr_db=None, **kwargs) -> None:
        self._enqueue(EVT_METRICS, {
            "node_id": node_id,
            "time_us": round(time_us, 1),
            "throughput_mbps": round(throughput_mbps, 3),
            "frames": frames,
            "bytes_tx": bytes_tx,
            "mcs": mcs,
            "snr_db": snr_db,
        })

    def on_log(self, time_ns: int, callback: str, kwargs: dict, **_) -> None:
        self._enqueue(EVT_LOG, {
            "time_ns": time_ns,
            "callback": callback,
            "node_id": kwargs.get("node_id", ""),
            "link_id": kwargs.get("link_id", ""),
        })

    # ------------------------------------------------------------------
    # Direct emit helpers (called from REST API / server)
    # ------------------------------------------------------------------

    def emit_status(self, status: str, now_us: float = 0.0) -> None:
        self._sio.emit(EVT_SIM_STATUS, {"status": status, "now_us": now_us})

    def emit_node_added(self, node_id: str, node_type: str,
                        position: list, links: list) -> None:
        self._sio.emit(EVT_NODE_ADDED, {
            "node_id": node_id, "type": node_type,
            "position": position, "links": links,
        })

    def emit_node_removed(self, node_id: str) -> None:
        self._sio.emit(EVT_NODE_REMOVED, {"node_id": node_id})

    def emit_session_saved(self, path: str, run_id: str) -> None:
        self._sio.emit(EVT_SESSION_SAVED, {"path": path, "run_id": run_id})

    # ------------------------------------------------------------------
    # Drain loop — runs in background thread
    # ------------------------------------------------------------------

    def start_drain(self) -> None:
        self._draining = True
        self._drain_thread = threading.Thread(
            target=self._drain_loop, daemon=True, name="simbridge-drain"
        )
        self._drain_thread.start()

    def stop_drain(self) -> None:
        self._draining = False
        if self._drain_thread:
            self._drain_thread.join(timeout=2.0)
            self._drain_thread = None

    def _drain_loop(self) -> None:
        while self._draining:
            if self._queue:
                item = self._queue.popleft()
                try:
                    self._sio.emit(item["event"], item["data"])
                except Exception as exc:
                    logger.debug("[Bridge] emit error: %s", exc)
            time.sleep(_MIN_INTERVAL)

    # ------------------------------------------------------------------

    def _enqueue(self, event: str, data: dict) -> None:
        self._queue.append({"event": event, "data": data})
