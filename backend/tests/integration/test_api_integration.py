from pathlib import Path
from types import SimpleNamespace
from importlib.util import find_spec

import pytest

HAS_FASTAPI = find_spec("fastapi") is not None
HAS_GIS = find_spec("geopandas") is not None and find_spec("shapely") is not None
HAS_RASTER = find_spec("rasterio") is not None and find_spec("pyproj") is not None
HAS_EXCEL = find_spec("pandas") is not None and find_spec("openpyxl") is not None

if HAS_FASTAPI:
    from fastapi import HTTPException
    from fastapi.testclient import TestClient
    from app.api.v1 import pipeline
    from app.api.v1.layer_response import _enrich_worst_supports_geojson
    from app.core.config import Config
    from app.main import app
else:
    TestClient = None
    pipeline = None
    _enrich_worst_supports_geojson = None
    Config = None
    app = None

if HAS_GIS:
    import geopandas as gpd
    from shapely.geometry import LineString, Point

if HAS_EXCEL:
    import pandas as pd


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


@pytest.mark.skipif(not (HAS_GIS and HAS_EXCEL), reason="dependencias GIS/Excel no disponibles")
def test_import_folder_creates_real_case_artifacts_compatible_with_domain_and_vanos(client, tmp_path):
    from app.services.domain.generation_service import DomainGenerationService
    from app.services.vanos.vanos_from_supports_service import generate_vanos_from_supports

    case_path = tmp_path / "cliente_minimo"
    input_apoyos_dir = case_path / "Apoyos"
    input_apoyos_dir.mkdir(parents=True)

    excel_path = input_apoyos_dir / "apoyos_cliente.xlsx"
    pd.DataFrame(
        {
            "id": ["AP-1", "AP-2", "AP-3"],
            "support_order": [1, 2, 3],
            "X": [500000.0, 500100.0, 500200.0],
            "Y": [4800000.0, 4800000.0, 4800100.0],
        }
    ).to_excel(excel_path, index=False)

    trace_path = case_path / "traza_cliente.shp"
    gpd.GeoDataFrame(
        {"name": ["trace"]},
        geometry=[LineString([(500000, 4800000), (500100, 4800000), (500200, 4800100)])],
        crs="EPSG:25830",
    ).to_file(trace_path, driver="ESRI Shapefile", encoding="UTF-8")

    response = client.post("/api/v1/case/import-folder", json={"input_path": str(case_path)})

    assert response.status_code == 200
    assert response.json() == {"case_path": str(case_path.resolve()), "status": "ready"}

    expected_dirs = [
        case_path / "SHP",
        case_path / "Apoyos",
        case_path / "MDT_WN",
        case_path / "Weather_Input_Data",
        case_path / "OUT_WN",
        case_path / "OUT_WN_REN",
        case_path / "WR",
    ]
    assert all(path.exists() and path.is_dir() for path in expected_dirs)

    copied_excel = case_path / "Apoyos" / f"Apoyos {case_path.name}.xlsx"
    named_supports_shp = case_path / "Apoyos" / f"Apoyos {case_path.name}.shp"
    generic_supports_shp = case_path / "Apoyos" / "apoyos.shp"
    supports_geojson = case_path / "Apoyos" / "apoyos.geojson"
    imported_trace_shp = case_path / "SHP" / "traza.shp"
    root_trace_shp = case_path / f"{case_path.name}.shp"
    domain_shp = case_path / "SHP" / "dominio.shp"
    domain_geojson = case_path / "SHP" / "dominio.geojson"

    for path in [
        copied_excel,
        named_supports_shp,
        generic_supports_shp,
        supports_geojson,
        imported_trace_shp,
        root_trace_shp,
        domain_shp,
        domain_geojson,
    ]:
        assert path.exists()

    supports = gpd.read_file(generic_supports_shp)
    assert len(supports) == 3
    assert supports.crs.to_epsg() == 25830
    assert supports.geometry.geom_type.tolist() == ["Point", "Point", "Point"]
    assert supports["id"].tolist() == ["AP-1", "AP-2", "AP-3"]
    order_column = "support_order" if "support_order" in supports.columns else "support_or"
    assert supports[order_column].astype(int).tolist() == [1, 2, 3]

    supports_json = gpd.read_file(supports_geojson)
    assert len(supports_json) == 3
    assert supports_json.crs.to_epsg() == 25830

    trace = gpd.read_file(imported_trace_shp)
    assert len(trace) == 1
    assert trace.crs.to_epsg() == 25830
    assert trace.geometry.iloc[0].geom_type == "LineString"

    domain_service = DomainGenerationService()
    domain_bounds = domain_service.read_domain_bounds_wgs84(case_path)
    assert domain_bounds is not None
    assert domain_bounds[1] == "dominio.geojson"

    cfg = Config.from_case_path(case_path)
    assert cfg.in_xlsx == copied_excel
    assert cfg.out_apoyos_shp == generic_supports_shp
    assert cfg.in_shp == domain_shp

    vanos_result = generate_vanos_from_supports(case_path, cfg)
    vanos_shp = case_path / "SHP" / "vanos.shp"
    vanos_geojson = case_path / "SHP" / "vanos.geojson"
    assert vanos_result["created"] is True
    assert vanos_result["vanos_count"] == 2
    assert vanos_shp.exists()
    assert vanos_geojson.exists()
    assert len(gpd.read_file(vanos_shp)) == 2


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


def test_with_domain_input_copies_frozen_config(tmp_path):
    domain_path = tmp_path / "SHP" / "dominio.shp"
    cfg = Config(general_path=tmp_path)

    updated = pipeline._with_domain_input(cfg, domain_path)

    assert cfg.in_shp is None
    assert updated.in_shp == domain_path


def test_prepare_dem_generates_missing_domain_then_dem(client, monkeypatch, tmp_path):
    case_path = tmp_path / "case_prepare_new"
    case_path.mkdir()
    domain_path = case_path / "SHP" / "dominio.shp"
    called = {"domain": 0, "dem": 0}

    monkeypatch.setattr(pipeline, "get_existing_domain_path", lambda _: None)

    def _generate(case_path_arg: str):
        called["domain"] += 1
        assert case_path_arg == str(case_path)
        return {"domain_shp": str(domain_path)}

    def _dem(case_path_arg: str):
        called["dem"] += 1
        assert case_path_arg == str(case_path)
        return {"status": "ok", "out_mdt_tif": str(case_path / "MDT_WN" / "terrain.tif")}

    monkeypatch.setattr(pipeline, "_generate_domain_from_supports_logic", _generate)
    monkeypatch.setattr(pipeline, "_generate_dem_for_case", _dem)

    response = client.post("/api/v1/domain/prepare-dem", json={"case_path": str(case_path)})

    assert response.status_code == 200
    assert response.json()["domain"]["status"] == "generated"
    assert called == {"domain": 1, "dem": 1}


def test_prepare_dem_reuses_existing_domain(client, monkeypatch, tmp_path):
    case_path = tmp_path / "case_prepare_existing"
    domain_path = case_path / "SHP" / "dominio.shp"
    domain_path.parent.mkdir(parents=True)
    domain_path.touch()

    monkeypatch.setattr(pipeline, "get_existing_domain_path", lambda _: domain_path)
    monkeypatch.setattr(
        pipeline,
        "_generate_domain_from_supports_logic",
        lambda *_: (_ for _ in ()).throw(AssertionError("domain should be reused")),
    )
    monkeypatch.setattr(pipeline, "_generate_dem_for_case", lambda _: {"status": "ok"})

    response = client.post("/api/v1/domain/prepare-dem", json={"case_path": str(case_path)})

    assert response.status_code == 200
    assert response.json()["domain"]["status"] == "reused"
    assert response.json()["domain"]["path"] == str(domain_path)


def test_prepare_dem_without_domain_or_supports_returns_controlled_error(client, monkeypatch, tmp_path):
    case_path = tmp_path / "case_prepare_missing"
    case_path.mkdir()
    monkeypatch.setattr(pipeline, "get_existing_domain_path", lambda _: None)
    monkeypatch.setattr(
        pipeline,
        "_generate_domain_from_supports_logic",
        lambda *_: (_ for _ in ()).throw(HTTPException(status_code=400, detail="No existen apoyos para generar el dominio.")),
    )

    response = client.post("/api/v1/domain/prepare-dem", json={"case_path": str(case_path)})

    assert response.status_code == 400
    assert response.json()["detail"] == "No existen apoyos para generar el dominio."


def test_prepare_dem_failure_keeps_generated_domain_and_reports_stage(client, monkeypatch, tmp_path):
    case_path = tmp_path / "case_prepare_dem_failure"
    case_path.mkdir()
    domain_path = case_path / "SHP" / "dominio.shp"
    monkeypatch.setattr(pipeline, "get_existing_domain_path", lambda _: None)

    def _generate(_):
        domain_path.parent.mkdir(parents=True)
        domain_path.touch()
        return {"domain_shp": str(domain_path)}

    monkeypatch.setattr(pipeline, "_generate_domain_from_supports_logic", _generate)
    monkeypatch.setattr(
        pipeline,
        "_generate_dem_for_case",
        lambda _: (_ for _ in ()).throw(HTTPException(status_code=500, detail={"error": "download failed"})),
    )

    response = client.post("/api/v1/domain/prepare-dem", json={"case_path": str(case_path)})

    assert response.status_code == 500
    assert response.json()["detail"]["stage"] == "dem"
    assert domain_path.exists()


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

    enriched = _enrich_worst_supports_geojson(geojson)
    props = enriched["features"][0]["properties"]

    assert "vperp_min" not in props
    assert "w_speed" not in props
    assert "alpha" not in props
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


def test_layer_geojson_normalization_exposes_canonical_support_and_span_fields():
    from app.api.v1.layer_response import normalize_layer_geojson

    supports = normalize_layer_geojson(
        {
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {"id": "7", "sup_order": 7, "sup_total": 9}}],
        },
        "apoyos",
    )
    spans = normalize_layer_geojson(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"id": "V-1", "from_ap": "AP-7", "to_ap": "AP-8", "direccion": 45},
                }
            ],
        },
        "vanos",
    )

    assert supports["features"][0]["properties"] == {"id": "AP-7", "support_order": 7, "support_total": 9}
    assert spans["features"][0]["properties"] == {
        "id": "V-1",
        "from_support": "AP-7",
        "to_support": "AP-8",
        "direction_deg": 45.0,
    }


def _write_ascii_grid(path: Path, rows: list[list[float]]) -> None:
    path.write_text(
        "\n".join(
            [
                "ncols 4",
                "nrows 4",
                "xllcorner 499950",
                "yllcorner 4799950",
                "cellsize 100",
                "NODATA_value -9999",
                *[" ".join(str(value) for value in row) for row in rows],
            ]
        )
        + "\n",
        encoding="utf-8",
    )


@pytest.mark.skipif(not (HAS_GIS and HAS_RASTER), reason="dependencias GIS/raster no disponibles")
def test_worst_supports_uses_real_vanos_and_synthetic_windninja_rasters(client, tmp_path):
    from pyproj import CRS

    from app.core.config import Config
    from app.services.analysis.worst_supports_service import compute_worst_supports
    from app.services.vanos.vanos_from_supports_service import generate_vanos_from_supports

    case_path = tmp_path / "case_worst_raster"
    supports_path = case_path / "Apoyos" / "apoyos.shp"
    supports_path.parent.mkdir(parents=True)
    gpd.GeoDataFrame(
        {
            "id": ["AP-1", "AP-2", "AP-3"],
            "support_order": [1, 2, 3],
        },
        geometry=[
            Point(500000, 4800000),
            Point(500200, 4800000),
            Point(500200, 4800200),
        ],
        crs="EPSG:25830",
    ).to_file(supports_path, driver="ESRI Shapefile", encoding="UTF-8")

    cfg = Config.from_case_path(case_path)
    vanos_result = generate_vanos_from_supports(case_path, cfg)
    out_wn_ren = case_path / "OUT_WN_REN"
    out_wn_ren.mkdir(parents=True)

    _write_ascii_grid(
        out_wn_ren / "synthetic_speed.asc",
        [
            [1, 1, 1, 1],
            [1, 1, 1, 1],
            [1, 1, 8, 1],
            [1, 10, 1, 1],
        ],
    )
    _write_ascii_grid(
        out_wn_ren / "synthetic_ang.asc",
        [
            [0, 0, 0, 0],
            [0, 0, 0, 0],
            [0, 0, 90, 0],
            [0, 90, 0, 0],
        ],
    )
    (out_wn_ren / "synthetic_speed.prj").write_text(
        CRS.from_epsg(25830).to_wkt(),
        encoding="utf-8",
    )

    result = compute_worst_supports(cfg, top_n=2)

    assert vanos_result["created"] is True
    assert result["top_n"] == 2
    assert Path(result["csv"]).exists()
    assert Path(result["shp"]) == case_path / "Calculos" / f"{case_path.name}_v_perp_min.shp"
    assert Path(result["shp"]).exists()
    assert len(result["worst"]) == 2

    first, second = result["worst"]
    assert first["span_label"] == "AP-1 -> AP-2"
    assert first["from_ap"] == "AP-1"
    assert first["to_ap"] == "AP-2"
    assert first["direccion"] == pytest.approx(90.0)
    assert first["wind_speed"] == pytest.approx(10.0)
    assert first["wind_dir"] == pytest.approx(90.0)
    assert first["alpha_eff"] == pytest.approx(0.0)
    assert first["v_perp"] == pytest.approx(0.0)

    assert second["span_label"] == "AP-2 -> AP-3"
    assert second["from_ap"] == "AP-2"
    assert second["to_ap"] == "AP-3"
    assert second["direccion"] == pytest.approx(0.0)
    assert second["wind_speed"] == pytest.approx(8.0)
    assert second["wind_dir"] == pytest.approx(90.0)
    assert second["alpha_eff"] == pytest.approx(90.0)
    assert second["v_perp"] == pytest.approx(8.0)

    out_gdf = gpd.read_file(result["shp"])
    assert len(out_gdf) == 2
    assert "vperp_min" in out_gdf.columns
    assert sorted(out_gdf["vperp_min"].round(6).tolist()) == [0.0, 8.0]

    layer_response = client.post(
        "/api/v1/layers/worst-supports",
        json={"case_path": str(case_path)},
    )

    assert layer_response.status_code == 200
    features = layer_response.json()["features"]
    assert len(features) == 2
    props_by_span = {feature["properties"]["span_label"]: feature["properties"] for feature in features}
    assert props_by_span["AP-1 -> AP-2"]["critical_metric"] == pytest.approx(0.0)
    assert props_by_span["AP-1 -> AP-2"]["wind_speed"] == pytest.approx(10.0)
    assert props_by_span["AP-1 -> AP-2"]["angle_relative"] == pytest.approx(0.0)
    assert props_by_span["AP-2 -> AP-3"]["critical_metric"] == pytest.approx(8.0)
    assert props_by_span["AP-2 -> AP-3"]["wind_direction"] == pytest.approx(90.0)


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


def test_run_preparation_generates_domain_with_domain_generation_service(client, monkeypatch, tmp_path):
    case_path = tmp_path / "case_prep_domain_service"
    case_path.mkdir(parents=True)
    supports_path = case_path / "Apoyos" / "apoyos.shp"
    supports_path.parent.mkdir(parents=True)
    supports_path.touch()
    domain_path = case_path / "SHP" / "dominio.shp"
    domain_path.parent.mkdir(parents=True)
    cfg = SimpleNamespace(
        in_shp=str(domain_path),
        out_shp=str(case_path / "Calculos" / "out.shp"),
        out_rec_shp=str(case_path / "Calculos" / "out_rec.shp"),
        out_rec_exp_shp=str(case_path / "SHP" / "dominio_exp.shp"),
        out_mdt_tif=str(case_path / "MDT_WN" / "mdt.tif"),
    )
    calls = {"generate_from_supports": 0}
    domain_lookup = iter([None, domain_path])

    class _DomainResult:
        def to_dict(self):
            return {
                "domain_shp": str(domain_path),
                "domain_geojson": str(domain_path.with_suffix(".geojson")),
                "source": "supports",
            }

    class _DomainService:
        def generate_from_supports(self, case_path_arg, supports_path_arg, buffer_m=None):
            calls["generate_from_supports"] += 1
            assert case_path_arg == str(case_path)
            assert supports_path_arg == supports_path
            domain_path.touch()
            return _DomainResult()

    monkeypatch.setattr(pipeline, "load_cfg_from_case_or_raise", lambda _: cfg)
    monkeypatch.setattr(pipeline, "get_existing_domain_path", lambda _: next(domain_lookup))
    monkeypatch.setattr(pipeline, "get_trace_shapefile_path", lambda _: None)
    monkeypatch.setattr(pipeline, "get_supports_shapefile_path", lambda _: supports_path)
    monkeypatch.setattr(pipeline, "domain_generation_service", _DomainService())
    monkeypatch.setattr(pipeline, "_ensure_vanos_for_preparation", lambda *_: {"status": "skipped"})
    monkeypatch.setattr(pipeline, "run_geometry_and_dem", lambda _cfg: {"minx": 0, "miny": 0, "maxx": 1, "maxy": 1})
    monkeypatch.setattr(pipeline, "_generate_weather_for_cfg", lambda _cfg: {"points": [], "station_files": []})

    response = client.post("/api/v1/pipeline/run-preparation", json={"case_path": str(case_path)})

    assert response.status_code == 200
    assert calls["generate_from_supports"] == 1
    assert response.json()["domain"]["source"] == "supports"


def test_run_preparation_generates_missing_vanos_in_backend(client, monkeypatch, tmp_path):
    case_path = tmp_path / "case_prep_vanos"
    domain_path = case_path / "SHP" / "dominio.shp"
    supports_path = case_path / "Apoyos" / "apoyos.shp"
    domain_path.parent.mkdir(parents=True)
    supports_path.parent.mkdir(parents=True)
    domain_path.touch()
    supports_path.touch()
    cfg = SimpleNamespace(
        in_shp=str(domain_path),
        out_shp=str(case_path / "Calculos" / "out.shp"),
        out_rec_shp=str(case_path / "Calculos" / "out_rec.shp"),
        out_rec_exp_shp=str(case_path / "SHP" / "dominio_exp.shp"),
        out_mdt_tif=str(case_path / "MDT_WN" / "mdt.tif"),
    )
    called = {"vanos": 0}

    def _generate_vanos(case_path_arg, cfg_arg):
        called["vanos"] += 1
        assert case_path_arg == str(case_path)
        assert cfg_arg is cfg
        return {"status": "ok", "created": True, "output_shp": str(case_path / "SHP" / "vanos.shp")}

    monkeypatch.setattr(pipeline, "load_cfg_from_case_or_raise", lambda _: cfg)
    monkeypatch.setattr(pipeline, "get_existing_domain_path", lambda _: domain_path)
    monkeypatch.setattr(pipeline, "find_existing_vanos_path", lambda *_: None)
    monkeypatch.setattr(pipeline, "get_supports_shapefile_path", lambda _: supports_path)
    monkeypatch.setattr(pipeline, "generate_vanos_from_supports_service", _generate_vanos)
    monkeypatch.setattr(pipeline, "run_geometry_and_dem", lambda _cfg: {"minx": 0, "miny": 0, "maxx": 1, "maxy": 1})
    monkeypatch.setattr(pipeline, "_generate_weather_for_cfg", lambda _cfg: {"points": [], "station_files": []})

    response = client.post("/api/v1/pipeline/run-preparation", json={"case_path": str(case_path)})

    assert response.status_code == 200
    assert called["vanos"] == 1
    assert response.json()["vanos"]["status"] == "generated"


@pytest.mark.skipif(not HAS_GIS, reason="geopandas/shapely no estan disponibles")
def test_run_preparation_generates_real_domain_and_vanos_with_external_edges_mocked(client, monkeypatch, tmp_path):
    case_path = tmp_path / "case_prep_semint"
    supports_path = case_path / "Apoyos" / "apoyos.shp"
    supports_path.parent.mkdir(parents=True)
    gpd.GeoDataFrame(
        {
            "id": ["AP-1", "AP-2", "AP-3"],
            "support_order": [1, 2, 3],
        },
        geometry=[
            Point(500000, 4800000),
            Point(500100, 4800000),
            Point(500200, 4800100),
        ],
        crs="EPSG:25830",
    ).to_file(supports_path, driver="ESRI Shapefile", encoding="UTF-8")

    called = {"dem": 0, "weather": 0, "run_towers": 0, "run_base": 0}

    def _fake_dem(cfg):
        called["dem"] += 1
        assert Path(cfg.in_shp) == case_path / "SHP" / "dominio.shp"
        Path(cfg.out_mdt_tif).parent.mkdir(parents=True, exist_ok=True)
        Path(cfg.out_mdt_tif).write_text("mock dem", encoding="utf-8")
        return {"minx": 500000.0, "miny": 4800000.0, "maxx": 500200.0, "maxy": 4800100.0}

    def _fake_weather(cfg):
        called["weather"] += 1
        weather_dir = Path(cfg.general_path) / "Weather_Input_Data"
        weather_dir.mkdir(parents=True, exist_ok=True)
        station_file = weather_dir / "WN_input_Point_1.csv"
        station_file.write_text("date_time,wind_speed,wind_direction\n2024-01-01T00:00:00Z,1,0\n", encoding="utf-8")
        station_list = weather_dir / "WN_PointInit_Path.csv"
        station_list.write_text("Station_File_List,\nWN_input_Point_1.csv\n", encoding="utf-8")
        return {
            "points": [{"name": "P1", "utm_x": 500000.0, "utm_y": 4800000.0}],
            "station_list_file": str(station_list),
            "station_files": [str(station_file)],
        }

    def _legacy_towers_called(*_args, **_kwargs):
        called["run_towers"] += 1
        raise AssertionError("run_towers should not be called by run-preparation")

    def _legacy_base_called(*_args, **_kwargs):
        called["run_base"] += 1
        raise AssertionError("run-base should not be called by run-preparation")

    monkeypatch.setattr(pipeline, "run_geometry_and_dem", _fake_dem)
    monkeypatch.setattr(pipeline, "_generate_weather_for_cfg", _fake_weather)
    monkeypatch.setattr(pipeline, "run_towers", _legacy_towers_called)
    monkeypatch.setattr(pipeline, "run_base_pipeline", _legacy_base_called)

    response = client.post("/api/v1/pipeline/run-preparation", json={"case_path": str(case_path)})

    assert response.status_code == 200
    body = response.json()

    domain_shp = case_path / "SHP" / "dominio.shp"
    domain_geojson = case_path / "SHP" / "dominio.geojson"
    vanos_shp = case_path / "SHP" / "vanos.shp"
    vanos_geojson = case_path / "SHP" / "vanos.geojson"
    dem_path = case_path / "MDT_WN" / f"MDT_WN_{case_path.name}.tif"
    station_list = case_path / "Weather_Input_Data" / "WN_PointInit_Path.csv"

    assert called == {"dem": 1, "weather": 1, "run_towers": 0, "run_base": 0}
    assert domain_shp.exists()
    assert domain_geojson.exists()
    assert vanos_shp.exists()
    assert vanos_geojson.exists()
    assert dem_path.exists()
    assert station_list.exists()
    assert len(gpd.read_file(domain_shp)) == 1
    assert len(gpd.read_file(vanos_shp)) == 2

    assert body["status"] == "ok"
    assert body["domain"]["source"] == "supports"
    assert body["domain"]["path"] == str(domain_shp)
    assert body["domain"]["domain_shp"] == str(domain_shp)
    assert body["domain"]["domain_geojson"] == str(domain_geojson)
    assert body["vanos"]["status"] == "generated"
    assert body["vanos"]["created"] is True
    assert body["vanos"]["vanos_count"] == 2
    assert body["vanos"]["output_shp"] == str(vanos_shp)
    assert body["vanos"]["output_geojson"] == str(vanos_geojson)
    assert body["dem"]["out_mdt_tif"] == str(dem_path)
    assert body["weather"]["station_list_file"] == str(station_list)
    assert body["weather"]["station_files"]
    assert body["geometry_results"] == {
        "minx": 500000.0,
        "miny": 4800000.0,
        "maxx": 500200.0,
        "maxy": 4800100.0,
    }


def _windninja_cfg(tmp_path: Path):
    domain = tmp_path / "SHP" / "dominio.shp"
    domain.parent.mkdir(parents=True)
    domain.touch()
    dem = tmp_path / "MDT_WN" / "mdt.tif"
    dem.parent.mkdir(parents=True)
    dem.touch()
    weather = tmp_path / "Weather_Input_Data" / "WN_PointInit_Path.csv"
    weather.parent.mkdir(parents=True)
    weather.touch()
    return SimpleNamespace(
        in_shp=domain,
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


def test_run_windninja_requires_canonical_domain(client, monkeypatch, tmp_path):
    cfg = _windninja_cfg(tmp_path)
    (tmp_path / "SHP" / "dominio.shp").unlink()
    monkeypatch.setattr(pipeline, "load_cfg_from_case_or_raise", lambda _: cfg)

    response = client.post("/api/v1/pipeline/run-windninja", json={"case_path": str(tmp_path)})

    assert response.status_code == 400
    assert "dominio canónico" in response.json()["detail"]


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
