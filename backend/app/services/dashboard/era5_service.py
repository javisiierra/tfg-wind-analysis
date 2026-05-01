from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import geopandas as gpd
import pandas as pd

from app.core.config import load_config_from_case
from app.services.wind.source_service import fetch_era5_hourly_point


class Era5Service:

    def _resolve_point(self, case_path: str | None) -> tuple[float, float]:
        if case_path:
            case_root = Path(case_path)
            domain_candidates = [case_root / "SHP" / "dominio.geojson", case_root / "SHP" / "dominio.shp"]
            for domain_path in domain_candidates:
                if not domain_path.exists():
                    continue
                gdf = gpd.read_file(domain_path)
                if gdf.empty or not gdf.geometry.notna().any():
                    continue
                gdf_wgs84 = gdf.to_crs(epsg=4326) if gdf.crs is not None else gdf
                centroid = gdf_wgs84.unary_union.centroid
                return float(centroid.y), float(centroid.x)

            cfg = load_config_from_case(case_root)
            if cfg.lat is not None and cfg.lon is not None:
                return float(cfg.lat), float(cfg.lon)

            raise FileNotFoundError(
                "No se encontró un dominio válido en el caso (SHP/dominio.geojson o SHP/dominio.shp) "
                "ni coordenadas lat/lon en la configuración."
            )
        raise ValueError("case_path es obligatorio para resolver el dominio del análisis meteorológico")

    def fetch_hourly(self, year: int, case_path: str | None = None) -> pd.DataFrame:
        lat, lon = self._resolve_point(case_path)
        start = date(year, 1, 1)
        end = date(year, 12, 31)
        return fetch_era5_hourly_point(lat=lat, lon=lon, start=start, end=end)
