"""REST API Blueprint for dashboard control commands."""
from __future__ import annotations

import logging
from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)
api_bp = Blueprint("api", __name__, url_prefix="/api")

# Set by init_api()
_engine = None
_bridge = None
session_store = None


def init_api(app, engine, bridge, store):
    global _engine, _bridge, session_store
    _engine = engine
    _bridge = bridge
    session_store = store


def _get_node(node_id: str):
    if _engine is None or _engine._registry is None:
        return None
    for node in _engine._registry:
        if node.node_id == node_id:
            return node
    return None


def _node_to_dict(node) -> dict:
    return {
        "node_id": node.node_id,
        "type": node.node_type,
        "position": list(node.position),
        "links": list(node.links),
        "mlo_mode": getattr(node, "mlo_mode", "str"),
    }


# ---- Sim controls -------------------------------------------------------

@api_bp.route("/sim/pause", methods=["POST"])
def sim_pause():
    if _engine:
        _engine.pause()
        if _bridge:
            _bridge.emit_status("paused", _engine.now_ns / 1_000.0)
    return jsonify({"status": "paused"})


@api_bp.route("/sim/resume", methods=["POST"])
def sim_resume():
    if _engine:
        _engine.resume()
        if _bridge:
            _bridge.emit_status("running", _engine.now_ns / 1_000.0)
    return jsonify({"status": "running"})


@api_bp.route("/sim/stop", methods=["POST"])
def sim_stop():
    if _engine:
        _engine._running = False
        _engine.resume()  # unblock if paused
    return jsonify({"status": "stopped"})


@api_bp.route("/sim/speed", methods=["PATCH"])
def sim_speed():
    data = request.get_json(silent=True) or {}
    mult = data.get("multiplier")
    if mult is None or not isinstance(mult, (int, float)) or mult < 0:
        return jsonify({"error": "multiplier must be a non-negative number"}), 400
    if _engine:
        _engine._speed_multiplier = float(mult)
    return jsonify({"speed_multiplier": float(mult)})


# ---- Node operations ----------------------------------------------------

@api_bp.route("/nodes", methods=["GET"])
def list_nodes():
    if _engine is None or _engine._registry is None:
        return jsonify([])
    return jsonify([_node_to_dict(n) for n in _engine._registry])


@api_bp.route("/nodes", methods=["POST"])
def add_node():
    data = request.get_json(silent=True) or {}
    node_id = data.get("id") or data.get("node_id", "")
    node_type = data.get("type", "sta")
    position = data.get("position", [0.0, 0.0])
    links = data.get("links", ["6g"])
    mlo_mode = data.get("mlo_mode", "str")
    if not node_id:
        return jsonify({"error": "id required"}), 400
    if _engine is None:
        return jsonify({"error": "no engine"}), 503

    from nxwlansim.core.config import NodeConfig
    from nxwlansim.core.node import APNode, STANode

    cfg = NodeConfig(id=node_id, type=node_type, links=links,
                     mlo_mode=mlo_mode, position=position)
    node = APNode(cfg) if node_type == "ap" else STANode(cfg)
    _engine._registry.register(node)
    if _bridge:
        _bridge.emit_node_added(node_id, node_type, position, links)
    return jsonify(_node_to_dict(node)), 201


@api_bp.route("/nodes/<node_id>", methods=["DELETE"])
def remove_node(node_id: str):
    node = _get_node(node_id)
    if node is None:
        return jsonify({"error": "not found"}), 404
    _engine._registry.nodes.pop(node_id, None)
    if _bridge:
        _bridge.emit_node_removed(node_id)
    return jsonify({"deleted": node_id})


@api_bp.route("/nodes/<node_id>/position", methods=["PATCH"])
def patch_position(node_id: str):
    node = _get_node(node_id)
    if node is None:
        return jsonify({"error": "not found"}), 404
    data = request.get_json(silent=True) or {}
    x = float(data.get("x", node.position[0]))
    y = float(data.get("y", node.position[1]))
    node.position = (x, y)
    if node.phy and hasattr(node.phy, "register_node"):
        node.phy.register_node(node_id, (x, y))
    return jsonify(_node_to_dict(node))


@api_bp.route("/nodes/<node_id>/mcs", methods=["PATCH"])
def patch_mcs(node_id: str):
    node = _get_node(node_id)
    if node is None:
        return jsonify({"error": "not found"}), 404
    data = request.get_json(silent=True) or {}
    mcs = data.get("mcs", "auto")
    node._mcs_override = None if mcs == "auto" else int(mcs)
    return jsonify({"node_id": node_id, "mcs": mcs})


@api_bp.route("/nodes/<node_id>/npca", methods=["PATCH"])
def patch_npca(node_id: str):
    node = _get_node(node_id)
    if node is None:
        return jsonify({"error": "not found"}), 404
    data = request.get_json(silent=True) or {}
    enabled = bool(data.get("enabled", True))
    if hasattr(node, "npca_engine") and node.npca_engine:
        node.npca_engine._enabled = enabled
    return jsonify({"node_id": node_id, "npca_enabled": enabled})


# ---- Traffic injection --------------------------------------------------

@api_bp.route("/traffic", methods=["POST"])
def inject_traffic():
    data = request.get_json(silent=True) or {}
    src = data.get("src", "")
    dst = data.get("dst", "")
    traffic_type = data.get("type", "udp_cbr")
    rate_mbps = float(data.get("rate_mbps", 10.0))
    ac = data.get("ac", "BE")
    if not src or not dst:
        return jsonify({"error": "src and dst required"}), 400
    if _engine is None:
        return jsonify({"error": "no engine"}), 503

    from nxwlansim.core.config import TrafficConfig
    from nxwlansim.traffic.generators import _schedule_single_source
    t_cfg = TrafficConfig(src=src, dst=dst, type=traffic_type,
                          rate_mbps=rate_mbps, ac=ac)
    src_node = _get_node(src)
    dst_node = _get_node(dst)
    if src_node is None or dst_node is None:
        return jsonify({"error": "src or dst node not found"}), 404
    _schedule_single_source(_engine, src_node, t_cfg)
    return jsonify({"injected": True, "src": src, "dst": dst,
                    "rate_mbps": rate_mbps, "ac": ac}), 201


# ---- Sessions -----------------------------------------------------------

@api_bp.route("/sessions", methods=["GET"])
def list_sessions():
    if session_store is None:
        return jsonify([])
    return jsonify(session_store.list_sessions())


@api_bp.route("/sessions/<run_id>", methods=["GET"])
def get_session(run_id: str):
    if session_store is None:
        return jsonify({"error": "no store"}), 503
    for s in session_store.list_sessions():
        if s.get("run_id") == run_id:
            return jsonify(s)
    return jsonify({"error": "not found"}), 404


@api_bp.route("/sessions/<run_id>/events", methods=["GET"])
def get_session_events(run_id: str):
    if session_store is None:
        return jsonify({"error": "no store"}), 503
    for s in session_store.list_sessions():
        if s.get("run_id") == run_id:
            events = session_store.load_events(s["path"])
            return jsonify(events)
    return jsonify({"error": "not found"}), 404
