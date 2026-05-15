from types import SimpleNamespace
import importlib
import sys
import types

import pytest


class P:
    geom_type = "Point"
    is_empty = False

    def __init__(self, x, y):
        self.x, self.y = x, y


class L:
    geom_type = "LineString"
    is_empty = False

    def __init__(self, coords):
        self.coords = [(float(x), float(y)) for x, y in coords]


class Poly:
    geom_type = "Polygon"
    is_empty = False

    def __init__(self, coords):
        self.exterior = SimpleNamespace(coords=[(float(x), float(y)) for x, y in coords])


fake_geom = types.SimpleNamespace(Point=P, Polygon=Poly)
sys.modules.setdefault("shapely.geometry", fake_geom)
sys.modules.setdefault("shapely", types.SimpleNamespace(geometry=fake_geom))
sys.modules.setdefault("geopandas", types.SimpleNamespace())
svc = importlib.import_module("app.services.domain.geometry_service")


def test_iter_coords_supports_common_geometries():
    assert svc.iter_coords(P(1, 2)) == [(1, 2)]
    assert svc.iter_coords(L([(0, 0), (1, 1)])) == [(0.0, 0.0), (1.0, 1.0)]
    poly_coords = svc.iter_coords(Poly([(0, 0), (2, 0), (2, 2), (0, 0)]))
    assert (2.0, 2.0) in poly_coords


def test_iter_coords_raises_for_unsupported_geometry():
    class CustomGeom:
        is_empty = False
        geom_type = "Unsupported"

    with pytest.raises(ValueError):
        svc.iter_coords(CustomGeom())

