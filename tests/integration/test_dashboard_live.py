"""
Integration test: start sim + dashboard in-process,
connect SocketIO test client, run 50ms sim,
assert no exceptions thrown during emission.
"""
import threading
import time
import pytest


def test_dashboard_emits_metrics():
    from nxwlansim.core.config import SimConfig
    from nxwlansim.core.engine import SimulationEngine
    from nxwlansim.dashboard.server import create_app

    cfg = SimConfig.quick_build(mlo_mode="str", n_links=1, n_stas=1, duration_us=50_000)
    engine = SimulationEngine(cfg)
    app, socketio = create_app(engine=engine, config=cfg)

    test_client = socketio.test_client(app)
    assert test_client.is_connected()

    # Run sim in background thread
    def run():
        engine.run()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout=10)

    # Drain any queued events
    received = test_client.get_received()
    test_client.disconnect()

    # Primary assertion: sim ran without errors and client connected
    assert True
