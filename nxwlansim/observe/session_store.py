"""SessionStore — writes per-run session data for replay."""
from __future__ import annotations

import json
import logging
import os
import time

logger = logging.getLogger(__name__)


class SessionStore:
    def __init__(self, base_dir: str = "results/sessions"):
        self._base = os.path.abspath(base_dir)
        os.makedirs(self._base, exist_ok=True)
        self.current_dir: str = ""
        self._events_file = None
        self._run_id: str = ""
        self._start_ts: float = 0.0

    def start_session(self, run_id: str, config_yaml: str) -> str:
        ts = time.strftime("%Y-%m-%dT%H-%M-%S")
        safe_id = run_id.replace("/", "_").replace(" ", "_")[:40]
        self.current_dir = os.path.join(self._base, f"{ts}_{safe_id}")
        os.makedirs(self.current_dir, exist_ok=True)
        self._run_id = run_id
        self._start_ts = time.time()
        with open(os.path.join(self.current_dir, "config.yaml"), "w") as f:
            f.write(config_yaml or "")
        self._events_file = open(os.path.join(self.current_dir, "events.jsonl"), "w")
        logger.info("[SessionStore] Started session: %s", self.current_dir)
        return self.current_dir

    def record_event(self, event: dict) -> None:
        if self._events_file:
            self._events_file.write(json.dumps(event) + "\n")

    def end_session(self, total_bytes: int = 0) -> None:
        if self._events_file:
            self._events_file.close()
            self._events_file = None
        meta = {
            "run_id": self._run_id,
            "start_ts": self._start_ts,
            "end_ts": time.time(),
            "total_bytes": total_bytes,
        }
        if self.current_dir:
            with open(os.path.join(self.current_dir, "meta.json"), "w") as f:
                json.dump(meta, f, indent=2)
        logger.info("[SessionStore] Session ended: %s", self.current_dir)

    def list_sessions(self) -> list[dict]:
        sessions = []
        for name in sorted(os.listdir(self._base), reverse=True):
            meta_path = os.path.join(self._base, name, "meta.json")
            if os.path.exists(meta_path):
                with open(meta_path) as f:
                    meta = json.load(f)
                meta["path"] = os.path.join(self._base, name)
                sessions.append(meta)
        return sessions

    def load_events(self, session_dir: str | None = None) -> list[dict]:
        d = session_dir or self.current_dir
        events_path = os.path.join(d, "events.jsonl")
        if not os.path.exists(events_path):
            return []
        events = []
        with open(events_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        return events
