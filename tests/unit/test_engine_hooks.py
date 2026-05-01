"""Tests for engine hook slots and pause/resume/speed throttle."""
import threading
import time
import pytest
from nxwlansim.core.config import SimConfig
from nxwlansim.core.engine import SimulationEngine


def _tiny_cfg():
    return SimConfig.quick_build(mlo_mode="str", n_links=1, n_stas=1, duration_us=5_000)


def test_hook_slots_exist():
    engine = SimulationEngine(_tiny_cfg())
    assert hasattr(engine, "on_tx")
    assert hasattr(engine, "on_state")
    assert hasattr(engine, "on_metrics")
    assert hasattr(engine, "on_log")
    assert engine.on_tx is None
    assert engine.on_state is None


def test_on_tx_callable_set_and_not_raised():
    called = []
    engine = SimulationEngine(_tiny_cfg())
    engine.on_tx = lambda **kw: called.append(kw)
    engine.run()
    assert isinstance(called, list)


def test_pause_resume_attributes():
    engine = SimulationEngine(_tiny_cfg())
    assert hasattr(engine, "_paused")
    assert hasattr(engine, "_speed_multiplier")
    assert engine._paused is False
    assert engine._speed_multiplier == 0.0


def test_pause_stops_and_resume_continues():
    cfg = SimConfig.quick_build(mlo_mode="str", n_links=1, n_stas=1, duration_us=100_000)
    engine = SimulationEngine(cfg)
    results = {}

    def run():
        results["r"] = engine.run()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    time.sleep(0.02)
    engine.pause()
    assert engine._paused is True
    engine.resume()
    t.join(timeout=15)
    assert "r" in results
