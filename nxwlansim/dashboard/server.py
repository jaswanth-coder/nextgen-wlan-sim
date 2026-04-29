"""
Flask + Flask-SocketIO dashboard server.
Call create_app(engine, config) to get (app, socketio).
"""
from __future__ import annotations

import logging
import os
import threading
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

# Module-level globals set by create_app — used by api.py blueprint
_engine = None
_bridge = None
_session_store = None


def create_app(engine=None, config=None):
    from flask import Flask
    from flask_socketio import SocketIO

    from nxwlansim.dashboard.bridge import SimBridge
    from nxwlansim.dashboard.api import api_bp, init_api
    from nxwlansim.observe.session_store import SessionStore

    global _engine, _bridge, _session_store

    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "templates"),
        static_folder=os.path.join(os.path.dirname(__file__), "static"),
    )
    app.config["SECRET_KEY"] = "nxwlansim-dashboard"

    socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")

    _engine = engine
    _bridge = SimBridge(socketio)
    _session_store = SessionStore()

    if engine is not None:
        _bridge.attach(engine)

    init_api(app, engine=_engine, bridge=_bridge, store=_session_store)
    app.register_blueprint(api_bp)

    @app.route("/")
    def index():
        from flask import render_template
        return render_template("dashboard.html")

    @socketio.on("connect")
    def on_connect():
        logger.info("[Dashboard] Client connected")
        if _engine is not None:
            status = "paused" if _engine._paused else "running"
            socketio.emit("sim:status", {
                "status": status,
                "now_us": _engine.now_ns / 1_000.0,
            })

    return app, socketio


def run_dashboard(engine, config, port: int = 5050) -> None:
    """Launch dashboard server and run sim in a background thread."""
    app, socketio = create_app(engine=engine, config=config)
    _bridge.start_drain()

    try:
        import yaml
        cfg_yaml = yaml.dump(config.__dict__) if config else ""
    except Exception:
        cfg_yaml = ""

    run_id = "sim"
    if config is not None and hasattr(config, "simulation"):
        run_id = f"sim_{config.simulation.duration_us}us"

    _session_store.start_session(run_id=run_id, config_yaml=cfg_yaml)

    def _run_sim():
        try:
            results = engine.run()
            total = 0
            if hasattr(results, "summary"):
                try:
                    total = results.summary().get("total_bytes", 0)
                except Exception:
                    pass
        except Exception as exc:
            logger.exception("[Dashboard] Sim error: %s", exc)
            total = 0
        finally:
            _bridge.emit_status("stopped", engine.now_ns / 1_000.0)
            _bridge.stop_drain()
            _session_store.end_session(total_bytes=total)
            _bridge.emit_session_saved(_session_store.current_dir, _session_store._run_id)

    sim_thread = threading.Thread(target=_run_sim, daemon=True, name="sim-runner")
    sim_thread.start()

    logger.info("[Dashboard] Listening on http://localhost:%d", port)
    socketio.run(app, host="0.0.0.0", port=port)
