"""Tests for SimBridge — event queuing and rate-limiting."""
import collections
import pytest
from unittest.mock import MagicMock
from nxwlansim.dashboard.bridge import SimBridge
from nxwlansim.dashboard.events import (
    EVT_TX, EVT_LINK_STATE, EVT_METRICS, EVT_LOG, EVT_SIM_STATUS
)


@pytest.fixture
def bridge():
    socketio_mock = MagicMock()
    return SimBridge(socketio_mock)


def test_bridge_queues_on_tx(bridge):
    bridge.on_tx(node_id="sta0", link_id="6g", bytes_tx=1500, mcs=9, time_ns=1000)
    assert len(bridge._queue) == 1
    assert bridge._queue[0]["event"] == EVT_TX


def test_bridge_queues_on_state(bridge):
    bridge.on_state(node_id="sta0", link_id="6g", state="TRANSMITTING", time_ns=1000)
    assert bridge._queue[0]["event"] == EVT_LINK_STATE


def test_bridge_queues_on_metrics(bridge):
    bridge.on_metrics(
        node_id="sta0", time_us=1000.0, throughput_mbps=45.2,
        frames=10, bytes_tx=1500, mcs=9, snr_db="28.0",
    )
    assert bridge._queue[0]["event"] == EVT_METRICS


def test_bridge_deque_max_length():
    socketio_mock = MagicMock()
    b = SimBridge(socketio_mock, maxlen=5)
    for i in range(10):
        b.on_tx(node_id="sta0", link_id="6g", bytes_tx=i, mcs=0, time_ns=i)
    assert len(b._queue) == 5
    # Oldest dropped — last 5 have bytes_tx 5..9
    assert b._queue[0]["data"]["bytes_tx"] == 5


def test_bridge_attach_hooks_engine():
    socketio_mock = MagicMock()
    b = SimBridge(socketio_mock)
    engine = MagicMock()
    engine.on_tx = None
    engine.on_state = None
    engine.on_metrics = None
    engine.on_log = None
    b.attach(engine)
    assert engine.on_tx == b.on_tx
    assert engine.on_state == b.on_state
    assert engine.on_metrics == b.on_metrics
    assert engine.on_log == b.on_log


def test_event_constants_are_strings():
    assert isinstance(EVT_TX, str)
    assert isinstance(EVT_LINK_STATE, str)
    assert isinstance(EVT_METRICS, str)
    assert isinstance(EVT_LOG, str)
    assert isinstance(EVT_SIM_STATUS, str)
