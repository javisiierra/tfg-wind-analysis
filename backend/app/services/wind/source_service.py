from __future__ import annotations

import argparse
import math
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
import xarray as xr
from pyproj import CRS, Transformer


# -----------------------
# Utilidades de coordenadas
# -----------------------

@dataclass(frozen=True)
class PointLL:
    lat: float
    lon: float


def utm_to_latlon(
    x: float,
    y: float,
    epsg: Optional[int] = None,
    zone: Optional[int] = None,
    hemisphere: Optional[str] = None,
) -> PointLL:
    """
    Convierte UTM (x,y) a lat/lon.

    Opción A (recomendada): pasar EPSG (p.ej. 25830 ETRS89 / UTM 30N, 32630 WGS84 / UTM 30N).
    Opción B: pasar zone y hemisphere ('N' o 'S') asumiendo WGS84 UTM (EPSG:326xx/327xx).
    """
    if epsg is None:
        if zone is None or hemisphere is None:
            raise ValueError("Para UTM debes indicar --epsg o bien (--utm-zone y --utm-hemisphere).")
        hem = hemisphere.upper()
        if hem not in ("N", "S"):
            raise ValueError("--utm-hemisphere debe ser 'N' o 'S'.")
        epsg = (32600 + zone) if hem == "N" else (32700 + zone)

    src = CRS.from_epsg(int(epsg))
    dst = CRS.from_epsg(4326)  # WGS84 lat/lon
    tr = Transformer.from_crs(src, dst, always_xy=True)
    lon, lat = tr.transform(x, y)
    return PointLL(lat=float(lat), lon=float(lon))


def resolve_point(args: argparse.Namespace) -> PointLL:
    if args.lat is not None and args.lon is not None:
        return PointLL(lat=float(args.lat), lon=float(args.lon))

    if args.utm_x is not None and args.utm_y is not None:
        return utm_to_latlon(
            x=float(args.utm_x),
            y=float(args.utm_y),
            epsg=args.epsg,
            zone=args.utm_zone,
            hemisphere=args.utm_hemisphere,
        )

    raise ValueError(
        "Debes indicar (--lat --lon) o bien (--utm-x --utm-y y --epsg/--utm-zone/--utm-hemisphere)."
    )


# -----------------------
# NASA POWER (horario)
# -----------------------

def fetch_power_hourly(lat: float, lon: float, start: date, end: date) -> pd.DataFrame:
    """
    Descarga WS10M y WD10M (horario) desde NASA POWER para un punto.
    """
    url = (
        "https://power.larc.nasa.gov/api/temporal/hourly/point"
        f"?parameters=WS10M,WD10M"
        f"&community=SB"
        f"&longitude={lon}&latitude={lat}"
        f"&start={start.strftime('%Y%m%d')}&end={end.strftime('%Y%m%d')}"
        f"&format=JSON&time-standard=UTC"
    )
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    js = r.json()
    params = js["properties"]["parameter"]

    df = pd.DataFrame(
        {
            "WS10M": pd.Series(params["WS10M"]),
            "WD10M": pd.Series(params["WD10M"]),
        }
    )
    df.index = pd.to_datetime(df.index, format="%Y%m%d%H")
    df.index.name = "time_utc"
    df = df.replace(-999, np.nan).dropna()
    return df


# -----------------------
# ERA5 (CDS API): U10/V10 -> WS/WD
# -----------------------

def uv_to_ws_wd(u: np.ndarray, v: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Convierte componentes (u,v) a:
      - WS = sqrt(u^2 + v^2)
      - WD meteorológica (dirección "de procedencia"): atan2(-u, -v)
    """
    ws = np.sqrt(u * u + v * v)
    wd = (np.degrees(np.arctan2(-u, -v)) + 360.0) % 360.0
    return ws, wd


def month_range(start: date, end: date) -> List[Tuple[int, int]]:
    months = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        months.append((y, m))
        m += 1
        if m == 13:
            m = 1
            y += 1
    return months


def fetch_era5_hourly_point(lat: float, lon: float, start: date, end: date) -> pd.DataFrame:
    """
    Descarga ERA5 horario (u10, v10) para una pequeña caja alrededor del punto y
    luego interpola bilinealmente al (lat,lon).
    Requiere configurar CDS API (~/.cdsapirc) y tener permisos.
    """
    try:
        import cdsapi
    except ImportError as e:
        raise ImportError("Instala cdsapi: pip install cdsapi") from e

    c = cdsapi.Client()

    # Caja pequeña para interpolación (0.25º suele coincidir con grid ERA5)
    d = 0.125
    area = [lat + d, lon - d, lat - d, lon + d]  # N, W, S, E

    frames = []
    with tempfile.TemporaryDirectory() as td:
        for (yy, mm) in month_range(start, end):
            target = os.path.join(td, f"era5_u10v10_{yy:04d}{mm:02d}.nc")

            days_in_month = pd.Period(f"{yy:04d}-{mm:02d}").days_in_month
            days = [f"{d:02d}" for d in range(1, days_in_month + 1)]
            times = [f"{h:02d}:00" for h in range(0, 24)]

            c.retrieve(
                "reanalysis-era5-single-levels",
                {
                    "product_type": "reanalysis",
                    "variable": ["10m_u_component_of_wind", "10m_v_component_of_wind"],
                    "year": f"{yy:04d}",
                    "month": f"{mm:02d}",
                    "day": days,
                    "time": times,
                    "area": area,
                    "format": "netcdf",
                },
                target,
            )

            ds = xr.open_dataset(target)

            # Interpolación bilineal al punto (lat, lon)
            # Nota: en ERA5 suele ser coords: latitude, longitude.
            dsi = ds.interp(latitude=lat, longitude=lon)

            u10 = dsi["u10"].values
            v10 = dsi["v10"].values
            ws, wd = uv_to_ws_wd(u10, v10)

            t = pd.to_datetime(dsi["time"].values)
            df = pd.DataFrame({"WS10M": ws, "WD10M": wd}, index=t)
            df.index.name = "time_utc"
            frames.append(df)

        out = pd.concat(frames).sort_index()
        out = out.loc[(out.index.date >= start) & (out.index.date <= end)]
        out = out.replace([np.inf, -np.inf], np.nan).dropna()
        return out


# -----------------------
# AEMET OpenData (diario): inventario + estación más cercana + serie diaria
# -----------------------

AEMET_BASE = "https://opendata.aemet.es/opendata/api"


def aemet_get_hateoas(path: str, api_key: str) -> object:
    """
    Llama a un endpoint AEMET OpenData (HATEOAS) y luego descarga el recurso indicado en el campo 'datos'.
    """
    url = f"{AEMET_BASE}{path}"
    r = requests.get(url, params={"api_key": api_key}, timeout=120)
    r.raise_for_status()
    js = r.json()
    datos_url = js.get("datos")
    if not datos_url:
        raise RuntimeError(f"Respuesta AEMET sin campo 'datos'. Respuesta: {js}")
    r2 = requests.get(datos_url, timeout=120)
    r2.raise_for_status()
    return r2.json()


def parse_aemet_coord(coord: object) -> float:
    """
    Convierte coordenadas AEMET (frecuentes en formato DDMMSS[N/S] / DDDMMSS[E/W]) a grados decimales.
    También acepta floats/strings decimales.
    """
    if coord is None:
        raise ValueError("Coordenada vacía.")
    if isinstance(coord, (int, float)):
        return float(coord)

    s = str(coord).strip()
    s = s.replace(",", ".")

    m = re.fullmatch(r"(\d{6,7})([NSEW])", s.upper())
    if m:
        digits, hemi = m.group(1), m.group(2)
        if len(digits) == 6:  # lat: DDMMSS
            dd = int(digits[0:2])
            mm = int(digits[2:4])
            ss = int(digits[4:6])
        else:  # lon: DDDMMSS
            dd = int(digits[0:3])
            mm = int(digits[3:5])
            ss = int(digits[5:7])
        val = dd + mm / 60.0 + ss / 3600.0
        if hemi in ("S", "W"):
            val = -val
        return float(val)

    return float(s)


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def aemet_find_nearest_station(lat: float, lon: float, api_key: str) -> Tuple[str, float]:
    """
    Usa el inventario de estaciones climatológicas y devuelve:
      - indicativo/idema de la estación más cercana
      - distancia (km)
    """
    inv = aemet_get_hateoas("/valores/climatologicos/inventarioestaciones/todasestaciones/", api_key)

    best_id = None
    best_d = float("inf")

    for st in inv:
        try:
            st_lat = parse_aemet_coord(st.get("latitud"))
            st_lon = parse_aemet_coord(st.get("longitud"))
            d = haversine_km(lat, lon, st_lat, st_lon)
            if d < best_d:
                best_d = d
                best_id = st.get("indicativo") or st.get("idema") or st.get("id")
        except Exception:
            continue

    if not best_id:
        raise RuntimeError("No se pudo determinar una estación AEMET cercana a partir del inventario.")
    return str(best_id), float(best_d)


def aemet_format_utc(dt: date) -> str:
    # Formato que aparece en ejemplos oficiales: YYYY-MM-DDTHH:MM:SSUTC
    return f"{dt.isoformat()}T00:00:00UTC"


def fetch_aemet_daily_station(
    lat: float,
    lon: float,
    start: date,
    end: date,
    api_key: str,
    dir_scale: str = "auto",
) -> pd.DataFrame:
    """
    Descarga valores climatológicos diarios para la estación climatológica más cercana.

    Campos de interés esperables:
      - 'velmedia' (velocidad media)
      - 'dir' (dirección)
    Se devuelven como strings con coma decimal con frecuencia.

    dir_scale:
      - 'auto': si max(dir)<=36, multiplica por 10; si no, deja igual.
      - '1' o '10': fuerza escala.
    """
    station, dist_km = aemet_find_nearest_station(lat, lon, api_key)
    path = (
        f"/valores/climatologicos/diarios/datos/fechaini/{aemet_format_utc(start)}"
        f"/fechafin/{aemet_format_utc(end)}/estacion/{station}"
    )
    data = aemet_get_hateoas(path, api_key)

    df = pd.DataFrame(data)

    def to_float(series: pd.Series) -> pd.Series:
        return pd.to_numeric(series.astype(str).str.replace(",", ".", regex=False), errors="coerce")

    ws = to_float(df.get("velmedia", pd.Series(dtype=str)))
    wd = to_float(df.get("dir", pd.Series(dtype=str)))

    wd_clean = wd.dropna()
    scale = 1.0
    if dir_scale == "auto":
        if not wd_clean.empty and wd_clean.max() <= 36.0:
            scale = 10.0
    else:
        scale = float(dir_scale)

    wd = wd * scale

    out = pd.DataFrame({"WS10M": ws, "WD10M": wd})
    out.index = pd.to_datetime(df["fecha"], errors="coerce")
    out.index.name = "date"
    out = out.dropna()

    out.attrs["aemet_station"] = station
    out.attrs["aemet_station_distance_km"] = dist_km
    return out


# -----------------------
# Helpers auxiliares
# -----------------------

def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def parse_date_str(s: str):
    """
    parse_date_str.

    Notes
    -----
    Auto-generated docstring. Please refine parameter/return descriptions if needed.
    """
    return datetime.strptime(s, "%Y-%m-%d").date()


def parse_bins(bins_list):
    """
    parse_bins.

    Notes
    -----
    Auto-generated docstring. Please refine parameter/return descriptions if needed.
    """
    bins = []
    for x in bins_list:
        if isinstance(x, str) and x.strip().lower() == "inf":
            bins.append(np.inf)
        else:
            bins.append(float(x))
    return bins


def resolve_point_from_cfg(cfg: dict):
    """
    resolve_point_from_cfg.

    Notes
    -----
    Auto-generated docstring. Please refine parameter/return descriptions if needed.
    """
    loc = cfg.get("location", {})
    lat = loc.get("lat", None)
    lon = loc.get("lon", None)
    utm_x = loc.get("utm_x", None)
    utm_y = loc.get("utm_y", None)
    epsg = loc.get("epsg", 25830)  # por defecto ETRS89/UTM30N

    # Prioridad: si vienen utm_x/utm_y, usar UTM
    if utm_x is not None and utm_y is not None:
        pt = utm_to_latlon(float(utm_x), float(utm_y), epsg=int(epsg))
        return pt

    # Si no, usar lat/lon
    if lat is not None and lon is not None:
        return PointLL(lat=float(lat), lon=float(lon))

    raise ValueError("Config inválida: define (lat,lon) o bien (utm_x,utm_y[,epsg]).")