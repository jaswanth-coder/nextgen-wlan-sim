"""Integration test: run sim → save session → load events from store."""
import os
import pytest
from nxwlansim.core.config import SimConfig
from nxwlansim.core.engine import SimulationEngine
from nxwlansim.observe.session_store import SessionStore


def test_session_saved_and_loadable(tmp_path):
    cfg = SimConfig.quick_build(mlo_mode="str", n_links=1, n_stas=1, duration_us=20_000)
    store = SessionStore(base_dir=str(tmp_path / "sessions"))
    store.start_session("integration_test", "")

    # Manually record a few events (simulating what bridge would do)
    store.record_event({"type": "tx:event", "node_id": "sta0", "bytes_tx": 1500})
    store.record_event({"type": "metrics:sample", "node_id": "sta0", "throughput_mbps": 45.2})

    store.end_session(total_bytes=1500)

    # Verify events.jsonl round-trips
    events = store.load_events()
    assert len(events) == 2
    assert events[0]["type"] == "tx:event"
    assert events[1]["type"] == "metrics:sample"

    # Verify meta.json
    sessions = store.list_sessions()
    assert len(sessions) == 1
    assert sessions[0]["run_id"] == "integration_test"
    assert sessions[0]["total_bytes"] == 1500
