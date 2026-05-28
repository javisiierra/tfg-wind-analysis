import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.api.v1 import dashboard_router
from app.main import app

client = TestClient(app)


def _meta():
    return {
        "source": "era5",
        "request_id": "req-1",
        "domain_bbox": [-6.0, 43.0, -5.0, 44.0],
        "time_range": {"start": "2024-01-01", "end": "2024-12-31"},
        "crs": "EPSG:4326",
        "status": "ok",
    }


def test_meteo_summary_contract(monkeypatch):
    captured = {}

    def fake_summary(year: int, domain):
        captured["year"] = year
        captured["domain"] = domain
        return {
            "year": year,
            "avg_velocity": 5.5,
            "max_velocity": 12.2,
            "dominant_direction": 270.0,
            "windiest_month": 1,
            "viability_index": 0.72,
            "data_points": 8760,
            **_meta(),
        }

    monkeypatch.setattr(dashboard_router.service, "get_meteo_summary", fake_summary)
    resp = client.post(
        "/api/v1/dashboard/meteo-summary",
        json={"year": 2024, "case_path": "/tmp/caseA"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["year"] == 2024
    assert body["source"] == "era5"
    assert body["request_id"] == "req-1"
    assert captured["domain"].case_path == "/tmp/caseA"


def test_wind_timeseries_contract(monkeypatch):
    def fake_ts(year: int, domain):
        return {
            "items": [
                {
                    "month": month,
                    "avg_velocity": 1.0,
                    "max_velocity": 2.0,
                    "min_velocity": 0.1,
                    "frequency": {
                        "0-2": 0.5,
                        "2-4": 0.5,
                        "4-6": 0.0,
                        "6-8": 0.0,
                        "8-10": 0.0,
                        "10+": 0.0,
                    },
                }
                for month in range(1, 13)
            ],
            **_meta(),
        }

    monkeypatch.setattr(dashboard_router.service, "get_wind_timeseries", fake_ts)
    resp = client.post(
        "/api/v1/dashboard/wind-timeseries",
        json={"year": 2024, "case_path": "/tmp/caseA"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 12
    assert {"month", "avg_velocity", "max_velocity", "min_velocity", "frequency"}.issubset(body[0])
    assert body[0]["source"] == "era5"


def test_wind_rose_contract(monkeypatch):
    def fake_rose(year: int, domain):
        return {
            "items": [
                {"direction": "N", "frequency": 0.1, "velocity_range": {"min": 1.0, "max": 3.0}}
            ]
            * 16,
            **_meta(),
        }

    monkeypatch.setattr(dashboard_router.service, "get_wind_rose", fake_rose)
    resp = client.post(
        "/api/v1/dashboard/wind-rose",
        json={"year": 2024, "case_path": "/tmp/caseA"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 16
    assert {"direction", "frequency", "velocity_range"}.issubset(body[0])
    assert body[0]["request_id"] == "req-1"


def test_request_requires_single_domain_identifier():
    resp = client.post(
        "/api/v1/dashboard/meteo-summary",
        json={"year": 2024, "case_path": "/tmp/caseA", "domain_id": "x"},
    )
    assert resp.status_code == 422
