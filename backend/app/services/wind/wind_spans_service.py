from pathlib import Path
from typing import List, Tuple

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from pyproj import CRS
import re


def sample_windninja_asc_at_points(
    vanos_df: pd.DataFrame,
    speed_asc: str | Path,
    dir_asc: str | Path,
    prj_path: str | Path | None = None,
    points_epsg: int = 25830,
    x_col: str = "UTMx",
    y_col: str = "UTMy",
    keep_cols: list[str] | None = None,
) -> pd.DataFrame:
    """
    Extrae (sample) velocidad y dirección de viento de WindNinja (ASCII Grid .asc) en los puntos intermedios de vano.

    - speed_asc: ráster ASCII de magnitud (m/s típicamente)
    - dir_asc:   ráster ASCII de dirección (grados; normalmente convención meteorológica)
    - prj_path:  fichero .prj con WKT del CRS (si los .asc no traen CRS). Si None, intenta inferirlo.
    - points_epsg: CRS de las coordenadas de los puntos (p.ej. 25830)
    """
    speed_asc = Path(speed_asc)
    dir_asc = Path(dir_asc)

    df = vanos_df.copy()
    df = df.dropna(subset=[x_col, y_col]).reset_index(drop=True)

    if keep_cols is not None:
        cols = list(keep_cols)
        if x_col not in cols:
            cols.append(x_col)
        if y_col not in cols:
            cols.append(y_col)
        missing = [c for c in cols if c not in df.columns]
        if missing:
            raise KeyError(f"Columnas no encontradas en vanos_df: {missing}")
        df = df.loc[:, cols]

    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df[x_col].astype(float), df[y_col].astype(float)),
        crs=f"EPSG:{int(points_epsg)}",
    )

    # CRS desde .prj (WKT), si se proporciona
    prj_crs = None
    if prj_path is not None:
        prj_path = Path(prj_path)
        wkt = prj_path.read_text(encoding="utf-8", errors="ignore")
        prj_crs = CRS.from_wkt(wkt)

    with rasterio.open(speed_asc) as src_spd, rasterio.open(dir_asc) as src_dir:
        # Validación mínima de rejilla
        if (src_spd.transform != src_dir.transform) or (src_spd.width != src_dir.width) or (src_spd.height != src_dir.height):
            raise ValueError("Los .asc de velocidad y dirección no están en la misma rejilla (transform/size).")

        # Determinar CRS efectivo del ráster
        raster_crs = src_spd.crs
        if raster_crs is None and prj_crs is not None:
            raster_crs = prj_crs
        if raster_crs is None:
            raise ValueError(
                "No se pudo determinar el CRS del ráster (.asc no trae CRS y no se proporcionó .prj)."
            )

        # Reproyectar puntos al CRS del ráster si hace falta
        if gdf.crs != raster_crs:
            gdf_r = gdf.to_crs(raster_crs)
        else:
            gdf_r = gdf

        coords = [(geom.x, geom.y) for geom in gdf_r.geometry]

        spd_vals = np.array([v[0] for v in src_spd.sample(coords)], dtype=float)
        dir_vals = np.array([v[0] for v in src_dir.sample(coords)], dtype=float)

        spd_nodata = src_spd.nodata
        dir_nodata = src_dir.nodata

    out = gdf.drop(columns="geometry").copy()
    out["wind_speed"] = spd_vals
    out["wind_dir"] = dir_vals

    # NoData -> NaN (robusto ante nodata definido en cabecera ASCII)
    if spd_nodata is not None:
        m = np.isclose(out["wind_speed"], float(spd_nodata))
        out.loc[m, "wind_speed"] = np.nan
    if dir_nodata is not None:
        m = np.isclose(out["wind_dir"], float(dir_nodata))
        out.loc[m, "wind_dir"] = np.nan

    return out


def add_effective_wind_projection_on_span(
    df: pd.DataFrame,
    span_dir_col: str = "direccion",      # dirección del vano (deg, 0=N, horario)
    wind_dir_col: str = "wind_dir",       # dirección del viento (deg, 0=N, horario; puede ser "from" meteorológica)
    wind_speed_col: str = "wind_speed",   # magnitud del viento (m/s)
    out_angle_col: str = "alpha_eff_deg", # ángulo axial efectivo en [0,90]
    out_proj_col: str = "v_proj_eff",     # proyección efectiva (m/s) sobre el eje del vano (sin signo)
) -> pd.DataFrame:
    """
    Añade al DataFrame:
      - alpha_eff_deg: ángulo axial entre dirección de viento y eje del vano, en [0,90] grados.
      - v_proj_eff: proyección efectiva (|V|·|cos(alpha)|) sobre el eje del vano (sin signo).

    Importante:
    - El cálculo es AXIAL: no distingue entre direcciones separadas 180° (ni en viento ni en vano).
    - Por tanto, no es necesario convertir la convención meteorológica ("from") a vector ("to").
    """
    out = df.copy()

    theta_span = pd.to_numeric(out[span_dir_col], errors="coerce").to_numpy(dtype=float)
    theta_wind = pd.to_numeric(out[wind_dir_col], errors="coerce").to_numpy(dtype=float)
    v = pd.to_numeric(out[wind_speed_col], errors="coerce").to_numpy(dtype=float)

    # Diferencia angular reducida a [0,180)
    d = np.abs(theta_wind - theta_span) % 360.0
    d = np.minimum(d, 360.0 - d)           # ahora en [0,180]
    alpha_eff = np.minimum(d, 180.0 - d)   # axial -> [0,90]

    v_proj = np.abs(v * np.sin(np.deg2rad(alpha_eff)))

    out[out_angle_col] = alpha_eff
    out[out_proj_col] = v_proj
    return out


def list_windninja_result_pairs(folder: str | Path) -> List[Tuple[str, Path, Path, Path, Path]]:
    """
    Busca en `folder` resultados WindNinja y devuelve una lista de tuplas:

      (base_name, vel_asc, ang_asc, vel_prj, ang_prj)

    donde `base_name` es el nombre común SIN los sufijos:
      _vel.asc, _ang.asc, _vel.prj, _ang.prj

    Requisitos:
      - ficheros con patrón: <base>_vel.asc, <base>_ang.asc, <base>_vel.prj, <base>_ang.prj
      - se consideran coincidencias completas (si falta alguno, ese base se descarta).
    """
    folder = Path(folder)
    if not folder.exists():
        raise FileNotFoundError(folder)

    # Índices por base
    vel_asc = {}
    ang_asc = {}
    vel_prj = {}
    ang_prj = {}

    for p in folder.iterdir():
        if not p.is_file():
            continue
        name = p.name

        if name.endswith("_vel.asc"):
            base = name[:-len("_vel.asc")]
            vel_asc[base] = p
        elif name.endswith("_ang.asc"):
            base = name[:-len("_ang.asc")]
            ang_asc[base] = p
        elif name.endswith("_vel.prj"):
            base = name[:-len("_vel.prj")]
            vel_prj[base] = p
        elif name.endswith("_ang.prj"):
            base = name[:-len("_ang.prj")]
            ang_prj[base] = p

    bases = sorted(set(vel_asc) & set(ang_asc) & set(vel_prj) & set(ang_prj))

    return [(b, vel_asc[b], ang_asc[b], vel_prj[b], ang_prj[b]) for b in bases]


def parse_windninja_dir_speed_from_name(
    filename: str | Path,
    *,
    prefix_to_remove: str = "",
) -> Tuple[float, float]:
    """
    Extrae (direccion_deg, velocidad) desde un nombre que contiene el patrón:
      DDD_d_VV_v
    (3 dígitos dir entera, 1 dígito dir decimal, 2 dígitos vel entera, 1 dígito vel decimal),
    separado por '_' y en ese orden.

    El patrón puede aparecer tras un prefijo (opcional) y puede haber más texto después.
    """
    s = Path(filename).name.strip()

    if prefix_to_remove:
        # elimina primera ocurrencia del prefijo (más robusto que startswith)
        if prefix_to_remove in s:
            s = s.replace(prefix_to_remove, "", 1)
        else:
            raise ValueError(f"No se encontró el prefijo '{prefix_to_remove}' en '{Path(filename).name}'.")

    # Buscar el patrón en cualquier parte
    m = re.search(r"(?P<dir_i>\d{3})_(?P<dir_d>\d)_(?P<spd_i>\d{2})_(?P<spd_d>\d)", s)
    if not m:
        raise ValueError(
            f"No se pudo extraer dirección/velocidad de '{Path(filename).name}'. "
            "Se esperaba encontrar: DDD_d_VV_v (p.ej. 270_3_12_5)."
        )

    dir_deg = float(f"{m.group('dir_i')}.{m.group('dir_d')}")
    spd = float(f"{m.group('spd_i')}.{m.group('spd_d')}")
    return dir_deg, spd


def build_all_cases_wind_effective_df(
    pairs,
    puntos_analisis_df,
    *,
    prefix_to_remove: str,
    points_epsg: int,
    keep_cols=None,
    # columnas existentes
    span_dir_col: str = "direccion",
    # nombres de salida
    case_col: str = "case",
    out_dir_col: str = "d_applied_deg",
    out_spd_col: str = "v_applied",
    # salida de efectivos
    out_angle_col: str = "alpha_eff_deg",
    out_perp_col: str = "v_perp",
    out_par_col: str = "v_par",
) -> pd.DataFrame:
    """
    Itera sobre `pairs` = [(base, vel_asc, ang_asc, vel_prj, ang_prj), ...],
    muestrea viento en puntos de vano y calcula:
      - alpha_eff_deg: ángulo axial efectivo entre eje de vano y eje de viento (0..90)
      - v_perp: componente transversal (refrigeración) = V*sin(alpha_eff)
      - v_par:  componente paralela = V*cos(alpha_eff)

    Añade a cada fila:
      - case (base)
      - d_applied_deg, v_applied: parámetros de simulación extraídos del nombre del caso
    """
    out_list = []

    for base, vasc, aasc, vprj, aprj in pairs:
        # 1) dirección/velocidad "aplicadas" (del nombre)
        d_applied, v_applied = parse_windninja_dir_speed_from_name(
            base, prefix_to_remove=prefix_to_remove
        )

        # 2) muestreo de WindNinja en puntos de vanos (usa los .asc/.prj del caso)
        df_w = sample_windninja_asc_at_points(
            puntos_analisis_df,
            speed_asc=vasc,
            dir_asc=aasc,
            prj_path=vprj,            # normalmente basta con uno
            points_epsg=points_epsg,
            keep_cols=keep_cols,
        )

        # 3) cálculo axial efectivo (sin sentido) + componentes
        theta_span = pd.to_numeric(df_w[span_dir_col], errors="coerce").to_numpy(dtype=float)
        theta_wind = pd.to_numeric(df_w["wind_dir"], errors="coerce").to_numpy(dtype=float)
        V = pd.to_numeric(df_w["wind_speed"], errors="coerce").to_numpy(dtype=float)

        d = np.abs(theta_wind - theta_span) % 360.0
        d = np.minimum(d, 360.0 - d)          # [0,180]
        alpha_eff = np.minimum(d, 180.0 - d)  # axial -> [0,90]
        a = np.deg2rad(alpha_eff)

        df_w[out_angle_col] = alpha_eff
        df_w[out_perp_col] = np.abs(V * np.sin(a))  # transversal (refrigeración)
        df_w[out_par_col]  = np.abs(V * np.cos(a))  # paralela

        # 4) columnas del caso
        df_w[case_col] = base
        df_w[out_dir_col] = d_applied
        df_w[out_spd_col] = v_applied

        out_list.append(df_w)

    if not out_list:
        return pd.DataFrame()

    return pd.concat(out_list, ignore_index=True)


def plot_hist_errores_cuadraticos(errores, bins=40, titulo=""):
    errores = np.asarray(errores, dtype=float)

    # --- configuración estética global ---
    mpl.rcParams.update({
        "figure.figsize": (9, 5.2),
        "figure.dpi": 120,
        "axes.titlesize": 16,
        "axes.labelsize": 13,
        "xtick.labelsize": 11,
        "ytick.labelsize": 11,
        "legend.fontsize": 11,
        "axes.linewidth": 1.0,
        "grid.linewidth": 0.8,
        "lines.linewidth": 1.8,
        "font.family": "serif",
        "mathtext.fontset": "cm",   # Computer Modern, estilo LaTeX sin requerir usetex
    })

    fig, ax = plt.subplots()

    # Fondo
    fig.patch.set_facecolor("white")      # exterior (ticks, labels, márgenes)
    ax.set_facecolor("#ffe5e0")           # interior (salmón claro)

    # Histograma
    n, b, patches = ax.hist(
        errores,
        bins=bins,
        edgecolor="black",
        linewidth=0.8,
        alpha=0.9
    )

    # Estadísticos
    media = np.mean(errores)
    mediana = np.median(errores)
    maximo = np.max(errores)
    minimo = np.min(errores)

    ax.axvline(media, linestyle="--", linewidth=2.0, label=fr"Media = {media:.4f}")
    ax.axvline(mediana, linestyle="-.", linewidth=2.0, label=fr"Mediana = {mediana:.4f}")
    ax.axvline(maximo, linestyle=":", linewidth=2.0, label=fr"Máximo = {maximo:.4f}")
    ax.axvline(minimo, linestyle=":", linewidth=2.0, label=fr"Mínimo = {minimo:.4f}")
    

    # Títulos y etiquetas
    ax.set_title( titulo, pad=14)
    ax.set_xlabel(r"Diferencia [m/s]")
    ax.set_ylabel(r"Frecuencia")

    # Rejilla
    ax.grid(True, which="major", linestyle="--", alpha=0.35)
    ax.set_axisbelow(True)

    # Bordes
    for spine in ax.spines.values():
        spine.set_linewidth(1.0)

    # Leyenda
    ax.legend(frameon=True, fancybox=True, framealpha=0.95)

    plt.tight_layout()
    plt.show()