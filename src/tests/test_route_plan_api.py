from fastapi.testclient import TestClient

from api.app import app


client = TestClient(app)


def test_route_plan_success():
    payload = {
        "session_id": "s1",
        "scenic_id": "lingshan",
        "interests": ["history", "buddhism"],
        "waypoints": [],
        "family_friendly": False,
        "avoid_stairs": False,
    }

    resp = client.post("/api/v1/guide/route-plan", json=payload)
    assert resp.status_code == 200

    data = resp.json()
    assert data["intent"] == "route_plan"
    assert data["action"] == "show_route"
    assert "data" in data
    assert "route" in data["data"]
    assert len(data["data"]["route"]) >= 2
    assert data["data"]["summary"]["estimated_total_minutes"] > 0


def test_route_plan_requires_session_id():
    payload = {
        "scenic_id": "lingshan",
        "interests": ["history"],
    }

    resp = client.post("/api/v1/guide/route-plan", json=payload)
    assert resp.status_code == 422


def test_route_plan_invalid_scenic_id():
    payload = {
        "session_id": "s1",
        "scenic_id": "unknown_scenic",
    }

    resp = client.post("/api/v1/guide/route-plan", json=payload)
    assert resp.status_code == 400
    assert "Unsupported scenic_id" in resp.json()["detail"]


def test_route_plan_with_waypoints():
    payload = {
        "session_id": "s1",
        "scenic_id": "lingshan",
        "waypoints": ["九龙灌浴"],
    }

    resp = client.post("/api/v1/guide/route-plan", json=payload)
    assert resp.status_code == 200

    route = resp.json()["data"]["route"]
    names = [item["name"] for item in route]
    assert "九龙灌浴" in names


def test_route_plan_family_friendly():
    payload = {
        "session_id": "s1",
        "scenic_id": "lingshan",
        "family_friendly": True,
    }

    resp = client.post("/api/v1/guide/route-plan", json=payload)
    assert resp.status_code == 200

    route = resp.json()["data"]["route"]
    names = [item["name"] for item in route]
    assert "九龙灌浴" in names


def test_route_plan_max_walk_minutes():
    payload = {
        "session_id": "s1",
        "scenic_id": "lingshan",
        "interests": ["history", "buddhism", "art"],
        "max_walk_minutes": 20,
    }

    resp = client.post("/api/v1/guide/route-plan", json=payload)
    assert resp.status_code == 200

    summary = resp.json()["data"]["summary"]
    assert summary["total_walk_minutes"] <= 30


def test_route_plan_ui_command():
    payload = {
        "session_id": "s1",
        "scenic_id": "lingshan",
    }

    resp = client.post("/api/v1/guide/route-plan", json=payload)
    assert resp.status_code == 200

    ui_command = resp.json()["ui_command"]
    assert ui_command["type"] == "display_route"
    assert ui_command["scenic_id"] == "lingshan"
    assert len(ui_command["route_poi_ids"]) >= 2
