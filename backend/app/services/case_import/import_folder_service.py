from __future__ import annotations

from pathlib import Path
from typing import Iterable

import geopandas as gpd
import pandas as pd
from fastapi import HTTPException
from shapely.geometry import Point, Polygon, box
from shapely.wkt import loads as load_wkt


SUPPORTED_EXCEL_SUFFIXES = {".xlsx", ".xls"}
SUPPORTED_SHAPE_EXTENSIONS = {".shp", ".dbf", ".shx", ".prj", ".cpg", ".qpj"}


def _ensure_case_dirs(case_root: Path) -> dict[str, Path]:
    folders = {
        "case": case_root,
        "shp": case_root / "SHP",
        "apoyos": case_root / "Apoyos",
        "mdt": case_root / "MDT_WN",
        "weather": case_root / "Weather_Input_Data",
        "out_wn": case_root / "OUT_WN",
        "out_wn_ren": case_root / "OUT_WN_REN",
        "wr": case_root / "WR",
    }

    for path in folders.values():
        path.mkdir(parents=True, exist_ok=True)

    return folders


def _find_support_excel(case_root: Path) -> Path:
    candidates = [
        p
        for p in case_root.rglob("*.xls*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXCEL_SUFFIXES
    ]

    if not candidates:
        raise HTTPException(
            status_code=404,
            detail=(
                "No se encontró ningún archivo de Excel de apoyos en la carpeta proporcionada. "
                "Busque un archivo con extensión .xlsx o .xls dentro de la carpeta."
            ),
        )

    if len(candidates) == 1:
        return candidates[0]

    preferred = [p for p in candidates if "apoy" in p.stem.lower() or "apoy" in "".join(p.parts).lower()]
    if len(preferred) == 1:
        return preferred[0]

    inside_apoyos = [p for p in candidates if "apoyos" in [part.lower() for part in p.parts]]
    if len(inside_apoyos) == 1:
        return inside_apoyos[0]

    raise HTTPException(
        status_code=400,
        detail=(
            "Se han encontrado varios archivos de Excel y no es posible determinar cuál usar. "
            f"Archivos encontrados: {[str(p) for p in candidates]}"
        ),
    )


def _find_trace_shapefile(case_root: Path) -> Path:
    candidates = [
        p
        for p in case_root.rglob("*.shp")
        if p.is_file()
        and "apoyos" not in [part.lower() for part in p.parts]
        and "dominio" not in p.stem.lower()
        and "wr" not in [part.lower() for part in p.parts]
    ]

    if not candidates:
        raise HTTPException(
            status_code=404,
            detail=(
                "No se encontró ningún shapefile de traza en la carpeta proporcionada. "
                "Busque un archivo .shp dentro de la carpeta o de sus subcarpetas."
            ),
        )

    if len(candidates) == 1:
        return candidates[0]

    line_candidates = []
    errors: list[str] = []

    for candidate in candidates:
        try:
            gdf = gpd.read_file(candidate)
            if gdf.empty:
                continue
            geom_types = {geom_type.lower() for geom_type in gdf.geom_type.unique() if geom_type}
            if geom_types & {"linestring", "multilinestring"}:
                line_candidates.append(candidate)
        except Exception as exc:
            errors.append(f"{candidate}: {exc}")

    if len(line_candidates) == 1:
        return line_candidates[0]

    if len(line_candidates) > 1:
        raise HTTPException(
            status_code=400,
            detail=(
                "Se encontraron varios shapefiles de traza en la carpeta. "
                f"Candidates: {[str(p) for p in line_candidates]}"
            ),
        )

    raise HTTPException(
        status_code=400,
        detail=(
            "Se encontró más de un archivo .shp y no se pudo determinar cuál es la traza. "
            f"Archivos encontrados: {[str(p) for p in candidates]}. "
            f"Errores de lectura: {errors}"
        ),
    )


def _infer_coordinate_columns(dataframe: pd.DataFrame) -> tuple[str, str]:
    lower_columns = {col.lower(): col for col in dataframe.columns}

    candidates = [
        ("x", "y"),
        ("east", "north"),
        ("easting", "northing"),
        ("lon", "lat"),
        ("longitude", "latitude"),
        ("long", "lat"),
        ("utm_e", "utm_n"),
        ("eastings", "northings"),
    ]

    for x_key, y_key in candidates:
        if x_key in lower_columns and y_key in lower_columns:
            return lower_columns[x_key], lower_columns[y_key]

    if "geometry" in lower_columns or "wkt" in lower_columns:
        raise HTTPException(
            status_code=400,
            detail=(
                "El archivo de Excel de apoyos contiene geometría en WKT, pero el soporte "
                "actual solo admite columnas de coordenadas X/Y o lon/lat. "
                "Use columnas como X/Y, East/North, Lon/Lat, Longitude/Latitude."
            ),
        )

    available = list(dataframe.columns)
    raise HTTPException(
        status_code=400,
        detail=(
            "No se encontraron columnas de coordenadas en el archivo de Excel de apoyos. "
            f"Columnas disponibles: {available}. "
            "Busque pares como X/Y, East/North, Lon/Lat o Longitude/Latitude."
        ),
    )


def _load_support_dataframe(excel_path: Path) -> pd.DataFrame:
    if not excel_path.exists():
        raise HTTPException(status_code=404, detail=f"No existe el archivo de Excel: {excel_path}")

    try:
        engine = "openpyxl" if excel_path.suffix.lower() == ".xlsx" else "xlrd"
        return pd.read_excel(excel_path, engine=engine)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"No se pudo leer el archivo de Excel de apoyos: {exc}",
        )


def _write_supports_shapefile(
    dataframe: pd.DataFrame,
    x_col: str,
    y_col: str,
    shp_path: Path,
    epsg: int = 25830,
) -> gpd.GeoDataFrame:
    if x_col not in dataframe.columns or y_col not in dataframe.columns:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Columnas de coordenadas no encontradas en el Excel: {x_col}, {y_col}. "
                "Verifique los nombres de las columnas."
            ),
        )

    points = [Point(float(x), float(y)) for x, y in zip(dataframe[x_col], dataframe[y_col])]
    gdf = gpd.GeoDataFrame(
        dataframe.drop(columns={x_col, y_col}),
        geometry=points,
        crs=f"EPSG:{epsg}",
    )

    shp_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(shp_path, driver="ESRI Shapefile", encoding="UTF-8")

    return gdf


def _write_geojson(gdf: gpd.GeoDataFrame, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(target_path, driver="GeoJSON", encoding="UTF-8")


def _copy_shapefile_components(source_shp: Path, target_shp: Path) -> None:
    if not source_shp.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No existe el shapefile de traza: {source_shp}",
        )

    for extension in SUPPORTED_SHAPE_EXTENSIONS:
        source = source_shp.with_suffix(extension)
        if source.exists():
            source.parent.mkdir(parents=True, exist_ok=True)
            target = target_shp.with_suffix(extension)
            target.write_bytes(source.read_bytes())


def _create_domain_from_trace(trace_shp: Path, domain_shp: Path, buffer_m: float = 100.0) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(trace_shp)

    if gdf.empty:
        raise HTTPException(
            status_code=400,
            detail=f"El shapefile de traza está vacío: {trace_shp}",
        )

    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=25830)

    minx, miny, maxx, maxy = gdf.total_bounds
    if minx == maxx or miny == maxy:
        raise HTTPException(
            status_code=400,
            detail=(
                "No se pudo calcular el dominio porque la traza tiene límites nulos. "
                f"Bounds: {gdf.total_bounds}"
            ),
        )

    buffer_value = max(buffer_m, max((maxx - minx), (maxy - miny)) * 0.05)
    polygon = box(minx - buffer_value, miny - buffer_value, maxx + buffer_value, maxy + buffer_value)
    domain_gdf = gpd.GeoDataFrame(
        {"tipo": ["dominio"]},
        geometry=[polygon],
        crs=gdf.crs,
    )

    domain_shp.parent.mkdir(parents=True, exist_ok=True)
    domain_gdf.to_file(domain_shp, driver="ESRI Shapefile", encoding="UTF-8")

    return domain_gdf


def _copy_excel_to_case(excel_path: Path, destino: Path) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(excel_path.read_bytes())
    return destino


def import_folder_from_input_path(input_path: str) -> dict[str, str]:
    case_root = Path(input_path).resolve()
    if not case_root.exists() or not case_root.is_dir():
        raise HTTPException(status_code=400, detail=f"La ruta de entrada no es una carpeta válida: {input_path}")

    paths = _ensure_case_dirs(case_root)
    case_name = case_root.name

    excel_path = _find_support_excel(case_root)
    trace_shp = _find_trace_shapefile(case_root)

    target_excel = paths["apoyos"] / f"Apoyos {case_name}.xlsx"
    _copy_excel_to_case(excel_path, target_excel)

    apoyos_shp = paths["apoyos"] / f"Apoyos {case_name}.shp"
    gdf_supports = _load_support_dataframe(target_excel)
    x_col, y_col = _infer_coordinate_columns(gdf_supports)
    support_gdf = _write_supports_shapefile(gdf_supports, x_col, y_col, apoyos_shp)

    generic_apoyos_shp = paths["apoyos"] / "apoyos.shp"
    _copy_shapefile_components(apoyos_shp, generic_apoyos_shp)
    _write_geojson(support_gdf, paths["apoyos"] / "apoyos.geojson")

    target_trace_shp = paths["shp"] / "traza.shp"
    _copy_shapefile_components(trace_shp, target_trace_shp)

    root_trace_shp = case_root / f"{case_name}.shp"
    _copy_shapefile_components(trace_shp, root_trace_shp)

    domain_shp = paths["shp"] / "dominio.shp"
    domain_gdf = _create_domain_from_trace(target_trace_shp, domain_shp)
    _write_geojson(domain_gdf, paths["shp"] / "dominio.geojson")

    return {
        "case_path": str(case_root),
        "status": "ready",
    }
