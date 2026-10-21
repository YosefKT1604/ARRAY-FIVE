import json
from pathlib import Path

FORM = json.loads(
    (Path(__file__).resolve().parents[1] / "fixtures" / "demo" / "incident.json").read_text(encoding="utf-8")
)["form_input"]


def test_report_disruption_returns_201_with_incident(client):
    response = client.post("/api/v1/disruptions", json=FORM)
    assert response.status_code == 201
    body = response.json()
    assert body["disruption"]["id"] == "D-001"
    assert body["disruption"]["status"] == "received"
    assert body["incident"]["quantity_affected"] == 20

def test_list_and_get_disruption(client):
    client.post("/api/v1/disruptions", json=FORM)
    assert [d["id"] for d in client.get("/api/v1/disruptions").json()["items"]] == ["D-001"]
    assert client.get("/api/v1/disruptions/D-001").status_code == 200

def test_unknown_disruption_returns_404(client):
    assert client.get("/api/v1/disruptions/D-999").status_code == 404

def test_analyze_returns_impact_and_marks_disruption_analyzed(client):
    client.post("/api/v1/disruptions", json=FORM)
    response = client.post("/api/v1/disruptions/D-001/analyze")
    assert response.status_code == 200
    impact = response.json()
    assert impact["disruption_id"] == "D-001"
    assert impact["resource_shortfalls"][0]["shortfall"] == 20
    assert client.get("/api/v1/disruptions/D-001").json()["status"] == "analyzed"
    assert client.get("/api/v1/disruptions/D-001/impact").json() == impact

def test_impact_before_analysis_returns_404(client):
    client.post("/api/v1/disruptions", json=FORM)
    response = client.get("/api/v1/disruptions/D-001/impact")
    assert response.status_code == 404

def test_analyze_unknown_disruption_returns_404(client):
    response = client.post("/api/v1/disruptions/D-999/analyze")
    assert response.status_code == 404

