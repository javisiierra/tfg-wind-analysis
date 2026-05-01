from __future__ import annotations

import os
import tempfile
import logging
from pathlib import Path
from threading import Event, Thread
from typing import Any, Callable

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

def _expand_bbox_for_era5_grid(bbox: list[float], min_size_deg: float = 0.75) -> list[float]:
    min_lon, min_lat, max_lon, max_lat = map(float, bbox)

    if min_lon >= max_lon or min_lat >= max_lat:
        raise ValueError("Invalid bbox: expected [minLon,minLat,maxLon,maxLat] with min < max")

    center_lon = (min_lon + max_lon) / 2.0
    center_lat = (min_lat + max_lat) / 2.0

    width = max_lon - min_lon
    height = max_lat - min_lat

    target_width = max(width, min_size_deg)
    target_height = max(height, min_size_deg)

    expanded = [
        center_lon - target_width / 2.0,
        center_lat - target_height / 2.0,
        center_lon + target_width / 2.0,
        center_lat + target_height / 2.0,
    ]

    return [
        max(-180.0, expanded[0]),
        max(-90.0, expanded[1]),
        min(180.0, expanded[2]),
        min(90.0, expanded[3]),
    ]


def era5_cache_target_path(bbox: list[float], year: int) -> str:
    min_lon, min_lat, max_lon, max_lat = bbox
    return os.path.join(
        tempfile.gettempdir(),
        f"era5_{year}_{min_lon}_{min_lat}_{max_lon}_{max_lat}.nc",
    )


def download_era5_for_bbox_year(
    bbox: list[float],
    year: int,
    progress_cb: Callable[[int, str], None] | None = None,
) -> str:
    if len(bbox) != 4:
        raise ValueError("bbox must have 4 elements: [minLon,minLat,maxLon,maxLat]")

    bbox = _expand_bbox_for_era5_grid(bbox)
    min_lon, min_lat, max_lon, max_lat = bbox

    _resolve_cds_credentials_source()

    try:
        import cdsapi
    except ImportError as exc:
        raise RuntimeError("cdsapi is required to download ERA5 data") from exc

    target = era5_cache_target_path(bbox, year)

    if os.path.exists(target):
        logger.info(
            "Using cached ERA5 dataset",
            extra={"target": target, "year": year, "bbox": bbox},
        )
        if progress_cb:
            progress_cb(80, "Usando ERA5 cacheado...")
        return target

    days = [f"{d:02d}" for d in range(1, 32)]
    times = [f"{h:02d}:00" for h in range(24)]
    stop_progress = Event()

    def _estimated_progress_worker() -> None:
        stages = [
            (45, "Solicitud ERA5 aceptada por Copernicus..."),
            (55, "Copernicus está procesando los datos..."),
            (65, "Descargando archivo ERA5..."),
            (75, "Finalizando descarga ERA5..."),
        ]

        for progress, message in stages:
            if stop_progress.wait(10):
                return
            if progress_cb:
                progress_cb(progress, message)

        while not stop_progress.wait(10):
            if progress_cb:
                progress_cb(80, "Finalizando descarga ERA5...")

    worker: Thread | None = None

    if progress_cb:
        worker = Thread(target=_estimated_progress_worker, daemon=True)
        worker.start()

    try:
        cdsapi.Client().retrieve(
            "reanalysis-era5-single-levels",
            {
                "product_type": "reanalysis",
                "variable": [
                    "10m_u_component_of_wind",
                    "10m_v_component_of_wind",
                ],
                "year": str(year),
                "month": [f"{m:02d}" for m in range(1, 13)],
                "day": days,
                "time": times,
                "area": [max_lat, min_lon, min_lat, max_lon],
                "data_format": "netcdf",
            },
            target,
        )
    finally:
        stop_progress.set()
        if worker is not None:
            worker.join(timeout=1)

    return target


def _detect_time_name(ds: xr.Dataset) -> str:
    for candidate in ("time", "valid_time", "forecast_reference_time"):
        if candidate in ds.coords or candidate in ds.variables or candidate in ds.dims:
            return candidate

    raise ValueError(
        "No se encontró variable temporal en ERA5. "
        f"Coords disponibles: {list(ds.coords)}. "
        f"Variables disponibles: {list(ds.variables)}. "
        f"Dims disponibles: {list(ds.dims)}."
    )


def analyze_hourly_wind_dataset(dataset_path: str) -> pd.DataFrame:
    ds = xr.open_dataset(dataset_path)

    try:
        if "u10" not in ds or "v10" not in ds:
            raise ValueError(
                f"Dataset must include u10 and v10 variables. Available variables: {list(ds.variables)}"
            )

        u10 = ds["u10"]
        v10 = ds["v10"]

        spatial_dims = [d for d in ("latitude", "longitude") if d in u10.dims]

        if spatial_dims:
            u10 = u10.mean(dim=spatial_dims)
            v10 = v10.mean(dim=spatial_dims)

        time_name = _detect_time_name(ds)

        time_values = pd.to_datetime(ds[time_name].values, utc=True)

        ws, wd = uv_to_ws_wd(u10.values, v10.values)

        ws = np.asarray(ws).ravel()
        wd = np.asarray(wd).ravel()
        time_values = pd.DatetimeIndex(np.asarray(time_values).ravel())

        min_len = min(len(time_values), len(ws), len(wd))

        df = pd.DataFrame(
            {
                "WS10M": ws[:min_len],
                "WD10M": wd[:min_len],
            },
            index=pd.DatetimeIndex(time_values[:min_len]),
        )

        df.index.name = "time_utc"

        return (
            df.replace([np.inf, -np.inf], np.nan)
            .dropna()
            .sort_index()
        )

    finally:
        ds.close()


def load_era5_dataset(path: str) -> pd.DataFrame:
    return analyze_hourly_wind_dataset(path)


def analyze_wind(df: pd.DataFrame) -> dict[str, Any]:
    if df is None or df.empty:
        raise ValueError("Input DataFrame is empty")

    if "WS10M" not in df.columns or "WD10M" not in df.columns:
        raise ValueError(f"Missing WS10M/WD10M columns. Available columns: {list(df.columns)}")

    ws = df["WS10M"]
    wd = df["WD10M"]

    monthly_stats = _build_monthly_stats(df)

    month_avg = ws.groupby(df.index.month).mean()
    dominant_direction = _calculate_dominant_direction(wd)

    return {
        "mean_wind_speed": float(ws.mean()),
        "max_wind_speed": float(ws.max()),
        "dominant_direction": float(dominant_direction),
        "monthly_stats": monthly_stats,
        "best_month": int(month_avg.idxmax()),
        "viability": calculate_viability(float(ws.mean())),
    }


def calculate_monthly_summary(df: pd.DataFrame) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if df is None or df.empty:
        raise ValueError("Input DataFrame is empty")

    analysis = analyze_wind(df)

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


def analyze_wind_for_dashboard(df: pd.DataFrame) -> dict[str, Any]:
    meteo_summary, timeseries = calculate_monthly_summary(df)

    return {
        "meteo_summary": meteo_summary,
        "wind_timeseries": timeseries,
        "wind_rose": calculate_wind_rose(df),
    }


def _build_monthly_stats(df: pd.DataFrame) -> list[dict[str, Any]]:
    bins = [0, 2, 4, 6, 8, 10, np.inf]
    labels = ["0-2", "2-4", "4-6", "6-8", "8-10", "10+"]

    monthly_stats: list[dict[str, Any]] = []

    for month in range(1, 13):
        monthly = df[df.index.month == month]

        if monthly.empty:
            monthly_stats.append(
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

        monthly_stats.append(
            {
                "month": month,
                "avg_velocity": float(monthly["WS10M"].mean()),
                "max_velocity": float(monthly["WS10M"].max()),
                "min_velocity": float(monthly["WS10M"].min()),
                "frequency": {str(k): float(v) for k, v in freq.items()},
            }
        )

    return monthly_stats


def calculate_wind_rose(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []

    sectors = [
        ("N", 348.75, 11.25),
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
        if start_deg < end_deg:
            mask = (wd >= start_deg) & (wd < end_deg)
        else:
            mask = (wd >= start_deg) | (wd < end_deg)

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

    return rows


def _calculate_dominant_direction(wd: pd.Series) -> float:
    if wd.empty:
        return 0.0

    sectors = np.arange(0, 361, 22.5)
    binned = pd.cut(wd % 360, bins=sectors, include_lowest=True)

    mode = binned.value_counts().idxmax()

    if pd.isna(mode):
        return 0.0

    return float((mode.left + mode.right) / 2.0)


def calculate_viability(mean_wind_speed: float) -> float:
    return float(np.clip(mean_wind_speed / 8.0, 0.0, 1.0))