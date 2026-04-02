from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from itertools import product
from pathlib import Path
from typing import Optional, Sequence, Union, Tuple

import geopandas as gpd
import pandas as pd


def first_point_xy_station(shp_path: Union[str, Path]) -> Tuple[str, float, float]:
    """
    Devuelve (station_name, x, y) del primer punto (primer registro) de un shapefile .shp de puntos,
    tomando station_name del atributo 'Structure'.

    Parameters
    ----------
    shp_path : str | Path
        Ruta al fichero .shp.

    Returns
    -------
    (station_name, x, y) : (str, float, float)
        station_name: valor del campo 'Structure' en el primer registro.
        x, y: coordenadas del primer punto en el CRS del shapefile.

    Raises
    ------
    FileNotFoundError
        Si el fichero .shp no existe.
    ValueError
        Si el shapefile no contiene registros o la primera geometría es None.
    KeyError
        Si no existe el campo 'Structure' en la tabla de atributos.
    TypeError
        Si la primera geometría no es un Point.
    """
    shp_path = Path(shp_path)
    if not shp_path.exists():
        raise FileNotFoundError(f"No existe el fichero: {shp_path}")

    gdf = gpd.read_file(shp_path)
    if gdf.empty:
        raise ValueError(f"El shapefile no contiene registros: {shp_path}")

    if "Structure" not in gdf.columns:
        raise KeyError(
            f"No existe el campo 'Structure' en el shapefile. Campos disponibles: {list(gdf.columns)}"
        )

    station_name = gdf["Structure"].iloc[0]
    if station_name is None or (isinstance(station_name, float) and station_name != station_name):
        raise ValueError("El campo 'Structure' del primer registro está vacío/NaN.")

    geom0 = gdf.geometry.iloc[0]
    if geom0 is None:
        raise ValueError("La primera geometría es None (vacía).")
    if geom0.geom_type != "Point":
        raise TypeError(f"La primera geometría no es Point, es: {geom0.geom_type}")

    return str(station_name), float(geom0.x), float(geom0.y)


COLUMNS = [
    "Station_Name",
    "Coord_Sys(PROJCS,GEOGCS)",
    "Datum(WGS84,NAD83,NAD27)",
    "Lat/YCoord",
    "Lon/XCoord",
    "Height",
    "Height_Units(meters,feet)",
    "Speed",
    "Speed_Units(mph,kph,mps,kts)",
    "Direction(degrees)",
    "Temperature",
    "Temperature_Units(F,C)",
    "Cloud_Cover(%)",
    "Radius_of_Influence",
    "Radius_of_Influence_Units(miles,feet,meters,km)",
    "date_time",
]


def _parse_utc(dt_str: str) -> datetime:
    """
    Acepta 'YYYY-MM-DDTHH:MM:SSZ' (como el adjunto) o ISO sin Z.
    Devuelve datetime timezone-aware en UTC.
    """
    s = dt_str.strip()
    if s.endswith("Z"):
        s = s[:-1]
        dt = datetime.fromisoformat(s)
        return dt.replace(tzinfo=timezone.utc)
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


def _format_utc_z(dt: datetime) -> str:
    dt_utc = dt.astimezone(timezone.utc)
    return dt_utc.replace(tzinfo=None).isoformat(timespec="seconds") + "Z"


def directions_evenly_spaced(n_directions: int, *, start_deg: float = 0.0) -> list[float]:
    """
    Genera n_directions direcciones equiespaciadas en [0, 360).
    Ej.: n=16 -> 0, 22.5, 45, ..., 337.5
    """
    if n_directions <= 0:
        raise ValueError("n_directions debe ser > 0")
    step = 360.0 / n_directions
    return [round((start_deg + k * step) % 360.0, 6) for k in range(n_directions)]


@dataclass
class WindNinjaDefaults:
    datum: str = "WGS84"
    ycoord: Union[int, float] = 0
    xcoord: Union[int, float] = 0
    height_units: str = "meters"
    speed_units: str = "mps"
    temp_units: str = "C"
    cloud_cover_pct: Union[int, float] = 5
    radius_of_influence: Union[int, float] = -1
    roi_units: str = "km"


def generate_windninja_input_csv(
    *,
    cfg,
    station_name: str = "Station1",
    projection: str = "PROJCS",
    datum: str = "WGS84",
    utm_x: Union[float, int],
    utm_y: Union[float, int],
    height: Union[int, float],
    temperature: Union[int, float],
    n_directions: int,
    wind_speeds: Sequence[Union[int, float]],
    output_csv: Union[str, Path],
    template_csv: Optional[Union[str, Path]] = None,
    start_datetime_utc: str = "2025-01-01T00:00:00Z",
    dt_minutes: int = 15,
    direction_start_deg: float = 0.0,
    ordering: str = "dir_then_speed",
    defaults: Optional[WindNinjaDefaults] = None,
) -> pd.DataFrame:
    """
    Genera un CSV de entrada para WindNinja con todas las combinaciones:
      n_directions * len(wind_speeds) filas.

    Si template_csv se proporciona, se toman valores por defecto de su primera fila
    para los campos no definidos explícitamente.
    """
    if defaults is None:
        defaults = WindNinjaDefaults()

    output_csv = Path(output_csv)
    if not wind_speeds:
        raise ValueError("wind_speeds no puede estar vacío")
    if dt_minutes <= 0:
        raise ValueError("dt_minutes debe ser > 0")

    # Cargar plantilla si existe y extraer valores base
    base = {
        "Datum(WGS84,NAD83,NAD27)": defaults.datum,
        "Lat/YCoord": defaults.ycoord,
        "Lon/XCoord": defaults.xcoord,
        "Height_Units(meters,feet)": defaults.height_units,
        "Speed_Units(mph,kph,mps,kts)": defaults.speed_units,
        "Temperature_Units(F,C)": defaults.temp_units,
        "Cloud_Cover(%)": defaults.cloud_cover_pct,
        "Radius_of_Influence": defaults.radius_of_influence,
        "Radius_of_Influence_Units(miles,feet,meters,km)": defaults.roi_units,
    }

    if template_csv is not None:
        tpl = pd.read_csv(Path(template_csv))
        if tpl.empty:
            raise ValueError("template_csv está vacío")
        row0 = tpl.iloc[0].to_dict()
        # Solo “rellenamos” base con valores existentes en plantilla
        for k in base.keys():
            if k in row0 and pd.notna(row0[k]):
                base[k] = row0[k]

    # Direcciones
    dirs = directions_evenly_spaced(n_directions, start_deg=direction_start_deg)

    # Producto cartesiano (orden configurable)
    if ordering not in {"dir_then_speed", "speed_then_dir"}:
        raise ValueError("ordering debe ser 'dir_then_speed' o 'speed_then_dir'")

    if ordering == "dir_then_speed":
        cases = list(product(dirs, wind_speeds))
    else:
        cases = [(d, s) for s, d in product(wind_speeds, dirs)]

    # Tiempos
    t0 = _parse_utc(start_datetime_utc)
    dt = timedelta(minutes=dt_minutes)

    rows = []
    for i, (d, s) in enumerate(cases):
        rows.append({
            "Station_Name": station_name,
            "Coord_Sys(PROJCS,GEOGCS)": projection,
            "Datum(WGS84,NAD83,NAD27)": base["Datum(WGS84,NAD83,NAD27)"],
            "Lat/YCoord": utm_x,
            "Lon/XCoord": utm_y,
            "Height": height,
            "Height_Units(meters,feet)": base["Height_Units(meters,feet)"],
            "Speed": float(s),
            "Speed_Units(mph,kph,mps,kts)": base["Speed_Units(mph,kph,mps,kts)"],
            "Direction(degrees)": float(d),
            "Temperature": float(temperature),
            "Temperature_Units(F,C)": base["Temperature_Units(F,C)"],
            "Cloud_Cover(%)": base["Cloud_Cover(%)"],
            "Radius_of_Influence": base["Radius_of_Influence"],
            "Radius_of_Influence_Units(miles,feet,meters,km)": base["Radius_of_Influence_Units(miles,feet,meters,km)"],
            "date_time": _format_utc_z(t0 + i * dt),
        })

    out = pd.DataFrame(rows, columns=COLUMNS)
    output_csv = cfg.out_weather_point_file
    out.to_csv(output_csv, index=False)
    return out