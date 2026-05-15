from fastapi.testclient import TestClient

from app.main import app
from app.api.v1 import dashboard_router

client = TestClient(app)


def test_meteo_summary_contract(monkeypatch):
    def fake_summary(year: int, case_path=None, fallback_to_mock=None):
        return {
            "year": year,
            "avg_velocity": 5.5,
            "max_velocity": 12.2,
            "dominant_direction": 270.0,
            "windiest_month": 1,
            "viability_index": 0.72,
            "data_points": 8760,
        }

    monkeypatch.setattr(dashboard_router.service, "get_meteo_summary", fake_summary)
    resp = client.post("/api/v1/dashboard/meteo-summary", json={"year": 2024, "case_path": "/tmp/caseA", "use_mock_fallback": True})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {
        "year",
        "avg_velocity",
        "max_velocity",
        "dominant_direction",
        "windiest_month",
        "viability_index",
        "data_points",
    }


def test_wind_timeseries_contract(monkeypatch):
    def fake_ts(year: int, case_path=None, fallback_to_mock=None):
        return [
            {
                "month": month,
                "avg_velocity": 1.0,
                "max_velocity": 2.0,
                "min_velocity": 0.1,
                "frequency": {"0-2": 0.5, "2-4": 0.5, "4-6": 0.0, "6-8": 0.0, "8-10": 0.0, "10+": 0.0},
            }
            for month in range(1, 13)
        ]

    monkeypatch.setattr(dashboard_router.service, "get_wind_timeseries", fake_ts)
    resp = client.post("/api/v1/dashboard/wind-timeseries", json={"year": 2024, "case_path": "/tmp/caseA", "use_mock_fallback": True})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 12
    assert set(body[0].keys()) == {"month", "avg_velocity", "max_velocity", "min_velocity", "frequency"}


def test_wind_rose_contract(monkeypatch):
    def fake_rose(year: int, case_path=None, fallback_to_mock=None):
        return [
            {"direction": "N", "frequency": 0.1, "velocity_range": {"min": 1.0, "max": 3.0}}
        ] * 16

    monkeypatch.setattr(dashboard_router.service, "get_wind_rose", fake_rose)
    resp = client.post("/api/v1/dashboard/wind-rose", json={"year": 2024, "case_path": "/tmp/caseA", "use_mock_fallback": True})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 16
    assert set(body[0].keys()) == {"direction", "frequency", "velocity_range"}


def test_request_requires_single_domain_identifier():
    resp = client.post("/api/v1/dashboard/meteo-summary", json={"year": 2024, "case_path": "/tmp/caseA", "domain_id": "x"})
    assert resp.status_code == 422


def test_fallback_flag_passthrough(monkeypatch):
    captured = {}

    def fake_summary(year: int, case_path=None, fallback_to_mock=None):
        captured["case_path"] = case_path
        captured["fallback_to_mock"] = fallback_to_mock
        return {"year": year, "avg_velocity": 1.0, "max_velocity": 2.0, "dominant_direction": 3.0, "windiest_month": 1, "viability_index": 0.1, "data_points": 10}

    monkeypatch.setattr(dashboard_router.service, "get_meteo_summary", fake_summary)
    resp = client.post("/api/v1/dashboard/meteo-summary", json={"year": 2024, "case_path": "/tmp/caseA", "use_mock_fallback": False})
    assert resp.status_code == 200
    assert captured == {"case_path": "/tmp/caseA", "fallback_to_mock": False}
