from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from pyproj import CRS
from shapely.geometry import LineString


def list_windninja_pairs(folder: str | Path):
    folder = Path(folder)
    if not folder.exists():
        raise FileNotFoundError(f"No existe la carpeta OUT_WN_REN: {folder}")

    files = [p for p in folder.iterdir() if p.is_file()]
    print("OUT_WN_REN files:", [p.name for p in files])

    vel = {}
    ang = {}
    prj = {}

    vel_pattern = re.compile(r"^(?P<base>.+?)_(vel|speed|spd)$", re.IGNORECASE)
    ang_pattern = re.compile(r"^(?P<base>.+?)_(ang|dir|angle|bearing)$", re.IGNORECASE)
    prj_pattern = re.compile(r"^(?P<base>.+?)_(vel|speed|spd)$", re.IGNORECASE)

    for p in files:
        name = p.name
        lower = name.lower()

        if lower.endswith(".asc"):
            stem = p.stem
            m_vel = vel_pattern.match(stem)
            m_ang = ang_pattern.match(stem)
            if m_vel:
                vel[m_vel.group("base")] = p
            elif m_ang:
                ang[m_ang.group("base")] = p
        elif lower.endswith(".prj"):
            stem = p.stem
            m_prj = prj_pattern.match(stem)
            if m_prj:
                prj[m_prj.group("base")] = p

    bases = sorted(set(vel) & set(ang) & set(prj))
    if not bases:
        print("No paired windninja files found.")
        print("vel keys:", sorted(vel.keys()))
        print("ang keys:", sorted(ang.keys()))
        print("prj keys:", sorted(prj.keys()))

    return [(b, vel[b], ang[b], prj[b]) for b in bases]


def _read_prj(path: Path):
    wkt = path.read_text(encoding="utf-8", errors="ignore")
    return CRS.from_wkt(wkt)


def _read_raster_crs(raster_path: Path, prj_path: Path | None = None):
    if prj_path is not None and prj_path.exists():
        try:
            return _read_prj(prj_path)
        except Exception as exc:
            print(f"No se pudo leer PRJ {prj_path}: {exc}")

    try:
        with rasterio.open(raster_path) as src:
            if src.crs is not None:
                return src.crs
            if src.tags().get("crs"):
                return CRS.from_wkt(src.tags()["crs"])
    except Exception as exc:
        print(f"No se pudo leer CRS del raster {raster_path}: {exc}")

    return None


def _axial_angle(span_dir, wind_dir):
    d = np.abs(wind_dir - span_dir) % 360.0
    d = np.minimum(d, 360.0 - d)
    return np.minimum(d, 180.0 - d)


def _find_direction_field(columns):
    candidates = [
        "direccion",
        "direccio",
        "direction",
        "bearing",
        "azimuth",
        "angle",
        "angulo",
        "dir",
        "ang",
    ]

    lower_columns = [str(c).lower() for c in columns]

    for cand in candidates:
        for i, col in enumerate(lower_columns):
            if col == cand:
                return columns[i]

    for cand in candidates:
        for i, col in enumerate(lower_columns):
            if cand in col:
                return columns[i]

    return None


def ensure_vanos_from_supports(cfg) -> Path:
    out_vanos = Path(cfg.out_vanos_shp) if cfg.out_vanos_shp else Path(cfg.general_path) / "Calculos" / f"{Path(cfg.general_path).name}_vanos.shp"

    if out_vanos.exists():
        return out_vanos

    apoyos_candidates = []
    if cfg.out_apoyos_shp:
        apoyos_candidates.append(Path(cfg.out_apoyos_shp))

    apoyos_candidates.extend([
        Path(cfg.general_path) / "Apoyos" / "apoyos.shp",
        Path(cfg.general_path) / "Apoyos" / f"Apoyos {Path(cfg.general_path).name}.shp",
    ])

    apoyos_path = None
    for candidate in apoyos_candidates:
        if candidate is not None and candidate.exists():
            apoyos_path = candidate
            break

    if apoyos_path is None:
        raise FileNotFoundError(
            "No existe shapefile de apoyos. Busque Apoyos/apoyos.shp o Apoyos/Apoyos <case>.shp."
        )

    apoyos = gpd.read_file(apoyos_path)

    if apoyos.empty:
        raise ValueError("El shapefile de apoyos está vacío.")

    if apoyos.crs is None:
        apoyos = apoyos.set_crs(epsg=cfg.apoyos_epsg_arg or 25830)

    order_field = None
    for candidate in ["support_order", "generated_id", "id"]:
        if candidate in apoyos.columns:
            order_field = candidate
            break

    if order_field is not None:
        apoyos = apoyos.sort_values(order_field)

    points = [
        geom
        for geom in apoyos.geometry
        if geom is not None and geom.geom_type == "Point"
    ]

    if len(points) < 2:
        raise ValueError("Se necesitan al menos 2 apoyos para generar vanos.")

    records = []

    for i in range(len(points) - 1):
        p1 = points[i]
        p2 = points[i + 1]

        dx = p2.x - p1.x
        dy = p2.y - p1.y
        direccion = (np.degrees(np.arctan2(dx, dy)) + 360.0) % 360.0

        line = LineString([p1, p2])
        midpoint = line.interpolate(0.5, normalized=True)

        records.append({
            "MAT": f"VANO-{i + 1}",
            "direccion": float(direccion),
            "from_idx": i + 1,
            "to_idx": i + 2,
            "geometry": midpoint,
        })

    vanos = gpd.GeoDataFrame(records, geometry="geometry", crs=apoyos.crs)

    out_vanos.parent.mkdir(parents=True, exist_ok=True)
    vanos.to_file(out_vanos, driver="ESRI Shapefile", encoding="UTF-8")

    return out_vanos


def compute_worst_supports(cfg, top_n: int = 4) -> dict[str, Any]:
    out_vanos = ensure_vanos_from_supports(cfg)

    if not out_vanos.exists():
        raise FileNotFoundError(f"No existe shapefile de vanos: {out_vanos}")

    if cfg.out_wn_ren is None or not Path(cfg.out_wn_ren).exists():
        raise FileNotFoundError(f"No existe carpeta OUT_WN_REN: {cfg.out_wn_ren}")

    print("worst_supports case_path:", cfg.general_path)
    print("cfg.out_apoyos_shp:", cfg.out_apoyos_shp, "exists:", Path(cfg.out_apoyos_shp).exists() if cfg.out_apoyos_shp else False)
    print("cfg.out_vanos_shp:", out_vanos, "exists:", out_vanos.exists())
    print("cfg.out_wn_ren:", cfg.out_wn_ren, "exists:", Path(cfg.out_wn_ren).exists())
    print("cfg.out_v_perp_min_shp:", cfg.out_v_perp_min_shp)

    pairs = list_windninja_pairs(cfg.out_wn_ren)

    if not pairs:
        files = [p.name for p in Path(cfg.out_wn_ren).iterdir() if p.is_file()]
        raise FileNotFoundError(
            f"No se encontraron pares compatibles de WindNinja en {cfg.out_wn_ren}. "
            f"Archivos encontrados: {files}"
        )

    gdf = gpd.read_file(out_vanos)
    if gdf.empty:
        raise ValueError("El shapefile de vanos está vacío.")

    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=cfg.apoyos_epsg_arg or 25830)

    direction_field = _find_direction_field(gdf.columns)
    if direction_field is None:
        raise KeyError(
            f"No existe columna de dirección compatible en vanos. Columnas: {list(gdf.columns)}"
        )

    if not all(geom is not None for geom in gdf.geometry):
        raise ValueError("Al menos una geometría de la capa de vanos es nula.")

    if not all(geom.geom_type == "Point" for geom in gdf.geometry):
        gdf = gdf.copy()
        gdf.geometry = gdf.geometry.centroid

    direction_values = pd.to_numeric(gdf[direction_field], errors="coerce").to_numpy(dtype=float)
    if np.all(np.isnan(direction_values)):
        raise ValueError(
            f"La columna de dirección '{direction_field}' no contiene valores numéricos válidos."
        )

    records = []

    for case_name, vel_asc, ang_asc, prj_path in pairs:
        raster_crs = _read_raster_crs(vel_asc, prj_path)
        if raster_crs is None:
            raise RuntimeError(
                f"No se pudo determinar el CRS del raster {vel_asc} ni del PRJ {prj_path}."
            )

        gdf_r = gdf.to_crs(raster_crs)
        coords = [(geom.x, geom.y) for geom in gdf_r.geometry]

        with rasterio.open(vel_asc) as src_vel, rasterio.open(ang_asc) as src_ang:
            vel_vals = np.array([v[0] for v in src_vel.sample(coords)], dtype=float)
            ang_vals = np.array([v[0] for v in src_ang.sample(coords)], dtype=float)

            if src_vel.nodata is not None:
                vel_vals[np.isclose(vel_vals, src_vel.nodata)] = np.nan

            if src_ang.nodata is not None:
                ang_vals[np.isclose(ang_vals, src_ang.nodata)] = np.nan

        alpha = _axial_angle(direction_values, ang_vals)
        v_perp = np.abs(vel_vals * np.sin(np.deg2rad(alpha)))

        for i in range(len(gdf)):
            row = gdf.iloc[i]
            records.append({
                "idx": i,
                "MAT": row.get("MAT", str(i)),
                "case": case_name,
                "direccion": float(direction_values[i]) if np.isfinite(direction_values[i]) else np.nan,
                "wind_speed": float(vel_vals[i]) if np.isfinite(vel_vals[i]) else np.nan,
                "wind_dir": float(ang_vals[i]) if np.isfinite(ang_vals[i]) else np.nan,
                "alpha_eff": float(alpha[i]) if np.isfinite(alpha[i]) else np.nan,
                "v_perp": float(v_perp[i]) if np.isfinite(v_perp[i]) else np.nan,
                "geometry": row.geometry,
            })

    df = pd.DataFrame(records).dropna(subset=["v_perp"])

    if df.empty:
        raise ValueError("No se obtuvieron valores válidos de v_perp.")

    idx_min = df.groupby("idx")["v_perp"].idxmin()
    worst_all = df.loc[idx_min].sort_values("v_perp", ascending=True)
    worst_top = worst_all.head(top_n).copy()

    out_csv = Path(cfg.general_path) / "Calculos" / "worst_supports.csv"
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    worst_top.drop(columns=["geometry"]).to_csv(out_csv, index=False)

    out_shp = Path(cfg.out_v_perp_min_shp)
    out_shp.parent.mkdir(parents=True, exist_ok=True)

    out_gdf = gpd.GeoDataFrame(
        worst_top.drop(columns=["geometry"]),
        geometry=worst_top["geometry"],
        crs=gdf.crs,
    )

    out_gdf = out_gdf.rename(columns={
        "wind_speed": "w_speed",
        "wind_dir": "w_dir",
        "alpha_eff": "alpha",
        "v_perp": "vperp_min",
    })

    out_gdf.to_file(out_shp, driver="ESRI Shapefile", encoding="UTF-8")

    return {
        "top_n": top_n,
        "csv": str(out_csv),
        "shp": str(out_shp),
        "worst": worst_top.drop(columns=["geometry"]).to_dict(orient="records"),
    }