from pathlib import Path
from typing import Optional

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from app.services.towers.towers_validation_service import parse_xyz_with_autoscale


def excel_to_shp(
    xlsx_path: Path,
    shp_path: Path,
    sheet: Optional[str] = None,
    epsg: Optional[int] = None,
    col_x: str = "X",
    col_y: str = "Y",
    col_z: str = "Z",
    col_label: str = "Structure Comment",
) -> pd.DataFrame:
    xlsx_path = Path(xlsx_path)
    shp_path = Path(shp_path)

    wb = pd.read_excel(xlsx_path, sheet_name=sheet, engine="openpyxl")  # no forzamos str: Excel puede traer numérico
    if isinstance(wb, dict):
        if not wb:
            raise ValueError("El Excel no contiene hojas.")
        df = wb[next(iter(wb))]
    else:
        df = wb

    df.columns = [str(c).strip() for c in df.columns]

    for c in (col_x, col_y, col_z, col_label):
        if c not in df.columns:
            raise KeyError(f"Falta la columna '{c}'. Columnas disponibles: {list(df.columns)}")

    # Conversión + autoscale
    df["_X"] = df[col_x].apply(lambda v: parse_xyz_with_autoscale(v, "x"))
    df["_Y"] = df[col_y].apply(lambda v: parse_xyz_with_autoscale(v, "y"))
    df["_Z"] = df[col_z].apply(lambda v: parse_xyz_with_autoscale(v, "z"))

    # Campo para etiquetar
    df["MAT"] = df[col_label].astype(str).str.strip()

    # Diagnóstico rápido (puedes comentar luego)
    print("Rangos interpretados:")
    print("X:", df["_X"].min(), df["_X"].max())
    print("Y:", df["_Y"].min(), df["_Y"].max())
    print("Z:", df["_Z"].min(), df["_Z"].max())

    geometry = [Point(x, y, z) for x, y, z in zip(df["_X"], df["_Y"], df["_Z"])]
    gdf = gpd.GeoDataFrame(df.drop(columns=["_X", "_Y", "_Z"]), geometry=geometry)

    if epsg is not None:
        gdf = gdf.set_crs(epsg=epsg, allow_override=True)

    shp_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(shp_path, driver="ESRI Shapefile", encoding="UTF-8")

    return df