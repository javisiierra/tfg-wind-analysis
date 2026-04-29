from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from pyproj import CRS


def list_windninja_pairs(folder: str | Path):
    folder = Path(folder)

    vel = {}
    ang = {}
    prj = {}

    for p in folder.iterdir():
        if not p.is_file():
            continue

        name = p.name

        if name.endswith("_vel.asc"):
            vel[name.removesuffix("_vel.asc")] = p
        elif name.endswith("_ang.asc"):
            ang[name.removesuffix("_ang.asc")] = p
        elif name.endswith("_vel.prj"):
            prj[name.removesuffix("_vel.prj")] = p

    bases = sorted(set(vel) & set(ang) & set(prj))
    return [(b, vel[b], ang[b], prj[b]) for b in bases]


def _read_prj(path: Path):
    wkt = path.read_text(encoding="utf-8", errors="ignore")
    return CRS.from_wkt(wkt)


def _axial_angle(span_dir, wind_dir):
    d = np.abs(wind_dir - span_dir) % 360.0
    d = np.minimum(d, 360.0 - d)
    return np.minimum(d, 180.0 - d)


def compute_worst_supports(cfg, top_n: int = 4) -> dict[str, Any]:
    if cfg.out_vanos_shp is None or not Path(cfg.out_vanos_shp).exists():
        raise FileNotFoundError(f"No existe shapefile de vanos: {cfg.out_vanos_shp}")

    if cfg.out_wn_ren is None or not Path(cfg.out_wn_ren).exists():
        raise FileNotFoundError(f"No existe carpeta OUT_WN_REN: {cfg.out_wn_ren}")

    pairs = list_windninja_pairs(cfg.out_wn_ren)
    if not pairs:
        raise FileNotFoundError(f"No se encontraron pares *_vel.asc / *_ang.asc en {cfg.out_wn_ren}")

    gdf = gpd.read_file(cfg.out_vanos_shp)

    if gdf.empty:
        raise ValueError("El shapefile de vanos está vacío.")

    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=cfg.apoyos_epsg_arg or 25830)

    if "direccion" not in gdf.columns:
        raise KeyError(f"No existe columna 'direccion' en vanos. Columnas: {list(gdf.columns)}")

    records = []

    for case_name, vel_asc, ang_asc, prj_path in pairs:
        raster_crs = _read_prj(prj_path)

        gdf_r = gdf.to_crs(raster_crs)
        coords = [(geom.x, geom.y) for geom in gdf_r.geometry]

        with rasterio.open(vel_asc) as src_vel, rasterio.open(ang_asc) as src_ang:
            vel_vals = np.array([v[0] for v in src_vel.sample(coords)], dtype=float)
            ang_vals = np.array([v[0] for v in src_ang.sample(coords)], dtype=float)

            if src_vel.nodata is not None:
                vel_vals[np.isclose(vel_vals, src_vel.nodata)] = np.nan

            if src_ang.nodata is not None:
                ang_vals[np.isclose(ang_vals, src_ang.nodata)] = np.nan

        span_dir = pd.to_numeric(gdf["direccion"], errors="coerce").to_numpy(dtype=float)
        alpha = _axial_angle(span_dir, ang_vals)
        v_perp = np.abs(vel_vals * np.sin(np.deg2rad(alpha)))

        for i, row in gdf.iterrows():
            records.append({
                "idx": i,
                "MAT": row.get("MAT", str(i)),
                "case": case_name,
                "direccion": float(span_dir[i]) if np.isfinite(span_dir[i]) else np.nan,
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