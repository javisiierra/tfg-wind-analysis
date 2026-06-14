from importlib.util import find_spec
from types import SimpleNamespace

import pytest

geopandas_available = find_spec("geopandas") is not None
shapely_available = find_spec("shapely") is not None

if geopandas_available and shapely_available:
    import geopandas as gpd
    from shapely.geometry import LineString, Point

    from app.services.vanos.vanos_from_supports_service import (
        VanosGenerationError,
        canonical_vanos_shp_path,
        generate_vanos_from_supports,
    )


pytestmark = pytest.mark.skipif(
    not (geopandas_available and shapely_available),
    reason="geopandas/shapely no están disponibles",
)


def _cfg(case_path):
    return SimpleNamespace(
        out_apoyos_shp=case_path / "Apoyos" / "apoyos.shp",
        out_vanos_shp=case_path / "SHP" / "vanos.shp",
        apoyos_epsg_arg=25830,
    )


def _write_supports(case_path, points):
    supports_dir = case_path / "Apoyos"
    supports_dir.mkdir(parents=True, exist_ok=True)
    gdf = gpd.GeoDataFrame(
        {
            "id": [f"AP-{idx}" for idx in range(1, len(points) + 1)],
            "support_order": list(range(1, len(points) + 1)),
        },
        geometry=[Point(x, y) for x, y in points],
        crs="EPSG:25830",
    )
    gdf.to_file(supports_dir / "apoyos.shp", driver="ESRI Shapefile", encoding="UTF-8")


def test_existing_vanos_are_not_regenerated(tmp_path):
    case_path = tmp_path / "case_existing"
    (case_path / "SHP").mkdir(parents=True)
    existing = gpd.GeoDataFrame(
        {"id": ["V-1"]},
        geometry=[LineString([(0, 0), (1, 0)])],
        crs="EPSG:25830",
    )
    existing.to_file(case_path / "SHP" / "vanos.shp", driver="ESRI Shapefile", encoding="UTF-8")

    result = generate_vanos_from_supports(case_path, _cfg(case_path))

    assert result["created"] is False
    assert result["message"] == "La capa de vanos ya existe"
    assert result["vanos_count"] == 1


def test_less_than_two_supports_returns_clear_error(tmp_path):
    case_path = tmp_path / "case_one_support"
    _write_supports(case_path, [(0, 0)])

    with pytest.raises(VanosGenerationError, match="Se necesitan al menos 2 apoyos"):
        generate_vanos_from_supports(case_path, _cfg(case_path))


def test_three_supports_generate_two_vanos_in_layers_path(tmp_path):
    case_path = tmp_path / "case_three_supports"
    _write_supports(case_path, [(20, 0), (10, 0), (30, 0)])

    result = generate_vanos_from_supports(case_path, _cfg(case_path))

    output_shp = canonical_vanos_shp_path(case_path)
    output_geojson = case_path / "SHP" / "vanos.geojson"
    generated = gpd.read_file(output_shp)

    assert result["created"] is True
    assert result["vanos_count"] == 2
    assert output_shp.exists()
    assert output_geojson.exists()
    assert result["output_shp"] == str(output_shp)
    assert len(generated) == 2
