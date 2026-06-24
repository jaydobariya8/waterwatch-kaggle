"""API contract tests via FastAPI TestClient."""

from __future__ import annotations


def test_healthz(client):
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_meta_and_mcp_tools(client):
    meta = client.get("/api/v1/meta").json()
    assert meta["app"] == "WaterWatch"
    tools = client.get("/api/v1/mcp/tools").json()["tools"]
    names = {t["name"] for t in tools}
    assert names == {"get_bis_limit", "evaluate_sample", "get_area_readings", "match_filtration", "health_effect"}


def test_samples_listed(client):
    samples = client.get("/api/v1/samples").json()["samples"]
    assert len(samples) >= 5
    assert all("expected_verdict" in s for s in samples)


def test_analyze_sample_shape(client):
    res = client.post("/api/v1/analyze", json={"sample_id": "fluoride_rajasthan"})
    assert res.status_code == 200
    body = res.json()
    assert body["verdict"] == "UNSAFE"
    assert body["citations_count"] > 0
    assert body["verifier"]["passed"] is True
    assert any(b["key"] == "fluoride" for b in body["breaches"])


def test_analyze_missing_input_is_422(client):
    res = client.post("/api/v1/analyze", json={})
    assert res.status_code == 422


def test_complaint_file_and_escalate_flow(client):
    analysis = client.post("/api/v1/analyze", json={"sample_id": "arsenic_bihar"}).json()
    payload = {
        "request_id": analysis["request_id"],
        "pincode": analysis["parsed"]["pincode"],
        "location": analysis["parsed"]["location"],
        "verdict": analysis["verdict"],
        "breached_parameters": [b["key"] for b in analysis["breaches"] if b["status"] == "breach"],
        "subject": analysis["complaint_draft"]["subject"],
        "body": analysis["complaint_draft"]["body"],
    }
    filed = client.post("/api/v1/complaints", json=payload).json()
    cid = filed["complaint"]["id"]
    assert filed["complaint"]["status"] == "open"

    escalated = client.post(f"/api/v1/complaints/{cid}/escalate").json()
    assert escalated["complaint"]["status"] == "escalated"
    assert "RIGHT TO INFORMATION" in escalated["complaint"]["rti_draft"]

    listed = client.get("/api/v1/complaints").json()["complaints"]
    assert any(c["id"] == cid for c in listed)


def test_watchdog_run_endpoint(client):
    res = client.post("/api/v1/watchdog/run")
    assert res.status_code == 200
    assert "escalated" in res.json()
