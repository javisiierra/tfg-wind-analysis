from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
from pyproj import Transformer


def _point_from_geometry(geom) -> tuple[float, float]:
    """
    Devuelve x, y desde una geometría Point.
    """
    if geom is None or geom.is_empty:
        raise ValueError("Geometría vacía")

    if geom.geom_type != "Point":
        c = geom.centroid
        return float(c.x), float(c.y)

    return float(geom.x), float(geom.y)


def _to_lat_lon_from_gdf(gdf: gpd.GeoDataFrame, x: float, y: float) -> tuple[float, float]:
    """
    Convierte una coordenada del CRS del GeoDataFrame a lat/lon EPSG:4326.
    """
    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=25830)

    transformer = Transformer.from_crs(gdf.crs, "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(x, y)
    return float(lat), float(lon)


def _lat_lon_to_utm(lat: float, lon: float, epsg: int = 25830) -> tuple[float, float]:
    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    x, y = transformer.transform(lon, lat)
    return float(x), float(y)


def select_weather_points(cfg) -> list[dict[str, Any]]:
    """
    Selecciona puntos meteorológicos para WindNinja con prioridad:

    1. Si existe shapefile de apoyos, usa el primer apoyo.
    2. Si no, usa el centroide del dominio.

    Devuelve una lista de puntos con:
    name, lat, lon, utm_x, utm_y, source.
    """

    # 1) Prioridad: apoyos existentes
    if cfg.out_apoyos_shp is not None and Path(cfg.out_apoyos_shp).exists():
        gdf = gpd.read_file(cfg.out_apoyos_shp)

        if not gdf.empty:
            geom = gdf.geometry.iloc[0]
            x, y = _point_from_geometry(geom)
            lat, lon = _to_lat_lon_from_gdf(gdf, x, y)
            utm_x, utm_y = _lat_lon_to_utm(lat, lon, epsg=cfg.apoyos_epsg_arg or 25830)

            return [
                {
                    "name": "Station1",
                    "lat": lat,
                    "lon": lon,
                    "utm_x": utm_x,
                    "utm_y": utm_y,
                    "source": "apoyos",
                }
            ]

    # 2) Fallback: centroide del dominio
    if cfg.lat is None or cfg.lon is None:
        raise ValueError("No se pudo obtener lat/lon desde apoyos ni desde el dominio.")

    utm_x, utm_y = _lat_lon_to_utm(cfg.lat, cfg.lon, epsg=cfg.apoyos_epsg_arg or 25830)

    return [
        {
            "name": "Station1",
            "lat": cfg.lat,
            "lon": cfg.lon,
            "utm_x": utm_x,
            "utm_y": utm_y,
            "source": "domain_centroid",
        }
    ]