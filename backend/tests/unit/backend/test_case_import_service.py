from pathlib import Path
import types
import sys
import pytest
from fastapi import HTTPException
import importlib


def _load_service_module():
    fake_pd = types.SimpleNamespace(DataFrame=lambda *a, **k: None)
    fake_gpd = types.SimpleNamespace(GeoDataFrame=lambda *a, **k: None)
    fake_geom = types.SimpleNamespace(
        Point=lambda x, y: (x, y),
        Polygon=object,
        box=lambda *a, **k: ("box", a),
    )
    fake_wkt = types.SimpleNamespace(loads=lambda w: w)
    monkey = {
        "pandas": fake_pd,
        "geopandas": fake_gpd,
        "shapely": types.SimpleNamespace(geometry=fake_geom, wkt=fake_wkt),
        "shapely.geometry": fake_geom,
        "shapely.wkt": fake_wkt,
    }
    previous = {k: sys.modules.get(k) for k in monkey}
    sys.modules.update(monkey)
    try:
        return importlib.import_module("app.services.case_import.import_folder_service")
    finally:
        for k, v in previous.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


svc = _load_service_module()


def test_find_support_excel_prefers_apoyos_folder(tmp_path: Path):
    (tmp_path / "foo.xlsx").write_text("x")
    target = tmp_path / "Apoyos" / "supports.xlsx"
    target.parent.mkdir()
    target.write_text("x")

    found = svc._find_support_excel(tmp_path)

    assert found == target


def test_find_support_excel_raises_when_none(tmp_path: Path):
    with pytest.raises(HTTPException) as exc:
        svc._find_support_excel(tmp_path)
    assert exc.value.status_code == 404


def test_infer_coordinate_columns_and_wkt_error():
    df = types.SimpleNamespace(columns=["Longitude", "Latitude", "name"])
    assert svc._infer_coordinate_columns(df) == ("Longitude", "Latitude")

    with pytest.raises(HTTPException) as exc:
        svc._infer_coordinate_columns(types.SimpleNamespace(columns=["WKT"]))
    assert exc.value.status_code == 400


def test_write_supports_shapefile_builds_geometry_and_crs(monkeypatch, tmp_path: Path):
    calls = {}

    class DummyGDF:
        def __init__(self, data, geometry, crs):
            calls["geometry"] = geometry
            calls["crs"] = crs
            self.data = data

        def to_file(self, path, **kwargs):
            calls["path"] = path
            calls["kwargs"] = kwargs

    monkeypatch.setattr(svc.gpd, "GeoDataFrame", DummyGDF)

    class FakeDF:
        columns = ["X", "Y", "id"]

        def __getitem__(self, key):
            return {"X": [1, 2], "Y": [3, 4]}[key]

        def drop(self, columns):
            return {"id": ["a", "b"]}

    df = FakeDF()
    out = tmp_path / "SHP" / "apoyos.shp"
    gdf = svc._write_supports_shapefile(df, "X", "Y", out, epsg=4326)

    assert isinstance(gdf, DummyGDF)
    assert len(calls["geometry"]) == 2
    assert calls["crs"] == "EPSG:4326"
    assert calls["path"] == out
