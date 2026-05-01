from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import shape

from app.services.dashboard.era5_service import Era5Service


@dataclass
class WeatherDashboardService:
    start_year: int = 2000
    end_year: int = 2099
    era5_service: Era5Service = Era5Service()

    def _validate_year(self, year: int) -> None:
        if not isinstance(year, int) or year < self.start_year or year > self.end_year:
            raise ValueError(f"Year must be a valid year ({self.start_year}-{self.end_year})")

    def _resolve_domain_descriptor(self, domain: Any) -> dict[str, Any]:
        descriptor = domain.model_dump() if hasattr(domain, "model_dump") else dict(domain or {})

        bbox = descriptor.get("bbox")
        if bbox is not None:
            min_lon, min_lat, max_lon, max_lat = map(float, bbox)
            return {
                "lat": (min_lat + max_lat) / 2.0,
                "lon": (min_lon + max_lon) / 2.0,
                "bbox": [min_lon, min_lat, max_lon, max_lat],
                "source": "bbox",
            }

        geometry = descriptor.get("geometry")
        if geometry is not None:
            geom = shape(geometry)
            min_lon, min_lat, max_lon, max_lat = map(float, geom.bounds)
            return {
                "lat": (min_lat + max_lat) / 2.0,
                "lon": (min_lon + max_lon) / 2.0,
                "bbox": [min_lon, min_lat, max_lon, max_lat],
                "source": "geometry",
            }

        case_path = descriptor.get("case_path")
        if case_path:
            base = Path(case_path)
            candidates = [base / "SHP" / "dominio.geojson", base / "SHP" / "dominio.shp"]
            for candidate in candidates:
                if candidate.exists():
                    gdf = gpd.read_file(candidate)
                    if not gdf.empty and gdf.geometry.notna().any():
                        gdf_wgs84 = gdf.to_crs(epsg=4326) if gdf.crs is not None else gdf
                        min_lon, min_lat, max_lon, max_lat = map(float, gdf_wgs84.total_bounds)
                        return {
                            "lat": (min_lat + max_lat) / 2.0,
                            "lon": (min_lon + max_lon) / 2.0,
                            "bbox": [min_lon, min_lat, max_lon, max_lat],
                            "source": f"case_path:{candidate.name}",
                        }

        domain_id = descriptor.get("domain_id")
        if domain_id:
            return {
                "lat": 40.4168,
                "lon": -3.7038,
                "bbox": None,
                "source": f"domain_id:{domain_id}:mock_fallback",
            }

        return {
            "lat": 40.4168,
            "lon": -3.7038,
            "bbox": None,
            "source": "mock_fallback_madrid",
        }

    def _load_year_data(self, year: int, domain: Any | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
        self._validate_year(year)
        resolved = self._resolve_domain_descriptor(domain)
        df = fetch_power_hourly(
            lat=resolved["lat"],
            lon=resolved["lon"],
            start=date(year, 1, 1),
            end=date(year, 12, 31),
        )
        if df.empty:
            raise ValueError(f"No meteorological data available for year {year}")
        return df, resolved

    def get_meteo_summary(self, year: int, domain: Any | None = None) -> dict[str, Any]:
        df, resolved = self._load_year_data(year, domain)

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
            "source": resolved["source"],
            "bbox": resolved["bbox"],
        }

    def get_wind_timeseries(self, year: int, domain: Any | None = None) -> dict[str, Any]:
        df, resolved = self._load_year_data(year, domain)
        out: list[dict[str, Any]] = []

        bins = [0, 2, 4, 6, 8, 10, np.inf]
        labels = ["0-2", "2-4", "4-6", "6-8", "8-10", "10+"]

        for month in range(1, 13):
            monthly = df[df.index.month == month]
            if monthly.empty:
                out.append(
                    {
                        "month": month,
                        "avg_velocity": 0.0,
                        "max_velocity": 0.0,
                        "min_velocity": 0.0,
                        "frequency": {k: 0.0 for k in labels},
                    }
                )
                continue

            grouped = pd.cut(monthly["WS10M"], bins=bins, labels=labels, right=False)
            freq = grouped.value_counts(normalize=True).reindex(labels, fill_value=0.0)
            out.append(
                {
                    "month": month,
                    "avg_velocity": float(monthly["WS10M"].mean()),
                    "max_velocity": float(monthly["WS10M"].max()),
                    "min_velocity": float(monthly["WS10M"].min()),
                    "frequency": {k: float(v) for k, v in freq.items()},
                }
            )

        return {"items": out, "source": resolved["source"], "bbox": resolved["bbox"]}

    def get_wind_rose(self, year: int, domain: Any | None = None) -> dict[str, Any]:
        df, resolved = self._load_year_data(year, domain)

        sectors = [
            ("N", 348.75, 360.0),
            ("NNE", 11.25, 33.75),
            ("NE", 33.75, 56.25),
            ("ENE", 56.25, 78.75),
            ("E", 78.75, 101.25),
            ("ESE", 101.25, 123.75),
            ("SE", 123.75, 146.25),
            ("SSE", 146.25, 168.75),
            ("S", 168.75, 191.25),
            ("SSW", 191.25, 213.75),
            ("SW", 213.75, 236.25),
            ("WSW", 236.25, 258.75),
            ("W", 258.75, 281.25),
            ("WNW", 281.25, 303.75),
            ("NW", 303.75, 326.25),
            ("NNW", 326.25, 348.75),
        ]

        wd = df["WD10M"] % 360
        ws = df["WS10M"]
        rows: list[dict[str, Any]] = []

        for name, start_deg, end_deg in sectors:
            if name == "N":
                mask = (wd >= 348.75) | (wd < 11.25)
            else:
                mask = (wd >= start_deg) & (wd < end_deg)
            sector_ws = ws[mask]
            rows.append(
                {
                    "direction": name,
                    "frequency": float(mask.mean()),
                    "velocity_range": {
                        "min": float(sector_ws.min()) if not sector_ws.empty else 0.0,
                        "max": float(sector_ws.max()) if not sector_ws.empty else 0.0,
                    },
                }
            )

        return {"items": rows, "source": resolved["source"], "bbox": resolved["bbox"]}
