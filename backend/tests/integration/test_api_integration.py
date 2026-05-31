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


def test_generate_vanos_from_supports_with_service_mock(client, monkeypatch, tmp_path):
    case_path = tmp_path / "case_vanos"
    case_path.mkdir(parents=True)
    expected = {
        "status": "ok",
        "message": "Generados 2 vanos desde apoyos",
        "created": True,
        "vanos_count": 2,
        "output_shp": str(case_path / "SHP" / "vanos.shp"),
        "output_geojson": str(case_path / "SHP" / "vanos.geojson"),
    }
    called = {}

    monkeypatch.setattr(pipeline, "load_cfg_from_case_or_raise", lambda path: SimpleNamespace())

    def _fake_generate(case_path_arg: str, cfg):
        called["case_path"] = case_path_arg
        called["cfg"] = cfg
        return expected

    monkeypatch.setattr(pipeline, "generate_vanos_from_supports_service", _fake_generate)

    response = client.post(
        "/api/v1/vanos/generate-from-supports",
        json={"case_path": str(case_path)},
    )

    assert response.status_code == 200
    assert response.json()["created"] is True
    assert response.json()["vanos_count"] == 2
    assert called["case_path"] == str(case_path)


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


def test_worst_supports_geojson_enrichment_keeps_existing_metrics():
    if pipeline is None:
        pytest.skip("dependencias de integracion no instaladas en el entorno")

    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "vperp_min": 1.25,
                    "w_speed": 8.5,
                    "w_dir": 250.74085312139727,
                    "alpha": 12.75,
                    "from_ap": "AP-5",
                    "to_ap": "AP-6",
                },
                "geometry": {"type": "Point", "coordinates": [-5.8, 43.3]},
            }
        ],
    }

    enriched = pipeline._enrich_worst_supports_geojson(geojson)
    props = enriched["features"][0]["properties"]

    assert props["vperp_min"] == 1.25
    assert props["w_speed"] == 8.5
    assert props["alpha"] == 12.75
    assert props["critical_metric"] == 1.25
    assert props["critical_metric_unit"] == "m/s"
    assert props["critical_reason"] == "Menor componente perpendicular sobre el vano entre escenarios WindNinja"
    assert props["wind_speed"] == 8.5
    assert props["wind_speed_unit"] == "m/s"
    assert props["wind_direction"] == 250.74085312139727
    assert props["angle_relative"] == 12.75
    assert props["angle_relative_unit"] == "deg"
    assert props["from_support"] == "AP-5"
    assert props["to_support"] == "AP-6"
    assert props["span_label"] == "AP-5 -> AP-6"


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


def _windninja_cfg(tmp_path: Path):
    dem = tmp_path / "MDT_WN" / "mdt.tif"
    dem.parent.mkdir(parents=True)
    dem.touch()
    weather = tmp_path / "Weather_Input_Data" / "WN_PointInit_Path.csv"
    weather.parent.mkdir(parents=True)
    weather.touch()
    return SimpleNamespace(
        in_weather_file=weather,
        out_mdt_tif=dem,
    )


def _windninja_result(returncode: int = 0):
    return {
        "summary_txt_path": "summary.txt",
        "command_txt_path": "command.txt",
        "stdout_tail_txt_path": "stdout.txt",
        "stderr_tail_txt_path": "stderr.txt",
        "new_files_txt_path": "new_files.txt",
        "new_files": ["a.asc"],
        "returncode": returncode,
    }


def test_run_windninja_failure_does_not_call_postprocess(client, monkeypatch, tmp_path):
    import app.scripts.run_local_pipeline as local_pipeline

    cfg = _windninja_cfg(tmp_path)
    called = {"rename": 0, "worst": 0, "rose": 0}
    monkeypatch.setattr(pipeline, "load_cfg_from_case_or_raise", lambda _: cfg)
    monkeypatch.setattr(local_pipeline, "run_windninja_stage", lambda _cfg: _windninja_result(returncode=2))
    monkeypatch.setattr(pipeline, "_run_rename_for_cfg", lambda _cfg: called.__setitem__("rename", called["rename"] + 1))
    monkeypatch.setattr(pipeline, "_run_worst_supports_for_cfg", lambda _cfg, top_n=4: called.__setitem__("worst", called["worst"] + 1))
    monkeypatch.setattr(pipeline, "_run_wind_rose_for_cfg", lambda _cfg: called.__setitem__("rose", called["rose"] + 1))

    response = client.post("/api/v1/pipeline/run-windninja", json={"case_path": str(tmp_path)})

    assert response.status_code == 500
    assert called == {"rename": 0, "worst": 0, "rose": 0}


def test_run_windninja_ok_runs_rename_and_worst_supports(client, monkeypatch, tmp_path):
    import app.scripts.run_local_pipeline as local_pipeline

    cfg = _windninja_cfg(tmp_path)
    called = {"rename": 0, "worst": 0, "rose": 0}
    monkeypatch.setattr(pipeline, "load_cfg_from_case_or_raise", lambda _: cfg)
    monkeypatch.setattr(local_pipeline, "run_windninja_stage", lambda _cfg: _windninja_result())

    def _rename(_cfg):
        called["rename"] += 1
        return {"status": "ok", "summary": "rename.txt"}

    def _worst(_cfg, top_n=4):
        called["worst"] += 1
        assert top_n == 4
        return {"top_n": top_n, "worst": [{"idx": 1}]}

    def _rose(_cfg):
        called["rose"] += 1
        return {"status": "ok", "plot": "wind_rose.png"}

    monkeypatch.setattr(pipeline, "_run_rename_for_cfg", _rename)
    monkeypatch.setattr(pipeline, "_run_worst_supports_for_cfg", _worst)
    monkeypatch.setattr(pipeline, "_run_wind_rose_for_cfg", _rose)

    response = client.post("/api/v1/pipeline/run-windninja", json={"case_path": str(tmp_path)})

    assert response.status_code == 200
    body = response.json()
    assert body["windninja_success"] is True
    assert body["rename_success"] is True
    assert body["worst_supports_success"] is True
    assert body["worst_supports_count"] == 4
    assert body["wind_rose_success"] is True
    assert body["wind_rose_output"]["plot"] == "wind_rose.png"
    assert body["postprocess_warnings"] == []
    assert called == {"rename": 1, "worst": 1, "rose": 1}


def test_run_windninja_rename_failure_warns_and_skips_worst(client, monkeypatch, tmp_path):
    import app.scripts.run_local_pipeline as local_pipeline

    cfg = _windninja_cfg(tmp_path)
    called = {"worst": 0, "rose": 0}
    monkeypatch.setattr(pipeline, "load_cfg_from_case_or_raise", lambda _: cfg)
    monkeypatch.setattr(local_pipeline, "run_windninja_stage", lambda _cfg: _windninja_result())
    monkeypatch.setattr(pipeline, "_run_rename_for_cfg", lambda _cfg: (_ for _ in ()).throw(RuntimeError("rename boom")))
    monkeypatch.setattr(pipeline, "_run_worst_supports_for_cfg", lambda _cfg, top_n=4: called.__setitem__("worst", called["worst"] + 1))
    monkeypatch.setattr(pipeline, "_run_wind_rose_for_cfg", lambda _cfg: called.__setitem__("rose", called["rose"] + 1) or {"status": "ok"})

    response = client.post("/api/v1/pipeline/run-windninja", json={"case_path": str(tmp_path)})

    assert response.status_code == 200
    body = response.json()
    assert body["windninja_success"] is True
    assert body["rename_success"] is False
    assert "rename boom" in body["rename_warning"]
    assert body["worst_supports_success"] is False
    assert called["worst"] == 0
    assert body["wind_rose_success"] is True
    assert called["rose"] == 1


def test_run_windninja_worst_supports_failure_warns(client, monkeypatch, tmp_path):
    import app.scripts.run_local_pipeline as local_pipeline

    cfg = _windninja_cfg(tmp_path)
    monkeypatch.setattr(pipeline, "load_cfg_from_case_or_raise", lambda _: cfg)
    monkeypatch.setattr(local_pipeline, "run_windninja_stage", lambda _cfg: _windninja_result())
    monkeypatch.setattr(pipeline, "_run_rename_for_cfg", lambda _cfg: {"status": "ok"})
    monkeypatch.setattr(
        pipeline,
        "_run_worst_supports_for_cfg",
        lambda _cfg, top_n=4: (_ for _ in ()).throw(RuntimeError("worst boom")),
    )
    monkeypatch.setattr(pipeline, "_run_wind_rose_for_cfg", lambda _cfg: {"status": "ok", "plot": "wind_rose.png"})

    response = client.post("/api/v1/pipeline/run-windninja", json={"case_path": str(tmp_path)})

    assert response.status_code == 200
    body = response.json()
    assert body["rename_success"] is True
    assert body["worst_supports_success"] is False
    assert "worst boom" in body["worst_supports_warning"]
    assert body["wind_rose_success"] is True


def test_run_windninja_wind_rose_failure_warns(client, monkeypatch, tmp_path):
    import app.scripts.run_local_pipeline as local_pipeline

    cfg = _windninja_cfg(tmp_path)
    monkeypatch.setattr(pipeline, "load_cfg_from_case_or_raise", lambda _: cfg)
    monkeypatch.setattr(local_pipeline, "run_windninja_stage", lambda _cfg: _windninja_result())
    monkeypatch.setattr(pipeline, "_run_rename_for_cfg", lambda _cfg: {"status": "ok"})
    monkeypatch.setattr(pipeline, "_run_worst_supports_for_cfg", lambda _cfg, top_n=4: {"top_n": top_n, "worst": []})
    monkeypatch.setattr(
        pipeline,
        "_run_wind_rose_for_cfg",
        lambda _cfg: (_ for _ in ()).throw(RuntimeError("rose boom")),
    )

    response = client.post("/api/v1/pipeline/run-windninja", json={"case_path": str(tmp_path)})

    assert response.status_code == 200
    body = response.json()
    assert body["windninja_success"] is True
    assert body["rename_success"] is True
    assert body["worst_supports_success"] is True
    assert body["wind_rose_success"] is False
    assert "rose boom" in body["wind_rose_warning"]


def test_run_rename_for_cfg_calls_rename_service_directly(monkeypatch, tmp_path):
    from app.services.wind import rename_files_service

    cfg = SimpleNamespace(
        general_path=tmp_path / "Caso Demo-01",
        out_weather_point_file=tmp_path / "Weather_Input_Data" / "WN_input_Point_1.csv",
        out_wn=tmp_path / "OUT_WN",
        out_wn_ren=tmp_path / "OUT_WN_REN",
    )
    called = {}

    def _run_rename(**kwargs):
        called.update(kwargs)
        return None, {}, None

    monkeypatch.setattr(rename_files_service, "run_rename", _run_rename)

    result = pipeline._run_rename_for_cfg(cfg)

    assert result == {
        "status": "ok",
        "apply": True,
        "summary": str(Path("out") / "rename" / "rename_summary.txt"),
        "plan": str(Path("out") / "rename" / "rename_plan.csv"),
        "diagnostics": str(Path("out") / "rename" / "rename_diagnostics.csv"),
    }
    assert called == {
        "cases_csv": cfg.out_weather_point_file,
        "out_dir": cfg.out_wn,
        "dest_dir": cfg.out_wn_ren,
        "diag_csv": Path("out") / "rename" / "rename_diagnostics.csv",
        "summary_txt": Path("out") / "rename" / "rename_summary.txt",
        "plan_csv": Path("out") / "rename" / "rename_plan.csv",
        "prefix": "MDT_WN_Caso_Demo_01_point",
        "recursive": False,
        "apply": True,
    }


def test_run_wind_rose_for_cfg_calls_runner_service_directly(monkeypatch):
    from app.services.wind import wind_rose_runner_service

    cfg = SimpleNamespace()
    called = {}

    def _run_wind_rose_for_cfg(arg):
        called["cfg"] = arg
        return {
            "out_csv_path": Path("out") / "wind_rose" / "wind_source_data.csv",
            "out_plot_path": Path("out") / "wind_rose" / "wind_rose.png",
            "out_weibull_path": Path("out") / "wind_rose" / "weibull_fit.png",
            "cfg_csv_path": Path("case") / "WR" / "wind.csv",
        }

    monkeypatch.setattr(wind_rose_runner_service, "run_wind_rose_for_cfg", _run_wind_rose_for_cfg)

    result = pipeline._run_wind_rose_for_cfg(cfg)

    assert called["cfg"] is cfg
    assert result == {
        "status": "ok",
        "csv": str(Path("out") / "wind_rose" / "wind_source_data.csv"),
        "plot": str(Path("out") / "wind_rose" / "wind_rose.png"),
        "weibull": str(Path("out") / "wind_rose" / "weibull_fit.png"),
        "cfg_csv": str(Path("case") / "WR" / "wind.csv"),
    }


def test_manual_run_rename_endpoint_still_uses_common_logic(client, monkeypatch, tmp_path):
    cfg = SimpleNamespace()
    monkeypatch.setattr(pipeline, "load_cfg_from_case_or_raise", lambda _: cfg)
    monkeypatch.setattr(pipeline, "_run_rename_for_cfg", lambda _cfg: {"status": "ok", "summary": "rename.txt"})

    response = client.post("/api/v1/pipeline/run-rename", json={"case_path": str(tmp_path)})

    assert response.status_code == 200
    assert response.json()["summary"] == "rename.txt"


def test_manual_run_wind_rose_endpoint_still_uses_common_logic(client, monkeypatch, tmp_path):
    cfg = SimpleNamespace()
    monkeypatch.setattr(pipeline, "load_cfg_from_case_or_raise", lambda _: cfg)
    monkeypatch.setattr(pipeline, "_run_wind_rose_for_cfg", lambda _cfg: {"status": "ok", "plot": "wind_rose.png"})

    response = client.post("/api/v1/pipeline/run-wind-rose", json={"case_path": str(tmp_path)})

    assert response.status_code == 200
    assert response.json()["plot"] == "wind_rose.png"


def test_manual_worst_supports_endpoint_still_uses_common_logic(client, monkeypatch, tmp_path):
    cfg = SimpleNamespace()
    monkeypatch.setattr(pipeline, "load_cfg_from_case_or_raise", lambda _: cfg)
    monkeypatch.setattr(pipeline, "_run_worst_supports_for_cfg", lambda _cfg, top_n=4: {"top_n": top_n, "worst": []})

    response = client.post("/api/v1/analysis/worst-supports", json={"case_path": str(tmp_path)})

    assert response.status_code == 200
    assert response.json()["top_n"] == 4
