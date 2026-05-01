from __future__ import annotations

import os
import tempfile
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import xarray as xr

from app.services.wind.utils import uv_to_ws_wd

logger = logging.getLogger(__name__)

_MISSING_CREDENTIALS_MESSAGE = (
    "No se encontraron credenciales de Copernicus CDS API. "
    "Configura CDSAPI_URL y CDSAPI_KEY o el archivo ~/.cdsapirc."
)


def _resolve_cds_credentials_source() -> str:
    has_env_credentials = bool(os.getenv("CDSAPI_URL") and os.getenv("CDSAPI_KEY"))
    home_credentials_path = Path.home() / ".cdsapirc"
    backend_credentials_path = Path(__file__).resolve().parents[3] / ".cdsapirc"

    if has_env_credentials:
        logger.info("ERA5 credentials found using method=env")
        return "env"
    if home_credentials_path.exists():
        logger.info("ERA5 credentials found using method=user_home")
        return "user_home"
    if backend_credentials_path.exists():
        logger.info("ERA5 credentials found using method=backend_file")
        os.environ.setdefault("CDSAPI_RC", str(backend_credentials_path))
        return "backend_file"

    logger.error("ERA5 credentials not found using methods=env,user_home,backend_file")
    raise RuntimeError(_MISSING_CREDENTIALS_MESSAGE)


def get_bbox_from_domain(domain_geojson: dict[str, Any]) -> list[float]:
    """Extract `[minLon,minLat,maxLon,maxLat]` bbox from a GeoJSON domain in EPSG:4326.

    Preconditions:
      - `domain_geojson` must be GeoJSON-like and coordinates in WGS84 lon/lat (EPSG:4326).
      - Returned bbox order is `[minLon,minLat,maxLon,maxLat]`.
    """
    if not isinstance(domain_geojson, dict):
        raise ValueError("domain_geojson must be a dictionary")

    coords: list[tuple[float, float]] = []

    def _collect(node: Any) -> None:
        if isinstance(node, (list, tuple)):
            if len(node) >= 2 and all(isinstance(v, (int, float)) for v in node[:2]):
                coords.append((float(node[0]), float(node[1])))
            else:
                for item in node:
                    _collect(item)

    _collect(domain_geojson.get("coordinates", domain_geojson))
    if not coords:
        raise ValueError("Could not extract coordinates from domain_geojson")

    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return [min(lons), min(lats), max(lons), max(lats)]


def download_era5_for_bbox_year(bbox: list[float], year: int) -> str:
    """Download ERA5 hourly u10/v10 for a bbox and year and return NetCDF path.

    Preconditions:
      - bbox order must be `[minLon,minLat,maxLon,maxLat]` in EPSG:4326.
    """
    if len(bbox) != 4:
        raise ValueError("bbox must have 4 elements: [minLon,minLat,maxLon,maxLat]")
    min_lon, min_lat, max_lon, max_lat = bbox

    _resolve_cds_credentials_source()

    try:
        import cdsapi
    except ImportError as exc:
        raise RuntimeError("cdsapi is required to download ERA5 data") from exc

    target = os.path.join(tempfile.gettempdir(), f"era5_{year}_{min_lon}_{min_lat}_{max_lon}_{max_lat}.nc")
    days = [f"{d:02d}" for d in range(1, 32)]
    times = [f"{h:02d}:00" for h in range(24)]

    cdsapi.Client().retrieve(
        "reanalysis-era5-single-levels",
        {
            "product_type": "reanalysis",
            "variable": ["10m_u_component_of_wind", "10m_v_component_of_wind"],
            "year": str(year),
            "month": [f"{m:02d}" for m in range(1, 13)],
            "day": days,
            "time": times,
            "area": [max_lat, min_lon, min_lat, max_lon],
            "format": "netcdf",
        },
        target,
    )
    return target


def analyze_hourly_wind_dataset(dataset_path: str) -> pd.DataFrame:
    """Read ERA5 u10/v10 dataset and return hourly WS10M/WD10M DataFrame indexed in UTC.

    Preconditions:
      - Input dataset must contain `u10`, `v10`, and `time` variables.
      - WS10M is m/s and WD10M is meteorological degrees (0-360).
    """
    ds = xr.open_dataset(dataset_path)
    if "u10" not in ds or "v10" not in ds:
        raise ValueError("Dataset must include u10 and v10 variables")

    u10 = ds["u10"]
    v10 = ds["v10"]
    spatial_dims = [d for d in ("latitude", "longitude") if d in u10.dims]
    if spatial_dims:
        u10 = u10.mean(dim=spatial_dims)
        v10 = v10.mean(dim=spatial_dims)

    ws, wd = uv_to_ws_wd(u10.values, v10.values)
    idx = pd.to_datetime(ds["time"].values, utc=True)
    df = pd.DataFrame({"WS10M": ws, "WD10M": wd}, index=idx)
    df.index.name = "time_utc"
    return df.replace([np.inf, -np.inf], np.nan).dropna().sort_index()


def load_era5_dataset(path: str) -> pd.DataFrame:
    """Load an ERA5 NetCDF file and convert it to hourly wind DataFrame."""
    return analyze_hourly_wind_dataset(path)


def analyze_wind(df: pd.DataFrame) -> dict[str, Any]:
    """Analyze hourly wind series and return canonical metrics for the weather endpoint.

    Returns:
      - mean_wind_speed
      - max_wind_speed
      - dominant_direction
      - monthly_stats
      - best_month
      - viability
    """
    if df.empty:
        raise ValueError("Input DataFrame is empty")

    ws = df["WS10M"]
    wd = df["WD10M"]
    monthly_stats = _build_monthly_stats(df)

    month_avg = ws.groupby(df.index.month).mean()
    dominant_mode = wd.mode()
    return {
        "mean_wind_speed": float(ws.mean()),
        "max_wind_speed": float(ws.max()),
        "dominant_direction": float(dominant_mode.iloc[0]) if not dominant_mode.empty else 0.0,
        "monthly_stats": monthly_stats,
        "best_month": int(month_avg.idxmax()),
        "viability": calculate_viability(float(ws.mean())),
    }


def calculate_monthly_summary(df: pd.DataFrame) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Calculate output dictionaries compatible with MeteoSummary and WindTimeseries.

    Preconditions:
      - DataFrame must have UTC datetime index and `WS10M`, `WD10M` columns.
      - WS10M is m/s and WD10M is meteorological degrees.
    """
    if df.empty:
        raise ValueError("Input DataFrame is empty")

    analysis = analyze_wind(df)
    ws = df["WS10M"]
    year = int(df.index[0].year)
    meteo_summary = {
        "year": year,
        "avg_velocity": analysis["mean_wind_speed"],
        "max_velocity": analysis["max_wind_speed"],
        "dominant_direction": analysis["dominant_direction"],
        "windiest_month": analysis["best_month"],
        "viability_index": analysis["viability"],
        "data_points": int(len(df)),
    }
    return meteo_summary, analysis["monthly_stats"]


def _build_monthly_stats(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Build monthly statistics helper structure."""
    bins = [0, 2, 4, 6, 8, 10, np.inf]
    labels = ["0-2", "2-4", "4-6", "6-8", "8-10", "10+"]
    monthly_stats: list[dict[str, Any]] = []
    for month in range(1, 13):
        monthly = df[df.index.month == month]
        if monthly.empty:
            monthly_stats.append({"month": month, "avg_velocity": 0.0, "max_velocity": 0.0, "min_velocity": 0.0, "frequency": {k: 0.0 for k in labels}})
            continue
        grouped = pd.cut(monthly["WS10M"], bins=bins, labels=labels, right=False)
        freq = grouped.value_counts(normalize=True).reindex(labels, fill_value=0.0)
        monthly_stats.append({
            "month": month,
            "avg_velocity": float(monthly["WS10M"].mean()),
            "max_velocity": float(monthly["WS10M"].max()),
            "min_velocity": float(monthly["WS10M"].min()),
            "frequency": {k: float(v) for k, v in freq.items()},
        })
    return monthly_stats


def calculate_wind_rose(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Calculate wind rose dictionaries compatible with WindRoseData.

    Preconditions:
      - DataFrame must have `WS10M` (m/s) and `WD10M` (meteorological degrees).
    """
    sectors = [
        ("N", 348.75, 11.25), ("NNE", 11.25, 33.75), ("NE", 33.75, 56.25), ("ENE", 56.25, 78.75),
        ("E", 78.75, 101.25), ("ESE", 101.25, 123.75), ("SE", 123.75, 146.25), ("SSE", 146.25, 168.75),
        ("S", 168.75, 191.25), ("SSW", 191.25, 213.75), ("SW", 213.75, 236.25), ("WSW", 236.25, 258.75),
        ("W", 258.75, 281.25), ("WNW", 281.25, 303.75), ("NW", 303.75, 326.25), ("NNW", 326.25, 348.75),
    ]
    wd = df["WD10M"] % 360
    ws = df["WS10M"]
    rows: list[dict[str, Any]] = []
    for name, start_deg, end_deg in sectors:
        mask = ((wd >= start_deg) & (wd < end_deg)) if start_deg < end_deg else ((wd >= start_deg) | (wd < end_deg))
        sector_ws = ws[mask]
        rows.append({
            "direction": name,
            "frequency": float(mask.mean()),
            "velocity_range": {
                "min": float(sector_ws.min()) if not sector_ws.empty else 0.0,
                "max": float(sector_ws.max()) if not sector_ws.empty else 0.0,
            },
        })
    return rows


def calculate_viability(mean_wind_speed: float) -> float:
    """Calculate viability index from mean wind speed in m/s, clamped to [0, 1]."""
    return float(np.clip(mean_wind_speed / 8.0, 0.0, 1.0))


def load_era5_dataset(path: str) -> pd.DataFrame:
    """Compatibility wrapper for ERA5 dataset loading."""
    return analyze_hourly_wind_dataset(path)


def analyze_wind(df: pd.DataFrame) -> dict[str, Any]:
    """Aggregate wind metrics for dashboard endpoints."""
    meteo_summary, timeseries = calculate_monthly_summary(df)
    return {
        "meteo_summary": meteo_summary,
        "timeseries": timeseries,
        "wind_rose": calculate_wind_rose(df),
    }
