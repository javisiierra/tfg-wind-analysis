from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Point

from app.services.dashboard.weather_dashboard_service import DashboardDataError, WeatherDashboardService
from app.services.domain.generation_service import (
    DEFAULT_DOMAIN_BUFFER_M,
    DomainGenerationError,
    DomainGenerationService,
)


def _write_supports(path: Path, crs: str | None = "EPSG:25830") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    points = (
        [Point(-5.80, 43.30), Point(-5.81, 43.30), Point(-5.79, 43.31)]
        if crs == "EPSG:4326"
        else [Point(500100, 4800000), Point(500000, 4800000), Point(500200, 4800100)]
    )
    gpd.GeoDataFrame(
        {"support_order": [2, 1, 3]},
        geometry=points,
        crs=crs,
    ).to_file(path)


def _write_trace(path: Path, crs: str | None = "EPSG:25830") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    gpd.GeoDataFrame(
        {"name": ["trace"]},
        geometry=[LineString([(500000, 4800000), (500100, 4800000), (500200, 4800100)])],
        crs=crs,
    ).to_file(path)


def test_same_supports_input_generates_same_canonical_domain(tmp_path: Path):
    service = DomainGenerationService()
    supports = tmp_path / "Apoyos" / "apoyos.shp"
    _write_supports(supports)

    first = service.generate_from_supports(tmp_path, supports)
    first_domain = gpd.read_file(first.domain_shp)
    second = service.generate_from_supports(tmp_path, supports)
    second_domain = gpd.read_file(second.domain_shp)

    assert first.to_dict() == second.to_dict()
    assert first_domain.geometry.iloc[0].equals_exact(second_domain.geometry.iloc[0], tolerance=0)
    assert first.buffer_m == DEFAULT_DOMAIN_BUFFER_M
    assert set(first.to_dict()) == {"domain_shp", "domain_geojson", "source", "buffer_m", "crs"}


def test_trace_and_supports_use_same_buffer_policy_and_output_crs(tmp_path: Path):
    service = DomainGenerationService(default_buffer_m=275)
    supports = tmp_path / "Apoyos" / "apoyos.shp"
    supports_wgs84 = tmp_path / "ApoyosWgs84" / "apoyos.shp"
    trace = tmp_path / "SHP" / "traza.shp"
    _write_supports(supports)
    _write_supports(supports_wgs84, crs="EPSG:4326")
    _write_trace(trace)

    supports_result = service.generate_from_supports(tmp_path, supports)
    supports_domain = gpd.read_file(supports_result.domain_shp)
    trace_result = service.generate_from_trace(tmp_path, trace)
    trace_domain = gpd.read_file(trace_result.domain_shp)

    assert supports_result.buffer_m == trace_result.buffer_m == 275
    assert supports_domain.geometry.iloc[0].equals_exact(trace_domain.geometry.iloc[0], tolerance=0)
    assert trace_domain.crs.to_epsg() == 25830
    assert Path(trace_result.domain_geojson).exists()
    reprojected = service.generate_from_supports(tmp_path, supports_wgs84)
    assert gpd.read_file(reprojected.domain_shp).crs.to_epsg() == 25830


def test_missing_crs_is_normalized_and_invalid_buffer_is_rejected(tmp_path: Path):
    service = DomainGenerationService()
    trace = tmp_path / "SHP" / "traza.shp"
    _write_trace(trace, crs=None)

    result = service.generate_from_trace(tmp_path, trace)

    assert gpd.read_file(result.domain_shp).crs.to_epsg() == 25830
    with pytest.raises(DomainGenerationError, match="mayor que 0"):
        service.generate_from_trace(tmp_path, trace, buffer_m=0)


def test_dashboard_reports_domain_missing_without_mutating_case(tmp_path: Path):
    trace = tmp_path / "SHP" / "traza.shp"
    _write_trace(trace)
    service = WeatherDashboardService()

    with pytest.raises(DashboardDataError) as exc:
        service._resolve_domain_descriptor({"case_path": str(tmp_path)})

    assert exc.value.error_code == "DOMAIN_MISSING"
    assert not (tmp_path / "SHP" / "dominio.shp").exists()
    assert not (tmp_path / "SHP" / "dominio.geojson").exists()
