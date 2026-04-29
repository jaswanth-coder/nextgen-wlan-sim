"""Structured text logger + CSV metrics writer."""

from __future__ import annotations

import csv
import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nxwlansim.core.config import SimConfig
    from nxwlansim.core.engine import Event

logger = logging.getLogger(__name__)


class SimLogger:
    def __init__(self, config: "SimConfig", engine=None):
        self._config = config
        self._engine = engine
        self._csv_path = os.path.join(config.obs.output_dir, "metrics.csv")
        self._csv_file = None
        self._csv_writer = None
        if config.obs.csv:
            os.makedirs(config.obs.output_dir, exist_ok=True)
            self._csv_file = open(self._csv_path, "w", newline="")
            self._csv_writer = csv.writer(self._csv_file)
            self._csv_writer.writerow(
                ["time_us", "node_id", "link_id", "event", "bytes", "mcs", "snr_db"]
            )

    def on_event(self, event: "Event") -> None:
        if self._csv_writer and hasattr(event, "kwargs"):
            kw = event.kwargs
            row = [
                event.time_ns / 1_000,
                kw.get("node_id", ""),
                kw.get("link_id", ""),
                getattr(event.callback, "__name__", ""),
                kw.get("bytes", ""),
                kw.get("mcs", ""),
                kw.get("snr_db", ""),
            ]
            self._csv_writer.writerow(row)

        if self._engine is not None and self._engine.on_log is not None:
            self._engine.on_log(
                time_ns=event.time_ns,
                callback=getattr(event.callback, "__name__", ""),
                kwargs=event.kwargs,
            )

    def close(self) -> None:
        if self._csv_file:
            self._csv_file.close()
