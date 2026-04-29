"""Tests for SessionStore — per-run session writer and replay loader."""
import json
import os
import pytest
from nxwlansim.observe.session_store import SessionStore


@pytest.fixture
def store(tmp_path):
    return SessionStore(base_dir=str(tmp_path))


def test_start_creates_directory(store, tmp_path):
    run_dir = store.start_session(run_id="test_run", config_yaml="simulation:\n  duration_us: 1000\n")
    assert os.path.isdir(run_dir)
    assert os.path.exists(os.path.join(run_dir, "config.yaml"))


def test_record_event_writes_jsonl(store):
    store.start_session("r1", "")
    store.record_event({"type": "tx:event", "node_id": "sta0", "bytes": 1500})
    store.record_event({"type": "tx:event", "node_id": "sta1", "bytes": 800})
    store.end_session(total_bytes=2300)
    events = store.load_events()
    assert len(events) == 2
    assert events[0]["node_id"] == "sta0"


def test_end_session_writes_meta(store, tmp_path):
    store.start_session("r2", "")
    store.end_session(total_bytes=12345)
    meta_path = os.path.join(store.current_dir, "meta.json")
    with open(meta_path) as f:
        meta = json.load(f)
    assert meta["run_id"] == "r2"
    assert meta["total_bytes"] == 12345
    assert "end_ts" in meta


def test_list_sessions(store, tmp_path):
    store.start_session("s1", ""); store.end_session(0)
    store.start_session("s2", ""); store.end_session(0)
    sessions = store.list_sessions()
    assert len(sessions) == 2
    ids = [s["run_id"] for s in sessions]
    assert "s1" in ids and "s2" in ids


def test_load_events_from_path(store, tmp_path):
    store.start_session("r3", "")
    store.record_event({"type": "sim:tick", "now_us": 100})
    store.end_session(0)
    events = store.load_events(store.current_dir)
    assert events[0]["type"] == "sim:tick"
