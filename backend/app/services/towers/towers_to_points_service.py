from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from shapely import line_interpolate_point


def build_vanos_df(
    df: pd.DataFrame,
    mat_col: str = "MAT",
    x_col: str = "_X",
    y_col: str = "_Y",
    z_col: str = "_Z",
) -> pd.DataFrame:
    """
    Devuelve un DataFrame con:
    MAT, UTMx, UTMy, UTMz, distancia, direccion, vanoUTMx, vanoUTMy

    - distancia: sqrt((Δx)^2 + (Δy)^2) entre fila i y i-1
    - direccion: azimut (deg) desde Norte (+Y) horario, en [0, 360)
    - vanoUTMx/vanoUTMy: punto medio entre (x_i,y_i) y (x_{i-1},y_{i-1})
    """
    # Copias como float para asegurar operaciones numéricas
    x = df[x_col].astype(float)
    y = df[y_col].astype(float)
    z = df[z_col].astype(float)

    dx = x.diff()
    dy = y.diff()

    distancia = np.hypot(dx, dy)

    # Azimut desde Norte: atan2(Δx, Δy)  -> radianes, luego grados
    direccion = (np.degrees(np.arctan2(dx, dy)) + 360.0) % 360.0

    vanoUTMx = (x + x.shift(1)) / 2.0
    vanoUTMy = (y + y.shift(1)) / 2.0

    out = pd.DataFrame({
        "MAT": df[mat_col],
        "UTMx": x,
        "UTMy": y,
        "UTMz": z,
        "distancia": distancia,
        "direccion": direccion,
        "vanoUTMx": vanoUTMx,
        "vanoUTMy": vanoUTMy,
    })

    return out


def export_vanos_midpoints_shp(
    vanos_df: pd.DataFrame,
    shp_path: str | Path,
    epsg: int = 25830,
    xmid_col: str = "vanoUTMx",
    ymid_col: str = "vanoUTMy",
    keep_cols: list[str] | None = None,
) -> Path:
    """
    Exporta a Shapefile (QGIS) los puntos intermedios de vano.

    Nota: evita duplicados si keep_cols ya incluye xmid_col/ymid_col.
    """
    import geopandas as gpd

    shp_path = Path(shp_path)
    shp_path.parent.mkdir(parents=True, exist_ok=True)

    # Filtra filas sin vano (primera fila) o con NaNs
    gdf_src = vanos_df.copy().dropna(subset=[xmid_col, ymid_col])

    # Selección de atributos sin duplicar nombres
    if keep_cols is not None:
        cols = list(keep_cols)
        if xmid_col not in cols:
            cols.append(xmid_col)
        if ymid_col not in cols:
            cols.append(ymid_col)

        missing = [c for c in cols if c not in gdf_src.columns]
        if missing:
            raise KeyError(f"Columnas no encontradas en vanos_df: {missing}")

        gdf_src = gdf_src.loc[:, cols]

    # Asegura Series 1D aunque existan columnas duplicadas por error upstream
    xmid = gdf_src.loc[:, xmid_col]
    ymid = gdf_src.loc[:, ymid_col]
    if isinstance(xmid, pd.DataFrame):
        xmid = xmid.iloc[:, 0]
    if isinstance(ymid, pd.DataFrame):
        ymid = ymid.iloc[:, 0]

    gdf = gpd.GeoDataFrame(
        gdf_src,
        geometry=gpd.points_from_xy(xmid.astype(float), ymid.astype(float)),
        crs=f"EPSG:{int(epsg)}",
    )

    # Shapefile: nombres de campo limitados (~10 chars)
    rename_map = {}
    if xmid_col in gdf.columns and len(xmid_col) > 10:
        rename_map[xmid_col] = "VANO_X"
    if ymid_col in gdf.columns and len(ymid_col) > 10:
        rename_map[ymid_col] = "VANO_Y"
    if rename_map:
        gdf = gdf.rename(columns=rename_map)

    gdf.to_file(shp_path, driver="ESRI Shapefile", encoding="UTF-8")
    return shp_path


def read_points_from_shp(
    shp_path: str | Path,
    source_epsg: Optional[int] = 25830,
    to_epsg: int | None = None,
    keep_cols: list[str] | None = None,
    rename: dict[str, str] | None = None,
    x_col: str = "apoyoUTMx",
    y_col: str = "apoyoUTMy",
    geometry_as_midpoint_xy: bool = True,
) -> pd.DataFrame:
    """
    Lee un shapefile (.shp) de puntos (pueden ser apoyos, vanos, etc.) y devuelve un DataFrame.

    Parámetros
    ----------
    shp_path : ruta al .shp
    to_epsg  : si se indica, reproyecta a EPSG:to_epsg antes de extraer coordenadas
    keep_cols: columnas a conservar (si None, conserva todas)
    rename   : diccionario para renombrar columnas (p.ej. {"VANO_X":"vanoUTMx","VANO_Y":"vanoUTMy"})
    x_col, y_col : nombres finales deseados para coordenadas del punto medio
    geometry_as_midpoint_xy : si True, toma x/y desde la geometría (recomendado)

    Devuelve
    --------
    pandas.DataFrame con atributos + vanoUTMx/vanoUTMy (si geometry_as_midpoint_xy=True).
    """
    import geopandas as gpd

    shp_path = Path(shp_path)
    if not shp_path.exists():
        raise FileNotFoundError(shp_path)

    gdf = gpd.read_file(shp_path)

    # Renombrado temprano (útil por nombres truncados del Shapefile)
    if rename:
        gdf = gdf.rename(columns=rename)

    # 1. Asignar CRS si falta
    if gdf.crs is None:
        print(f"CRS no definido → asignando EPSG:{source_epsg}")
        gdf = gdf.set_crs(epsg=source_epsg)

    # 2. Reproyección
    if to_epsg is not None:
        gdf = gdf.to_crs(epsg=int(to_epsg))

    # Extraer coordenadas desde la geometría (puntos)
    if geometry_as_midpoint_xy:
        if not all(gdf.geometry.geom_type == "Point"):
            raise ValueError("El shapefile no contiene geometrías Point. Ajusta geometry_as_midpoint_xy o revisa el .shp.")
        gdf[x_col] = gdf.geometry.x.astype(float)
        gdf[y_col] = gdf.geometry.y.astype(float)
    else:
        # En este modo exigimos que existan campos x_col/y_col ya en atributos
        if x_col not in gdf.columns or y_col not in gdf.columns:
            raise KeyError(f"No existen columnas {x_col}/{y_col} y geometry_as_midpoint_xy=False.")

    # Selección de columnas
    if keep_cols is not None:
        cols = list(keep_cols)
        # asegura que las coordenadas estén
        if x_col not in cols:
            cols.append(x_col)
        if y_col not in cols:
            cols.append(y_col)

        missing = [c for c in cols if c not in gdf.columns]
        if missing:
            raise KeyError(f"Columnas no encontradas en el shapefile: {missing}")

        gdf = gdf.loc[:, cols + ["geometry"]] if "geometry" in gdf.columns else gdf.loc[:, cols]

    # Devolver DataFrame (sin geometría)
    return pd.DataFrame(gdf.drop(columns="geometry"))


# muestrea la traza de la línea en pasos de step_m metros
def sample_line(line, step_m):
    distances = np.arange(0, line.length, step_m)
    distances = np.append(distances, line.length)

    points = [line_interpolate_point(line, d) for d in distances]

    return [(p.x, p.y) for p in points]


# incorpora a cada tramo entre apoyos la dirección de dicho tramo considerando el norte
def add_bearing_from_north(df, x_col="UTMx", y_col="UTMy", out_col="dir_deg"):
    df = df.copy()

    # Punto siguiente
    dx = (-1) * (df[x_col].shift(-1) - df[x_col])  # -1 porque UTMx avanza del este hacia el oeste
    dy = df[y_col].shift(-1) - df[y_col]

    # Ángulo respecto al norte, sentido horario
    ang_deg = np.degrees(np.arctan2(dx, dy))
    ang_deg = (ang_deg + 360) % 360

    # Para el último punto, mantener la dirección del anterior
    if len(df) >= 2:
        ang_deg.iloc[-1] = ang_deg.iloc[-2]
    elif len(df) == 1:
        ang_deg.iloc[0] = np.nan

    df[out_col] = ang_deg
    return df