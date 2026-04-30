import json
import traceback
from pathlib import Path
from typing import Any
import numpy as np

import geopandas as gpd
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from shapely.geometry import shape, LineString, box

from app.core.config import load_config_from_case
from app.services.case_import.import_folder_service import import_folder_from_input_path
from app.scripts.run_local_pipeline import (
    run_generate_scenarios,
    run_geometry_and_dem,
    run_line_profile,
    run_towers,
)

router = APIRouter()

BASE_ROOT = Path(r"C:\Datos_TFG")


# ============================================================
# Modelos
# ============================================================

class PipelineRequest(BaseModel):
    case_path: str


class DomainFromSupportsRequest(BaseModel):
    case_path: str
    buffer_m: float | None = None


class SupportCreateRequest(BaseModel):
    case_path: str | None = None
    case_name: str | None = None
    geometry: dict[str, Any]
    epsg: int = 4326


class FolderImportRequest(BaseModel):
    input_path: str


# ============================================================
# Utilidades
# ============================================================

def load_cfg_from_case_or_raise(case_path: str):
    base = Path(case_path)

    if not base.exists():
        raise HTTPException(status_code=404, detail=f"No existe la carpeta del caso: {case_path}")

    if not base.is_dir():
        raise HTTPException(status_code=400, detail=f"La ruta no es una carpeta: {case_path}")

    try:
        return load_config_from_case(base)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"No se pudo construir la configuración automáticamente: {e}",
        )


def create_case_structure(base_root: Path, case_name: str) -> dict[str, Path]:
    case_path = base_root / case_name

    folders = {
        "case": case_path,
        "shp": case_path / "SHP",
        "calculos": case_path / "Calculos",
        "mdt": case_path / "MDT_WN",
        "weather": case_path / "Weather_Input_Data",
        "apoyos": case_path / "Apoyos",
        "out_wn": case_path / "OUT_WN",
        "out_wn_ren": case_path / "OUT_WN_REN",
        "wr": case_path / "WR",
    }

    for folder in folders.values():
        folder.mkdir(parents=True, exist_ok=True)

    return folders


def get_or_create_case_structure(case_name: str) -> dict[str, Path]:
    return create_case_structure(BASE_ROOT, case_name)


def shapefile_to_geojson_response(shp_path: Path, layer_name: str):
    if not shp_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No existe el shapefile de {layer_name}: {shp_path}",
        )

    try:
        gdf = gpd.read_file(shp_path)

        if gdf.empty:
            raise HTTPException(
                status_code=404,
                detail=f"El shapefile de {layer_name} está vacío: {shp_path}",
            )

        if gdf.crs is None:
            gdf = gdf.set_crs(epsg=25830)

        gdf = gdf.to_crs(epsg=4326)

        return JSONResponse(content=json.loads(gdf.to_json()))

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"No se pudo leer el shapefile de {layer_name}: {e}",
        )


def geojson_file_to_geojson_response(geojson_path: Path, layer_name: str):
    if not geojson_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No existe el GeoJSON de {layer_name}: {geojson_path}",
        )

    try:
        return JSONResponse(content=json.loads(geojson_path.read_text(encoding="utf-8")))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"No se pudo leer el GeoJSON de {layer_name}: {e}",
        )


def get_existing_path(*paths: Path) -> Path | None:
    for path in paths:
        if path and path.exists():
            return path
    return None


def get_existing_domain_path(case_path: str) -> Path | None:
    case_root = Path(case_path)
    cfg = load_cfg_from_case_or_raise(case_path)

    return get_existing_path(
        Path(cfg.in_shp) if cfg.in_shp else None,
        case_root / "SHP" / "dominio.shp",
        case_root / "SHP" / "dominio.geojson",
    )


def get_trace_shapefile_path(case_path: str) -> Path | None:
    trace_path = Path(case_path) / "SHP" / "traza.shp"
    return trace_path if trace_path.exists() else None


def get_supports_shapefile_path(case_path: str) -> Path | None:
    cfg = load_cfg_from_case_or_raise(case_path)
    return get_existing_path(
        Path(cfg.out_apoyos_shp) if cfg.out_apoyos_shp else None,
        Path(case_path) / "Apoyos" / "apoyos.shp",
    )


def _create_domain_from_trace_shp(case_path: str, trace_shp: Path, buffer_m: float | None = None) -> dict[str, str]:
    if not trace_shp.exists():
        raise HTTPException(status_code=404, detail=f"No existe el shapefile de traza: {trace_shp}")

    gdf = gpd.read_file(trace_shp)
    if gdf.empty:
        raise HTTPException(status_code=400, detail=f"El shapefile de traza está vacío: {trace_shp}")

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

    buffer_value = buffer_m if buffer_m is not None else max(100.0, max(maxx - minx, maxy - miny) * 0.05)
    domain_geom = box(minx - buffer_value, miny - buffer_value, maxx + buffer_value, maxy + buffer_value)

    domain_gdf = gpd.GeoDataFrame(
        {"source": ["generated_from_trace"], "buffer_m": [buffer_value]},
        geometry=[domain_geom],
        crs=gdf.crs,
    )

    shp_dir = Path(case_path) / "SHP"
    shp_dir.mkdir(parents=True, exist_ok=True)

    domain_shp_path = shp_dir / "dominio.shp"
    domain_geojson_path = shp_dir / "dominio.geojson"

    domain_gdf.to_file(domain_shp_path)
    domain_geojson_path.write_text(domain_gdf.to_crs(epsg=4326).to_json(), encoding="utf-8")

    return {
        "domain_shp": str(domain_shp_path),
        "domain_geojson": str(domain_geojson_path),
        "source": "trace",
        "buffer_m": buffer_value,
    }


def _generate_domain_from_supports_logic(case_path: str, buffer_m: float | None = None) -> dict[str, str]:
    supports_path = get_supports_shapefile_path(case_path)

    if supports_path is None:
        raise HTTPException(
            status_code=400,
            detail="No existen apoyos para generar el dominio.",
        )

    supports_gdf = gpd.read_file(supports_path)
    if supports_gdf.empty:
        raise HTTPException(status_code=400, detail="La capa de apoyos está vacía.")

    if supports_gdf.crs is None:
        supports_gdf = supports_gdf.set_crs(epsg=25830)

    supports_utm = supports_gdf.to_crs(epsg=25830)
    if "support_order" in supports_utm.columns:
        supports_utm = supports_utm.sort_values("support_order")

    coords = [
        (geom.x, geom.y)
        for geom in supports_utm.geometry
        if geom is not None and geom.geom_type == "Point"
    ]

    if len(coords) < 2:
        raise HTTPException(
            status_code=400,
            detail="Se necesitan al menos 2 apoyos para generar el dominio.",
        )

    line = LineString(coords)
    distances = [
        ((coords[i + 1][0] - coords[i][0]) ** 2 + (coords[i + 1][1] - coords[i][1]) ** 2) ** 0.5
        for i in range(len(coords) - 1)
    ]
    mean_span_m = sum(distances) / len(distances)

    computed_buffer = buffer_m if buffer_m is not None else max(mean_span_m * 2, 200)
    if computed_buffer <= 0:
        raise HTTPException(
            status_code=400,
            detail="El buffer debe ser mayor que 0 metros.",
        )

    domain_geometry = line.buffer(computed_buffer)
    domain_gdf = gpd.GeoDataFrame(
        [
            {
                "source": "generated_from_supports",
                "buffer_m": computed_buffer,
                "mean_span_m": mean_span_m,
                "n_supports": len(coords),
                "geometry": domain_geometry,
            }
        ],
        geometry="geometry",
        crs="EPSG:25830",
    )

    shp_dir = Path(case_path) / "SHP"
    shp_dir.mkdir(parents=True, exist_ok=True)

    domain_shp_path = shp_dir / "dominio.shp"
    domain_geojson_path = shp_dir / "dominio.geojson"

    domain_gdf.to_file(domain_shp_path)
    domain_geojson_path.write_text(domain_gdf.to_crs(epsg=4326).to_json(), encoding="utf-8")

    return {
        "domain_shp": str(domain_shp_path),
        "domain_geojson": str(domain_geojson_path),
        "source": "supports",
        "buffer_m": computed_buffer,
        "mean_span_m": mean_span_m,
        "n_supports": len(coords),
    }


def _generate_weather_for_cfg(cfg):
    import pandas as pd
    import traceback

    from app.services.scenarios.generate_scenarios_service import generate_windninja_input_csv
    from app.services.weather.weather_point_selector_service import select_weather_points

    weather_dir = Path(cfg.general_path) / "Weather_Input_Data"
    weather_dir.mkdir(parents=True, exist_ok=True)

    station_list_file = weather_dir / "WN_PointInit_Path.csv"
    points = select_weather_points(cfg)

    station_filenames = []
    station_full_paths = []
    for idx, point in enumerate(points, start=1):
        station_csv_file = weather_dir / f"WN_input_Point_{idx}.csv"

        generate_windninja_input_csv(
            cfg=cfg,
            station_name=point["name"],
            projection="PROJCS",
            utm_x=point["utm_x"],
            utm_y=point["utm_y"],
            height=cfg.height,
            temperature=cfg.temperature,
            n_directions=cfg.n_directions,
            wind_speeds=[1],
            output_csv=station_csv_file,
            start_datetime_utc="2025-01-01T00:00:00Z",
            dt_minutes=15,
            ordering="speed_then_dir",
        )

        if not station_csv_file.exists():
            raise FileNotFoundError(
                f"Fallo al generar el CSV de estación: {station_csv_file}"
            )
        station_filenames.append(station_csv_file.name)
        station_full_paths.append(station_csv_file.resolve())

    station_list_file.write_text(
        "Station_File_List,\n" + "\n".join(station_filenames) + "\n",
        encoding="utf-8",
    )

    print("Generado WN_PointInit_Path.csv:", station_list_file)
    print("Contenido:")
    for fn in station_filenames:
        print("  ", fn)
    print("Validación de archivos:")
    for station_path in station_full_paths:
        exists = station_path.exists()
        print(f"  {station_path} -> exists: {exists}")
        if not exists:
            raise FileNotFoundError(f"El archivo no existe: {station_path}")

    return {
        "points": points,
        "station_list_file": str(station_list_file),
        "station_files": [str(p) for p in station_full_paths],
    }


# ============================================================
# Sistema
# ============================================================

@router.get(
    "/health",
    tags=["Sistema"],
    summary="Health check",
    description="Comprueba que la API está funcionando correctamente.",
)
def health():
    return {"status": "ok"}


# ============================================================
# Apoyos
# ============================================================

@router.post(
    "/supports/generate-vanos",
    tags=["Apoyos"],
    summary="Generar vanos desde apoyos",
    description="Genera automáticamente los vanos (líneas entre apoyos consecutivos).",
)
def generate_vanos_from_supports(request: PipelineRequest):
    try:
        case_path = Path(request.case_path)

        supports_path = get_supports_shapefile_path(request.case_path)

        if supports_path is None or not supports_path.exists():
            raise HTTPException(
                status_code=400,
                detail="No existen apoyos para generar vanos.",
            )

        gdf = gpd.read_file(supports_path)

        if gdf.empty:
            raise HTTPException(
                status_code=400,
                detail="El shapefile de apoyos está vacío.",
            )

        if gdf.crs is None:
            gdf = gdf.set_crs(epsg=25830)

        gdf = gdf.to_crs(epsg=25830)

        if "sup_order" in gdf.columns:
            gdf = gdf.sort_values("sup_order")
        elif "support_order" in gdf.columns:
            gdf = gdf.sort_values("support_order")
        elif "support_or" in gdf.columns:
            gdf = gdf.sort_values("support_or")

        points = [
            geom for geom in gdf.geometry
            if geom is not None and geom.geom_type == "Point"
        ]

        if len(points) < 2:
            raise HTTPException(
                status_code=400,
                detail="Se necesitan al menos 2 apoyos para generar vanos.",
            )

        records = []

        for i in range(len(points) - 1):
            p1 = points[i]
            p2 = points[i + 1]

            dx = p2.x - p1.x
            dy = p2.y - p1.y

            direccion = (np.degrees(np.arctan2(dx, dy)) + 360.0) % 360.0

            records.append({
                "id": f"V-{i+1}",
                "from_ap": f"AP-{i+1}",
                "to_ap": f"AP-{i+2}",
                "direccion": float(direccion),
                "geometry": LineString([p1, p2]),
            })

        vanos_gdf = gpd.GeoDataFrame(
            records,
            geometry="geometry",
            crs="EPSG:25830",
        )

        out_path = case_path / "Calculos" / f"{case_path.name}_vanos.shp"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # limpiar shapefile previo
        for ext in [".shp", ".shx", ".dbf", ".prj", ".cpg"]:
            p = out_path.with_suffix(ext)
            if p.exists():
                p.unlink()

        vanos_gdf.to_file(out_path, driver="ESRI Shapefile", encoding="UTF-8")

        return {
            "status": "ok",
            "case_path": request.case_path,
            "vanos_shp": str(out_path),
            "n_vanos": len(vanos_gdf),
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        raise HTTPException(
            status_code=500,
            detail={
                "message": f"Error generando vanos: {e}",
                "traceback": traceback.format_exc(),
            },
        )

@router.post(
    "/supports/create",
    tags=["Apoyos"],
    summary="Crear apoyo",
    description="Añade un nuevo apoyo manual dibujado desde el mapa al caso.",
)
def create_support(request: SupportCreateRequest):
    try:
        if request.case_path:
            case_path = Path(request.case_path)
        elif request.case_name:
            case_path = BASE_ROOT / request.case_name
        else:
            raise HTTPException(status_code=400, detail="Debe indicarse case_path o case_name.")

        apoyos_dir = case_path / "Apoyos"
        apoyos_dir.mkdir(parents=True, exist_ok=True)

        supports_geojson_path = apoyos_dir / "apoyos.geojson"
        supports_shp_path = apoyos_dir / "apoyos.shp"

        if request.geometry.get("type") != "Point":
            raise HTTPException(status_code=400, detail="La geometría del apoyo debe ser de tipo Point.")

        new_geom = shape(request.geometry)

        if supports_shp_path.exists():
            old_gdf = gpd.read_file(supports_shp_path)

            if old_gdf.crs is None:
                old_gdf = old_gdf.set_crs(epsg=25830)

            old_gdf = old_gdf.to_crs(epsg=25830)
            old_gdf = old_gdf.rename(columns={
                "support_order": "sup_order",
                "support_or": "sup_order",
                "support_total": "sup_total",
                "support_to": "sup_total",
            })

            if "sup_order" in old_gdf.columns:
                old_gdf = old_gdf.sort_values("sup_order")
                next_order = int(old_gdf["sup_order"].max()) + 1
            else:
                next_order = len(old_gdf) + 1
        else:
            old_gdf = None
            next_order = 1

        support_id = f"AP-{next_order}"

        new_gdf = gpd.GeoDataFrame(
            [{
                "id": support_id,
                "sup_order": next_order,
                "case_name": case_path.name,
                "source": "drawn_in_web",
                "epsg": 25830,
                "sup_total": next_order,
                "geometry": new_geom,
            }],
            geometry="geometry",
            crs=f"EPSG:{request.epsg}",
        ).to_crs(epsg=25830)

        if old_gdf is not None and not old_gdf.empty:
            import pandas as pd

            gdf = pd.concat([old_gdf, new_gdf], ignore_index=True)
            gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs="EPSG:25830")
        else:
            gdf = new_gdf

        gdf = gdf.sort_values("sup_order")

        support_total = len(gdf)
        gdf["sup_total"] = support_total
        gdf["epsg"] = 25830

        keep_columns = [
            "id",
            "sup_order",
            "case_name",
            "source",
            "epsg",
            "sup_total",
            "geometry",
        ]
        gdf = gdf[[c for c in keep_columns if c in gdf.columns]]

        for ext in [".shp", ".shx", ".dbf", ".prj", ".cpg"]:
            p = supports_shp_path.with_suffix(ext)
            if p.exists():
                p.unlink()

        gdf.to_file(
            supports_shp_path,
            driver="ESRI Shapefile",
            encoding="UTF-8",
        )

        gdf.to_crs(epsg=4326).to_file(
            supports_geojson_path,
            driver="GeoJSON",
        )

        # Generar vanos/línea entre apoyos consecutivos
        vanos_path = case_path / "Calculos" / f"{case_path.name}_vanos.shp"
        vanos_path.parent.mkdir(parents=True, exist_ok=True)

        points = [
            geom
            for geom in gdf.geometry
            if geom is not None and geom.geom_type == "Point"
        ]

        if len(points) >= 2:
            records = []

            for i in range(len(points) - 1):
                p1 = points[i]
                p2 = points[i + 1]

                dx = p2.x - p1.x
                dy = p2.y - p1.y
                direccion = (np.degrees(np.arctan2(dx, dy)) + 360.0) % 360.0

                records.append({
                    "id": f"V-{i + 1}",
                    "from_ap": f"AP-{i + 1}",
                    "to_ap": f"AP-{i + 2}",
                    "direccion": float(direccion),
                    "geometry": LineString([p1, p2]),
                })

            vanos_gdf = gpd.GeoDataFrame(
                records,
                geometry="geometry",
                crs="EPSG:25830",
            )

            for ext in [".shp", ".shx", ".dbf", ".prj", ".cpg"]:
                p = vanos_path.with_suffix(ext)
                if p.exists():
                    p.unlink()

            vanos_gdf.to_file(
                vanos_path,
                driver="ESRI Shapefile",
                encoding="UTF-8",
            )

        print("Guardado apoyo:", support_id)
        print("Total apoyos:", support_total)
        print("Ruta apoyos:", supports_shp_path)
        print("Ruta vanos:", vanos_path)

        return {
            "status": "ok",
            "case_name": case_path.name,
            "case_path": str(case_path),
            "support_id": support_id,
            "support_total": support_total,
            "supports_geojson": str(supports_geojson_path),
            "supports_shp": str(supports_shp_path),
            "vanos_shp": str(vanos_path),
            "n_vanos": max(0, support_total - 1),
        }

    except HTTPException:
        raise

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(tb)
        raise HTTPException(
            status_code=500,
            detail={
                "message": f"No se pudo guardar el apoyo: {e}",
                "traceback": tb,
            },
        )
# ============================================================
# Dominio
# ============================================================

@router.post(
    "/domain/generate-from-supports",
    tags=["Dominio"],
    summary="Generar dominio desde apoyos",
    description=(
        "Genera automáticamente un dominio de simulación a partir de la línea "
        "formada por los apoyos. Si no se indica buffer_m, se calcula de forma automática."
    ),
)
def generate_domain_from_supports(request: DomainFromSupportsRequest):
    try:
        supports_path = get_supports_shapefile_path(request.case_path)

        print("case_path:", request.case_path)
        print("supports_path:", supports_path)
        print("exists:", supports_path.exists())

        result = _generate_domain_from_supports_logic(
            request.case_path,
            buffer_m=request.buffer_m,
        )

        return {
            "status": "ok",
            "case_path": request.case_path,
            "supports_file": str(supports_path),
            **result,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"No se pudo generar el dominio desde apoyos: {e}",
        )


@router.post(
    "/domain/generate-dem",
    tags=["Dominio"],
    summary="Generar DEM",
    description="Genera el Modelo Digital de Elevaciones a partir del dominio.",
)
def generate_dem_from_domain(request: PipelineRequest):
    cfg = load_cfg_from_case_or_raise(request.case_path)
    case_path = Path(request.case_path)

    domain_path = case_path / "SHP" / "dominio.shp"
    if domain_path.exists() and (cfg.in_shp is None or Path(cfg.in_shp).resolve() != domain_path.resolve()):
        cfg.in_shp = domain_path

    if cfg.in_shp is None or not Path(cfg.in_shp).exists():
        raise HTTPException(
            status_code=400,
            detail="No existe geometría de dominio para generar el DEM.",
        )

    # Asegurar carpetas necesarias para la ruta de salida
    for required in [case_path / "Calculos", case_path / "MDT_WN", case_path / "SHP"]:
        required.mkdir(parents=True, exist_ok=True)

    for path in [cfg.out_shp, cfg.out_rec_shp, cfg.out_rec_exp_shp, cfg.out_mdt_tif]:
        if path is not None:
            Path(path).parent.mkdir(parents=True, exist_ok=True)

    # Si dominio existe sin CRS, asignarlo explícitamente.
    if domain_path.exists():
        try:
            gdf = gpd.read_file(domain_path)
            if gdf.crs is None:
                gdf = gdf.set_crs(epsg=25830)
                gdf.to_file(domain_path)
        except Exception:
            pass

    debug_info = {
        "request.case_path": request.case_path,
        "cfg.general_path": str(cfg.general_path),
        "cfg.in_shp": str(cfg.in_shp) if cfg.in_shp else None,
        "cfg.out_shp": str(cfg.out_shp) if cfg.out_shp else None,
        "cfg.out_rec_shp": str(cfg.out_rec_shp) if cfg.out_rec_shp else None,
        "cfg.out_rec_exp_shp": str(cfg.out_rec_exp_shp) if cfg.out_rec_exp_shp else None,
        "cfg.out_mdt_tif": str(cfg.out_mdt_tif) if cfg.out_mdt_tif else None,
        "exists_in_shp": Path(cfg.in_shp).exists() if cfg.in_shp else False,
        "exists_out_shp_parent": Path(cfg.out_shp).parent.exists() if cfg.out_shp else False,
        "exists_out_rec_shp_parent": Path(cfg.out_rec_shp).parent.exists() if cfg.out_rec_shp else False,
        "exists_out_rec_exp_shp_parent": Path(cfg.out_rec_exp_shp).parent.exists() if cfg.out_rec_exp_shp else False,
        "exists_out_mdt_tif_parent": Path(cfg.out_mdt_tif).parent.exists() if cfg.out_mdt_tif else False,
    }

    try:
        if cfg.in_shp is not None:
            source_gdf = gpd.read_file(cfg.in_shp)
            debug_info["in_shp_crs"] = str(source_gdf.crs)
            debug_info["in_shp_geom_types"] = list(set(source_gdf.geom_type))
            debug_info["in_shp_bounds"] = list(source_gdf.total_bounds)
        else:
            debug_info["in_shp_crs"] = None
            debug_info["in_shp_geom_types"] = None
            debug_info["in_shp_bounds"] = None

        run_geometry_and_dem(cfg)

        return {
            "status": "ok",
            "case_path": request.case_path,
            "domain_file": str(cfg.in_shp) if cfg.in_shp else None,
            "out_shp": str(cfg.out_shp) if cfg.out_shp else None,
            "out_rec_shp": str(cfg.out_rec_shp) if cfg.out_rec_shp else None,
            "out_rec_exp_shp": str(cfg.out_rec_exp_shp) if cfg.out_rec_exp_shp else None,
            "out_mdt_tif": str(cfg.out_mdt_tif) if cfg.out_mdt_tif else None,
            "debug": debug_info,
        }

    except HTTPException:
        raise
    except Exception as e:
        tb = traceback.format_exc()
        raise HTTPException(
            status_code=500,
            detail={
                "error": str(e),
                "traceback": tb,
                "debug": debug_info,
            },
        )


@router.post(
    "/domain/generate-weather",
    tags=["Dominio"],
    summary="Generar meteorología",
    description="Genera los ficheros de entrada de viento para WindNinja.",
)
def generate_weather_from_domain(request: PipelineRequest):
    import traceback
    
    cfg = load_cfg_from_case_or_raise(request.case_path)

    if cfg.in_shp is None or not Path(cfg.in_shp).exists():
        raise HTTPException(
            status_code=400,
            detail="No existe geometría de dominio para generar meteorología.",
        )

    try:
        weather_result = _generate_weather_for_cfg(cfg)
        return {
            "status": "ok",
            "case_path": request.case_path,
            **weather_result,
        }

    except HTTPException:
        raise
    except Exception as e:
        tb = traceback.format_exc()
        raise HTTPException(
            status_code=500,
            detail={
                "message": f"Error generando meteorología desde dominio: {str(e)}",
                "error_type": type(e).__name__,
                "traceback": tb,
            },
        )


@router.post(
    "/pipeline/run-preparation",
    tags=["Pipeline"],
    summary="Ejecutar preparación moderna",
    description=(
        "Genera dominio, DEM y meteorología para casos importados o con apoyos normalizados. "
        "No ejecuta towers ni line profile."
    ),
)
def run_preparation(request: PipelineRequest):
    cfg = load_cfg_from_case_or_raise(request.case_path)
    case_path = Path(request.case_path)

    domain_path = get_existing_domain_path(request.case_path)
    domain_info = {"generated": False}

    if domain_path is None:
        trace_path = get_trace_shapefile_path(request.case_path)
        if trace_path is not None:
            domain_info = _create_domain_from_trace_shp(request.case_path, trace_path)
        else:
            supports_path = get_supports_shapefile_path(request.case_path)
            if supports_path is not None:
                domain_info = _generate_domain_from_supports_logic(request.case_path)
            else:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "No existe dominio ni fuente para generarlo. "
                        "Se requiere SHP/traza.shp o Apoyos/apoyos.shp."
                    ),
                )

        cfg = load_cfg_from_case_or_raise(request.case_path)
        domain_path = get_existing_domain_path(request.case_path)

    if cfg.in_shp is None or not Path(cfg.in_shp).exists():
        raise HTTPException(
            status_code=400,
            detail="No se encontró el dominio después de la generación.",
        )

    dem_result = run_geometry_and_dem(cfg)
    weather_result = _generate_weather_for_cfg(cfg)

    return {
        "status": "ok",
        "case_path": request.case_path,
        "domain": {
            "path": str(domain_path) if domain_path else None,
            **domain_info,
        },
        "dem": {
            "out_shp": str(cfg.out_shp) if cfg.out_shp else None,
            "out_rec_shp": str(cfg.out_rec_shp) if cfg.out_rec_shp else None,
            "out_rec_exp_shp": str(cfg.out_rec_exp_shp) if cfg.out_rec_exp_shp else None,
            "out_mdt_tif": str(cfg.out_mdt_tif) if cfg.out_mdt_tif else None,
        },
        "weather": weather_result,
        "geometry_results": {
            "minx": dem_result.get("minx"),
            "miny": dem_result.get("miny"),
            "maxx": dem_result.get("maxx"),
            "maxy": dem_result.get("maxy"),
        },
    }


# ============================================================
# Pipeline
# ============================================================

@router.post(
    "/pipeline/run-base",
    tags=["Pipeline legacy"],
    summary="LEGACY - Ejecutar pipeline base antiguo",
    description="Flujo antiguo completo. No debe usarse en casos importados ni generados desde apoyos.",
)
def run_base_pipeline(request: PipelineRequest):
    cfg = load_cfg_from_case_or_raise(request.case_path)

    try:
        run_geometry_and_dem(cfg)

        # 👇 IMPORTANTE
        if cfg.out_apoyos_shp and Path(cfg.out_apoyos_shp).exists():
            # Ya existen apoyos → no ejecutar towers
            towers_result = "skipped"
        else:
            run_towers(cfg)
            towers_result = "executed"

        run_line_profile(cfg)
        run_generate_scenarios(cfg)

        return {
            "status": "ok",
            "mode": "legacy",
            "towers": towers_result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post(
    "/pipeline/run-windninja",
    tags=["Pipeline"],
    summary="Ejecutar WindNinja",
    description="Lanza la simulación de WindNinja con los datos preparados.",
)
def run_windninja_api(request: PipelineRequest):
    cfg = load_cfg_from_case_or_raise(request.case_path)

    if cfg.in_weather_file is None:
        raise HTTPException(
            status_code=400,
            detail="No existe archivo meteorológico WN_PointInit_Path.csv en el caso.",
        )

    if cfg.out_mdt_tif is None or not Path(cfg.out_mdt_tif).exists():
        raise HTTPException(
            status_code=400,
            detail="No existe MDT DEM necesario para WindNinja.",
        )

    try:
        from app.scripts.run_local_pipeline import run_windninja_stage

        result = run_windninja_stage(cfg)

        return {
            "status": "ok",
            "case_path": request.case_path,
            "summary": str(result.get("summary_txt_path")),
            "command": str(result.get("command_txt_path")),
            "stdout_tail": str(result.get("stdout_tail_txt_path")),
            "stderr_tail": str(result.get("stderr_tail_txt_path")),
            "new_files_txt": str(result.get("new_files_txt_path")),
            "n_new_files": len(result.get("new_files", [])),
            "returncode": result.get("returncode"),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error ejecutando WindNinja: {e}")


@router.post(
    "/pipeline/run-rename",
    tags=["Pipeline"],
    summary="Renombrar outputs",
    description="Renombra los outputs generados por WindNinja.",
)
def run_rename_api(request: PipelineRequest):
    cfg = load_cfg_from_case_or_raise(request.case_path)

    try:
        from app.scripts.run_local_pipeline import run_rename_stage

        result = run_rename_stage(cfg, apply=True)

        return {
            "status": "ok",
            "case_path": request.case_path,
            "apply": result.get("apply"),
            "summary": str(result.get("summary_txt_path")),
            "plan": str(result.get("plan_csv_path")),
            "diagnostics": str(result.get("diag_csv_path")),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error ejecutando rename: {e}")


@router.post(
    "/pipeline/run-wind-rose",
    tags=["Pipeline"],
    summary="Calcular rosa de vientos",
    description="Genera la rosa de vientos y ajuste Weibull.",
)
def run_wind_rose_api(request: PipelineRequest):
    cfg = load_cfg_from_case_or_raise(request.case_path)

    try:
        from app.scripts.run_local_pipeline import run_wind_rose_stage

        result = run_wind_rose_stage(cfg)

        return {
            "status": "ok",
            "case_path": request.case_path,
            "csv": str(result.get("out_csv_path")),
            "plot": str(result.get("out_plot_path")),
            "weibull": str(result.get("out_weibull_path")),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error ejecutando wind rose: {e}")


@router.post(
    "/case/import-folder",
    tags=["Case"],
    summary="Importar carpeta de entrada del cliente",
    description=(
        "Adapta una carpeta de entrada simplificada a la estructura esperada por el pipeline, "
        "incluyendo SHP/, Apoyos/, dominio.shp y archivos de trazado."
    ),
)
def import_folder_api(request: FolderImportRequest):
    try:
        return import_folder_from_input_path(request.input_path)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error importando carpeta: {e}")


# ============================================================
# Estado
# ============================================================

@router.post(
    "/case/status",
    tags=["Estado"],
    summary="Estado del caso",
    description="Devuelve el estado del caso: dominio, DEM, apoyos, vanos y meteorología.",
)
def get_case_status(request: PipelineRequest):
    cfg = load_cfg_from_case_or_raise(request.case_path)

    fallback_apoyos = Path(request.case_path) / "Apoyos" / "apoyos.shp"
    fallback_domain = Path(request.case_path) / "SHP" / "dominio.shp"

    has_domain = (
        cfg.in_shp is not None and Path(cfg.in_shp).exists()
    ) or fallback_domain.exists()

    has_dem = cfg.out_mdt_tif is not None and Path(cfg.out_mdt_tif).exists()
    has_weather = cfg.in_weather_file is not None and Path(cfg.in_weather_file).exists()

    has_apoyos = (
        cfg.out_apoyos_shp is not None and Path(cfg.out_apoyos_shp).exists()
    ) or fallback_apoyos.exists()

    has_vanos = cfg.out_vanos_shp is not None and Path(cfg.out_vanos_shp).exists()

    return {
        "status": "ok",
        "case_path": request.case_path,
        "has_domain": has_domain,
        "has_dem": has_dem,
        "has_weather": has_weather,
        "has_apoyos": has_apoyos,
        "has_vanos": has_vanos,
        "ready_for_windninja": has_domain and has_dem and has_weather and has_apoyos,
        "paths": {
            "domain": str(cfg.in_shp) if cfg.in_shp else str(fallback_domain),
            "dem": str(cfg.out_mdt_tif) if cfg.out_mdt_tif else None,
            "weather": str(cfg.in_weather_file) if cfg.in_weather_file else None,
            "apoyos": str(cfg.out_apoyos_shp) if cfg.out_apoyos_shp else str(fallback_apoyos),
            "vanos": str(cfg.out_vanos_shp) if cfg.out_vanos_shp else None,
        },
    }


# ============================================================
# Capas
# ============================================================

@router.post(
    "/layers/apoyos",
    tags=["Capas"],
    summary="Obtener apoyos",
    description="Devuelve la capa de apoyos en formato GeoJSON.",
)
def get_apoyos_layer(request: PipelineRequest):
    cfg = load_cfg_from_case_or_raise(request.case_path)

    shp_path = get_existing_path(
        Path(cfg.out_apoyos_shp) if cfg.out_apoyos_shp else None,
        Path(request.case_path) / "Apoyos" / "apoyos.shp",
    )

    if shp_path:
        return shapefile_to_geojson_response(shp_path, "apoyos")

    return geojson_file_to_geojson_response(
        Path(request.case_path) / "Apoyos" / "apoyos.geojson",
        "apoyos",
    )


@router.post(
    "/layers/vanos",
    tags=["Capas"],
    summary="Obtener vanos",
    description="Devuelve la capa de vanos en formato GeoJSON.",
)
def get_vanos_layer(request: PipelineRequest):
    cfg = load_cfg_from_case_or_raise(request.case_path)

    if cfg.out_vanos_shp is None:
        raise HTTPException(status_code=404, detail="No existe ruta configurada para vanos.")

    return shapefile_to_geojson_response(Path(cfg.out_vanos_shp), "vanos")


@router.post(
    "/layers/dominio",
    tags=["Capas"],
    summary="Obtener dominio",
    description="Devuelve la capa del dominio de simulación.",
)
def get_dominio_layer(request: PipelineRequest):
    cfg = load_cfg_from_case_or_raise(request.case_path)

    shp_path = get_existing_path(
        Path(cfg.out_rec_exp_shp) if cfg.out_rec_exp_shp else None,
        Path(cfg.in_shp) if cfg.in_shp else None,
        Path(request.case_path) / "SHP" / "dominio.shp",
    )

    if shp_path is None:
        return geojson_file_to_geojson_response(
            Path(request.case_path) / "SHP" / "dominio.geojson",
            "dominio",
        )

    return shapefile_to_geojson_response(shp_path, "dominio")


@router.post(
    "/layers/worst-supports",
    tags=["Capas"],
    summary="Obtener peores apoyos",
    description="Devuelve la capa de los apoyos más críticos.",
)
def get_worst_supports_layer(request: PipelineRequest):
    cfg = load_cfg_from_case_or_raise(request.case_path)

    if cfg.out_v_perp_min_shp is None:
        raise HTTPException(status_code=404, detail="No existe ruta configurada para peores apoyos.")

    return shapefile_to_geojson_response(Path(cfg.out_v_perp_min_shp), "worst_supports")


# ============================================================
# Análisis
# ============================================================

@router.post(
    "/analysis/worst-supports",
    tags=["Análisis"],
    summary="Calcular peores apoyos",
    description="Calcula los N apoyos más críticos según los resultados.",
)
def worst_supports_api(request: PipelineRequest, top_n: int = 4):
    cfg = load_cfg_from_case_or_raise(request.case_path)

    try:
        from app.services.analysis.worst_supports_service import compute_worst_supports

        result = compute_worst_supports(cfg, top_n=top_n)

        return {
            "status": "ok",
            "case_path": request.case_path,
            **result,
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback

        raise HTTPException(
            status_code=500,
            detail={
                "message": f"Error calculando los peores apoyos/vanos: {e}",
                "traceback": traceback.format_exc(),
            },
        )