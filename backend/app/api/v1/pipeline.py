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
        result = run_geometry_and_dem(cfg)

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