"""Unit tests for dashboard REST API using Flask test client."""
import json
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def app():
    from nxwlansim.dashboard.server import create_app
    engine_mock = MagicMock()
    engine_mock._paused = False
    engine_mock._running = True
    engine_mock._speed_multiplier = 0.0
    engine_mock.now_ns = 0
    engine_mock._registry = MagicMock()
    engine_mock._registry.__iter__ = MagicMock(return_value=iter([]))
    app, _ = create_app(engine=engine_mock, config=None)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_pause_returns_200(client):
    resp = client.post("/api/sim/pause")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["status"] == "paused"


def test_resume_returns_200(client):
    resp = client.post("/api/sim/resume")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["status"] == "running"


def test_stop_returns_200(client):
    resp = client.post("/api/sim/stop")
    assert resp.status_code == 200


def test_set_speed_valid(client):
    resp = client.patch("/api/sim/speed",
                        data=json.dumps({"multiplier": 2.0}),
                        content_type="application/json")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["speed_multiplier"] == 2.0


def test_set_speed_invalid(client):
    resp = client.patch("/api/sim/speed",
                        data=json.dumps({"multiplier": -1}),
                        content_type="application/json")
    assert resp.status_code == 400


def test_get_nodes_returns_list(client):
    resp = client.get("/api/nodes")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert isinstance(data, list)


def test_get_sessions_returns_list(client):
    with patch("nxwlansim.dashboard.api.session_store") as mock_store:
        mock_store.list_sessions.return_value = []
        resp = client.get("/api/sessions")
    assert resp.status_code == 200


def test_patch_node_position(client):
    with patch("nxwlansim.dashboard.api._get_node") as mock_get:
        mock_node = MagicMock()
        mock_node.node_id = "sta0"
        mock_node.node_type = "sta"
        mock_node.position = (5.0, 0.0)
        mock_node.links = ["6g"]
        mock_node.mlo_mode = "str"
        mock_get.return_value = mock_node
        resp = client.patch("/api/nodes/sta0/position",
                            data=json.dumps({"x": 10.0, "y": 5.0}),
                            content_type="application/json")
    assert resp.status_code == 200
