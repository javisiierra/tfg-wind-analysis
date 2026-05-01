from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import geopandas as gpd
import pandas as pd
from shapely.geometry import shape

from app.services.weather.era5_service import analyze_wind, download_era5_for_bbox_year, load_era5_dataset


class DashboardDataError(Exception):
    def __init__(self, message: str, error_code: str, http_status: int):
        super().__init__(message)
        self.error_code = error_code
        self.http_status = http_status


@dataclass
class WeatherDashboardService:
    start_year: int = 2000
    end_year: int = 2099

    def _validate_year(self, year: int) -> None:
        if not isinstance(year, int) or year < self.start_year or year > self.end_year:
            raise DashboardDataError(
                f"Year must be a valid year ({self.start_year}-{self.end_year})",
                error_code="INVALID_YEAR",
                http_status=422,
            )

    def _resolve_domain_descriptor(self, domain: Any) -> dict[str, Any]:
        descriptor = domain.model_dump() if hasattr(domain, "model_dump") else dict(domain or {})

        bbox = descriptor.get("bbox")
        if bbox is not None:
            min_lon, min_lat, max_lon, max_lat = map(float, bbox)
            if min_lon >= max_lon or min_lat >= max_lat:
                raise DashboardDataError("Invalid bbox: expected min < max", "INVALID_BBOX", 422)
            return {
                "lat": (min_lat + max_lat) / 2.0,
                "lon": (min_lon + max_lon) / 2.0,
                "bbox": [min_lon, min_lat, max_lon, max_lat],
                "source": "bbox",
                "crs": "EPSG:4326",

            }

        geometry = descriptor.get("geometry")
        if geometry is not None:
            try:
                geom = shape(geometry)
            except Exception as exc:
                raise DashboardDataError("Invalid geometry payload", "INVALID_GEOJSON", 422) from exc
            min_lon, min_lat, max_lon, max_lat = map(float, geom.bounds)
            return {
                "lat": (min_lat + max_lat) / 2.0,
                "lon": (min_lon + max_lon) / 2.0,
                "bbox": [min_lon, min_lat, max_lon, max_lat],
                "source": "geometry",
                "crs": "EPSG:4326",

            }

        case_path = descriptor.get("case_path")
        if case_path:
            base = Path(case_path)
            candidates = [base / "SHP" / "dominio.geojson", base / "SHP" / "dominio.shp"]
            for candidate in candidates:
                if candidate.exists():
                    try:
                        gdf = gpd.read_file(candidate)
                    except Exception as exc:
                        raise DashboardDataError(
                            f"Could not read domain file: {candidate.name}",
                            "INVALID_CASE_DOMAIN",
                            422,
                        ) from exc
                    if not gdf.empty and gdf.geometry.notna().any():
                        gdf_wgs84 = gdf.to_crs(epsg=4326) if gdf.crs is not None else gdf
                        min_lon, min_lat, max_lon, max_lat = map(float, gdf_wgs84.total_bounds)
                        return {
                            "lat": (min_lat + max_lat) / 2.0,
                            "lon": (min_lon + max_lon) / 2.0,
                            "bbox": [min_lon, min_lat, max_lon, max_lat],
                            "source": f"case_path:{candidate.name}",
                            "crs": "EPSG:4326",
                            "case_path": str(base),

                        }
            raise DashboardDataError(
                "Domain file not found or empty in case_path (expected SHP/dominio.geojson or SHP/dominio.shp)",
                "INVALID_CASE_DOMAIN",
                422,
            )

        raise DashboardDataError(
            "Provide one valid domain source (bbox, geometry, or case_path)",
            "MISSING_DOMAIN",
            422,
        )

    def _load_year_data(self, year: int, domain: Any | None = None) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
        self._validate_year(year)
        resolved = self._resolve_domain_descriptor(domain)
        time_range = {"start": f"{year}-01-01", "end": f"{year}-12-31"}
        meta = {
            "source": "era5",
            "request_id": str(uuid4()),
            "domain_bbox": resolved["bbox"],
            "time_range": time_range,
            "crs": resolved.get("crs", "EPSG:4326"),
            "status": "ok",
        }

        bbox = resolved["bbox"]
        try:
            dataset_path = download_era5_for_bbox_year(bbox, year)
            df = load_era5_dataset(dataset_path)
        except Exception as exc:
            detail = str(exc)
            lowered = detail.lower()
            if "dominio.geojson" in lowered or "dominio.shp" in lowered or "dominio válido" in lowered:
                raise DashboardDataError(
                    "Domain file not found or invalid in case_path (expected SHP/dominio.geojson or SHP/dominio.shp)",
                    "INVALID_CASE_DOMAIN",
                    422,
                ) from exc
            if ".cdsapirc" in lowered or "missing/incomplete configuration file" in lowered:
                raise DashboardDataError(
                    "CDS credentials not found (~/.cdsapirc)",
                    "CDS_CREDENTIALS_MISSING",
                    503,
                ) from exc
            if "cdsapi" in lowered and "instala" in lowered:
                raise DashboardDataError(
                    "CDS client dependency missing (install cdsapi)",
                    "CDS_CLIENT_MISSING",
                    500,
                ) from exc
            raise DashboardDataError(
                "ERA5 fetch failed (network timeout or upstream error)",
                "ERA5_UPSTREAM_ERROR",
                502,
            ) from exc

        if df.empty:
            raise DashboardDataError(
                f"No meteorological data available for year {year}",
                "NO_DATA",
                404,
            )
        return df, resolved, meta

    def get_meteo_summary(self, year: int, domain: Any | None = None) -> dict[str, Any]:
        df, _, meta = self._load_year_data(year, domain)
        metrics = analyze_wind(df)
        summary = metrics["meteo_summary"]

        return {
            **summary,
            **meta,
        }

    def get_wind_timeseries(self, year: int, domain: Any | None = None) -> dict[str, Any]:
        df, _, meta = self._load_year_data(year, domain)
        metrics = analyze_wind(df)
        return {"items": metrics["timeseries"], **meta}

    def get_wind_rose(self, year: int, domain: Any | None = None) -> dict[str, Any]:
        df, _, meta = self._load_year_data(year, domain)
        metrics = analyze_wind(df)
        return {"items": metrics["wind_rose"], **meta}
