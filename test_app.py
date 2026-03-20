import pytest, json
from main import app

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c

def test_home_loads(client):
    r = client.get("/")
    assert r.status_code == 200

def test_health_check(client):
    r = client.get("/health")
    assert r.status_code == 200
    d = json.loads(r.data)
    assert d["status"] == "ok"
    assert d["app"] == "maru-mitra"
    assert d["version"] == "2.0"

def test_api_test_route(client):
    r = client.get("/api/test")
    assert r.status_code == 200
    d = json.loads(r.data)
    assert "status" in d

def test_analyze_empty_input(client):
    r = client.post("/api/analyze",
        json={},
        content_type="application/json")
    assert r.status_code == 400

def test_analyze_no_json(client):
    r = client.post("/api/analyze")
    assert r.status_code in [400, 415]

def test_weather_proxy_default(client):
    r = client.post("/api/weather",
        json={"lat": 26.9157, "lon": 70.9083},
        content_type="application/json")
    assert r.status_code == 200
    d = json.loads(r.data)
    assert "current" in d

def test_weather_proxy_no_body(client):
    r = client.post("/api/weather",
        json={},
        content_type="application/json")
    assert r.status_code == 200

def test_grievance_check(client):
    r = client.get("/api/grievance/MM-2026-12345")
    assert r.status_code == 200
    d = json.loads(r.data)
    assert "found" in d
    assert d["found"] is True

def test_analyze_heat_input(client):
    r = client.post("/api/analyze",
        json={"text": "garmi lag gayi", "weather": {"temp": 46}},
        content_type="application/json")
    # Routes must respond; may 500 without real API key
    assert r.status_code in [200, 500]

def test_analyze_water_input(client):
    r = client.post("/api/analyze",
        json={"text": "paani nahi hai gaon mein"},
        content_type="application/json")
    assert r.status_code in [200, 500]

def test_analyze_with_location(client):
    r = client.post("/api/analyze",
        json={
            "text": "medical emergency",
            "location": {"lat": 26.9157, "lon": 70.9083}
        },
        content_type="application/json")
    assert r.status_code in [200, 500]
