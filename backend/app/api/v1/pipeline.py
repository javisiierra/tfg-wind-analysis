import json
from pathlib import Path
from typing import Any

import geopandas as gpd
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.config import load_config_from_case
from app.scripts.run_local_pipeline import (
    run_generate_scenarios,
    run_geometry_and_dem,
    run_line_profile,
    run_towers,
)

router = APIRouter()


class PipelineRequest(BaseModel):
    case_path: str


class DomainCreateRequest(BaseModel):
    case_name: str
    geometry: dict[str, Any]
    epsg: int = 4326


def load_cfg_from_case_or_raise(case_path: str):
    base = Path(case_path)

    if not base.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No existe la carpeta del caso: {case_path}",
        )

    if not base.is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"La ruta no es una carpeta: {case_path}",
        )

    try:
        return load_config_from_case(base)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"No se pudo construir la configuración automáticamente: {e}",
        )


def create_case_structure(base_root: Path, case_name: str) -> dict[str, Path]:
    case_path = base_root / case_name

    if case_path.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Ya existe un caso con ese nombre: {case_name}",
        )

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

        # Si no trae CRS, asumimos 25830 porque tus datos están en UTM ETRS89 zona 30
        if gdf.crs is None:
            gdf = gdf.set_crs(epsg=25830)

        # GeoJSON web -> WGS84
        gdf = gdf.to_crs(epsg=4326)

        return JSONResponse(content=json.loads(gdf.to_json()))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"No se pudo leer el shapefile de {layer_name}: {e}",
        )


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/domain/create")
def create_domain_case(request: DomainCreateRequest):
    base_root = Path(r"C:\Datos_TFG")

    try:
        folders = create_case_structure(base_root, request.case_name)

        domain_geojson_path = folders["shp"] / "dominio.geojson"

        feature_collection = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "case_name": request.case_name,
                        "source": "drawn_in_web",
                        "epsg": request.epsg,
                    },
                    "geometry": request.geometry,
                }
            ],
        }

        domain_geojson_path.write_text(
            json.dumps(feature_collection, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return {
            "status": "ok",
            "case_name": request.case_name,
            "case_path": str(folders["case"]),
            "domain_file": str(domain_geojson_path),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"No se pudo crear el caso: {e}",
        )


@router.post("/domain/generate-dem")
def generate_dem_from_domain(request: PipelineRequest):
    cfg = load_cfg_from_case_or_raise(request.case_path)

    if cfg.in_shp is None or not Path(cfg.in_shp).exists():
        raise HTTPException(
            status_code=400,
            detail="No existe geometría de dominio para generar el DEM",
        )

    try:
        run_geometry_and_dem(cfg)

        return {
            "status": "ok",
            "case_path": request.case_path,
            "domain_file": str(cfg.in_shp) if cfg.in_shp else None,
            "out_shp": str(cfg.out_shp) if cfg.out_shp else None,
            "out_rec_shp": str(cfg.out_rec_shp) if cfg.out_rec_shp else None,
            "out_rec_exp_shp": str(cfg.out_rec_exp_shp) if cfg.out_rec_exp_shp else None,
            "out_mdt_tif": str(cfg.out_mdt_tif) if cfg.out_mdt_tif else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error generando DEM desde dominio: {e}",
        )

@router.post("/domain/generate-weather")
def generate_weather_from_domain(request: PipelineRequest):
    cfg = load_cfg_from_case_or_raise(request.case_path)

    if cfg.in_shp is None or not Path(cfg.in_shp).exists():
        raise HTTPException(
            status_code=400,
            detail="No existe geometría de dominio para generar meteorología",
        )

    try:
        import pandas as pd

        from app.services.scenarios.generate_scenarios_service import generate_windninja_input_csv
        from app.services.weather.weather_point_selector_service import select_weather_points

        weather_dir = Path(cfg.general_path) / "Weather_Input_Data"
        weather_dir.mkdir(parents=True, exist_ok=True)

        station_list_file = weather_dir / "WN_PointInit_Path.csv"

        points = select_weather_points(cfg)

        station_files = []

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

            station_files.append(station_csv_file.name)

        pd.DataFrame({
            "Station_File_List": station_files
        }).to_csv(station_list_file, index=False)

        return {
            "status": "ok",
            "case_path": request.case_path,
            "points": points,
            "station_list_file": str(station_list_file),
            "station_files": [str(weather_dir / f) for f in station_files],
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error generando meteorología desde dominio: {e}",
        )


@router.post("/pipeline/run-base")
def run_base_pipeline(request: PipelineRequest):
    cfg = load_cfg_from_case_or_raise(request.case_path)

    try:
        run_geometry_and_dem(cfg)
        run_towers(cfg)
        run_line_profile(cfg)
        run_generate_scenarios(cfg)

        return {
            "status": "ok",
            "case_path": request.case_path,
            "outputs": {
                "geometry_dem": {
                    "out_shp": str(cfg.out_shp) if cfg.out_shp else None,
                    "out_rec_shp": str(cfg.out_rec_shp) if cfg.out_rec_shp else None,
                    "out_rec_exp_shp": str(cfg.out_rec_exp_shp) if cfg.out_rec_exp_shp else None,
                    "out_mdt_tif": str(cfg.out_mdt_tif) if cfg.out_mdt_tif else None,
                },
                "towers": {
                    "out_apoyos_shp": str(cfg.out_apoyos_shp) if cfg.out_apoyos_shp else None,
                    "out_vanos_shp": str(cfg.out_vanos_shp) if cfg.out_vanos_shp else None,
                },
                "line_profile": {
                    "out_perfil_file": str(cfg.out_perfil_file) if cfg.out_perfil_file else None,
                },
                "scenarios": {
                    "out_weather_point_file": str(cfg.out_weather_point_file) if cfg.out_weather_point_file else None,
                },
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error ejecutando pipeline base: {e}",
        )


@router.post("/pipeline/run-windninja")
def run_windninja_api(request: PipelineRequest):
    cfg = load_cfg_from_case_or_raise(request.case_path)

    if cfg.in_weather_file is None:
        raise HTTPException(
            status_code=400,
            detail="No existe archivo meteorológico (WN_PointInit_Path.csv) en el caso",
        )

    if cfg.out_mdt_tif is None or not Path(cfg.out_mdt_tif).exists():
        raise HTTPException(
            status_code=400,
            detail="No existe MDT (DEM) necesario para WindNinja",
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
        raise HTTPException(
            status_code=500,
            detail=f"Error ejecutando WindNinja: {e}",
        )


@router.post("/pipeline/run-rename")
def run_rename_api(request: PipelineRequest):
    cfg = load_cfg_from_case_or_raise(request.case_path)

    try:
        from app.scripts.run_local_pipeline import run_rename_stage

        result = run_rename_stage(cfg)

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
        raise HTTPException(
            status_code=500,
            detail=f"Error ejecutando rename: {e}",
        )


@router.post("/pipeline/run-wind-rose")
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
        raise HTTPException(
            status_code=500,
            detail=f"Error ejecutando wind rose: {e}",
        )
    
@router.post("/case/status")
def get_case_status(request: PipelineRequest):
    cfg = load_cfg_from_case_or_raise(request.case_path)

    has_domain = cfg.in_shp is not None and Path(cfg.in_shp).exists()
    has_dem = cfg.out_mdt_tif is not None and Path(cfg.out_mdt_tif).exists()
    has_weather = cfg.in_weather_file is not None and Path(cfg.in_weather_file).exists()
    has_apoyos = cfg.out_apoyos_shp is not None and Path(cfg.out_apoyos_shp).exists()
    has_vanos = cfg.out_vanos_shp is not None and Path(cfg.out_vanos_shp).exists()

    return {
        "status": "ok",
        "case_path": request.case_path,
        "has_domain": has_domain,
        "has_dem": has_dem,
        "has_weather": has_weather,
        "has_apoyos": has_apoyos,
        "has_vanos": has_vanos,
        "ready_for_windninja": has_domain and has_dem and has_weather,
        "paths": {
            "domain": str(cfg.in_shp) if cfg.in_shp else None,
            "dem": str(cfg.out_mdt_tif) if cfg.out_mdt_tif else None,
            "weather": str(cfg.in_weather_file) if cfg.in_weather_file else None,
            "apoyos": str(cfg.out_apoyos_shp) if cfg.out_apoyos_shp else None,
            "vanos": str(cfg.out_vanos_shp) if cfg.out_vanos_shp else None,
        }
    }


@router.post("/layers/apoyos")
def get_apoyos_layer(request: PipelineRequest):
    cfg = load_cfg_from_case_or_raise(request.case_path)
    shp_path = Path(cfg.out_apoyos_shp)
    return shapefile_to_geojson_response(shp_path, "apoyos")


@router.post("/layers/vanos")
def get_vanos_layer(request: PipelineRequest):
    cfg = load_cfg_from_case_or_raise(request.case_path)
    shp_path = Path(cfg.out_vanos_shp)
    return shapefile_to_geojson_response(shp_path, "vanos")


@router.post("/layers/dominio")
def get_dominio_layer(request: PipelineRequest):
    cfg = load_cfg_from_case_or_raise(request.case_path)
    shp_path = Path(cfg.out_rec_exp_shp)
    return shapefile_to_geojson_response(shp_path, "dominio")

@router.post("/layers/worst-supports")
def get_worst_supports_layer(request: PipelineRequest):
    cfg = load_cfg_from_case_or_raise(request.case_path)
    shp_path = Path(cfg.out_v_perp_min_shp)
    return shapefile_to_geojson_response(shp_path, "worst_supports")

@router.post("/analysis/worst-supports")
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
        raise HTTPException(
            status_code=500,
            detail=f"Error calculando los peores apoyos/vanos: {e}",
        )