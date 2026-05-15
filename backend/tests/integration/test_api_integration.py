from pathlib import Path
from types import SimpleNamespace
from importlib.util import find_spec

import pytest

HAS_FASTAPI = find_spec("fastapi") is not None

if HAS_FASTAPI:
    from fastapi.testclient import TestClient
    from app.api.v1 import pipeline
    from app.main import app
else:
    TestClient = None
    pipeline = None
    app = None


@pytest.fixture()
def client():
    if not HAS_FASTAPI:
        pytest.skip("dependencias de integración (fastapi) no instaladas en el entorno")
    return TestClient(app)


def test_health_status_ok(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_import_folder_endpoint_uses_service_mock(client, monkeypatch, tmp_path):
    input_dir = tmp_path / "entrada_cliente"
    input_dir.mkdir()
    expected = {"status": "ok", "case_path": str(tmp_path / "case_imported")}
    monkeypatch.setattr(pipeline, "import_folder_from_input_path", lambda p: expected)

    response = client.post("/api/v1/case/import-folder", json={"input_path": str(input_dir)})

    assert response.status_code == 200
    assert response.json() == expected


def test_generate_domain_from_supports_with_service_mock(client, monkeypatch, tmp_path):
    case_path = tmp_path / "case_a"
    case_path.mkdir(parents=True)
    supports_dir = case_path / "Apoyos"
    supports_dir.mkdir(parents=True)
    (supports_dir / "apoyos.shp").touch()
    called = {}

    def _fake_generate(case_path_arg: str, buffer_m: float = 200.0):
        called["case_path"] = case_path_arg
        called["buffer_m"] = buffer_m
        return {"status": "ok", "source": "supports", "domain": "fake"}

    monkeypatch.setattr(pipeline, "_generate_domain_from_supports_logic", _fake_generate)

    response = client.post(
        "/api/v1/domain/generate-from-supports",
        json={"case_path": str(case_path), "buffer_m": 250},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert called == {"case_path": str(case_path), "buffer_m": 250}


def test_controlled_errors_case_not_found_and_invalid_supports(client, monkeypatch, tmp_path):
    missing_response = client.post(
        "/api/v1/domain/generate-from-supports",
        json={"case_path": str(tmp_path / 'missing')},
    )
    assert missing_response.status_code == 404

    case_invalid = tmp_path / "case_invalid"
    case_invalid.mkdir(parents=True)
    invalid_supports_response = client.post(
        "/api/v1/domain/generate-from-supports",
        json={"case_path": str(case_invalid)},
    )
    assert invalid_supports_response.status_code == 400


def test_controlled_error_invalid_parameters(client):
    response = client.post("/api/v1/domain/generate-from-supports", json={"case_path": 123, "buffer_m": "abc"})
    assert response.status_code == 422


def test_run_preparation_does_not_use_legacy_pipeline_or_towers(client, monkeypatch, tmp_path):
    case_path = tmp_path / "case_prep"
    case_path.mkdir(parents=True)
    cfg = SimpleNamespace(
        in_shp=str(case_path / "SHP" / "dominio.shp"),
        out_shp=str(case_path / "Calculos" / "out.shp"),
        out_rec_shp=str(case_path / "Calculos" / "out_rec.shp"),
        out_rec_exp_shp=str(case_path / "SHP" / "dominio_exp.shp"),
        out_mdt_tif=str(case_path / "MDT_WN" / "mdt.tif"),
    )
    (case_path / "SHP").mkdir(parents=True, exist_ok=True)
    (case_path / "SHP" / "dominio.shp").touch()

    called = {"run_geometry_and_dem": 0, "run_towers": 0, "run_base": 0}
    monkeypatch.setattr(pipeline, "load_cfg_from_case_or_raise", lambda _: cfg)
    monkeypatch.setattr(pipeline, "get_existing_domain_path", lambda _: Path(cfg.in_shp))
    monkeypatch.setattr(
        pipeline,
        "run_geometry_and_dem",
        lambda _cfg: called.__setitem__("run_geometry_and_dem", called["run_geometry_and_dem"] + 1)
        or {"minx": 0, "miny": 0, "maxx": 1, "maxy": 1},
    )
    monkeypatch.setattr(pipeline, "_generate_weather_for_cfg", lambda _cfg: {"points": [], "station_files": []})

    def _towers_called(*_args, **_kwargs):
        called["run_towers"] += 1
        raise AssertionError("run_towers should not be called")

    def _run_base_called(*_args, **_kwargs):
        called["run_base"] += 1
        raise AssertionError("legacy run-base should not be called")

    monkeypatch.setattr(pipeline, "run_towers", _towers_called)
    monkeypatch.setattr(pipeline, "run_base_pipeline", _run_base_called)

    response = client.post("/api/v1/pipeline/run-preparation", json={"case_path": str(case_path)})

    assert response.status_code == 200
    assert called["run_geometry_and_dem"] == 1
    assert called["run_towers"] == 0
    assert called["run_base"] == 0
