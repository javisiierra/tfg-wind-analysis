from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import shape

from app.services.dashboard.era5_service import Era5Service


class DashboardDataError(Exception):
    def __init__(self, message: str, error_code: str, http_status: int):
        super().__init__(message)
        self.error_code = error_code
        self.http_status = http_status


@dataclass
class WeatherDashboardService:
    start_year: int = 2000
    end_year: int = 2099
    era5_service: Era5Service = field(default_factory=Era5Service)

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

        try:
            df = self.era5_service.fetch_hourly(
                year=year,
                case_path=resolved.get("case_path"),
            )
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

        month_avg = df["WS10M"].groupby(df.index.month).mean()
        dominant_direction = float(df["WD10M"].mode().iloc[0]) if not df["WD10M"].mode().empty else 0.0
        viability_index = float(np.clip(df["WS10M"].mean() / 8.0, 0.0, 1.0))

        return {
            "year": year,
            "avg_velocity": float(df["WS10M"].mean()),
            "max_velocity": float(df["WS10M"].max()),
            "dominant_direction": dominant_direction,
            "windiest_month": int(month_avg.idxmax()),
            "viability_index": viability_index,
            "data_points": int(len(df)),
            **meta,
        }

    def get_wind_timeseries(self, year: int, domain: Any | None = None) -> dict[str, Any]:
        df, _, meta = self._load_year_data(year, domain)
        out: list[dict[str, Any]] = []

        bins = [0, 2, 4, 6, 8, 10, np.inf]
        labels = ["0-2", "2-4", "4-6", "6-8", "8-10", "10+"]

        for month in range(1, 13):
            monthly = df[df.index.month == month]
            if monthly.empty:
                out.append({"month": month, "avg_velocity": 0.0, "max_velocity": 0.0, "min_velocity": 0.0, "frequency": {k: 0.0 for k in labels}})
                continue
            grouped = pd.cut(monthly["WS10M"], bins=bins, labels=labels, right=False)
            freq = grouped.value_counts(normalize=True).reindex(labels, fill_value=0.0)
            out.append({
                "month": month,
                "avg_velocity": float(monthly["WS10M"].mean()),
                "max_velocity": float(monthly["WS10M"].max()),
                "min_velocity": float(monthly["WS10M"].min()),
                "frequency": {k: float(v) for k, v in freq.items()},
            })

        return {"items": out, **meta}

    def get_wind_rose(self, year: int, domain: Any | None = None) -> dict[str, Any]:
        df, _, meta = self._load_year_data(year, domain)
        sectors = [("N", 348.75, 360.0), ("NNE", 11.25, 33.75), ("NE", 33.75, 56.25), ("ENE", 56.25, 78.75), ("E", 78.75, 101.25), ("ESE", 101.25, 123.75), ("SE", 123.75, 146.25), ("SSE", 146.25, 168.75), ("S", 168.75, 191.25), ("SSW", 191.25, 213.75), ("SW", 213.75, 236.25), ("WSW", 236.25, 258.75), ("W", 258.75, 281.25), ("WNW", 281.25, 303.75), ("NW", 303.75, 326.25), ("NNW", 326.25, 348.75)]
        wd = df["WD10M"] % 360
        ws = df["WS10M"]
        rows: list[dict[str, Any]] = []
        for name, start_deg, end_deg in sectors:
            mask = (wd >= 348.75) | (wd < 11.25) if name == "N" else (wd >= start_deg) & (wd < end_deg)
            sector_ws = ws[mask]
            rows.append({"direction": name, "frequency": float(mask.mean()), "velocity_range": {"min": float(sector_ws.min()) if not sector_ws.empty else 0.0, "max": float(sector_ws.max()) if not sector_ws.empty else 0.0}})
        return {"items": rows, **meta}
