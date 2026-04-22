import json
from pathlib import Path

import geopandas as gpd
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.config import load_config_toml
from app.scripts.run_local_pipeline import (
    run_generate_scenarios,
    run_geometry_and_dem,
    run_line_profile,
    run_towers,
)

router = APIRouter()


class PipelineRequest(BaseModel):
    case_path: str


def load_cfg_from_case_or_raise(case_path: str):
    normalized_case_path = case_path.strip().strip('"').strip("'")
    base = Path(normalized_case_path).expanduser()

    if not base.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No existe la carpeta del caso: {normalized_case_path}",
        )

    if not base.is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"La ruta no es una carpeta: {normalized_case_path}",
        )

    config_candidates = [
        base / "config.toml",
        base / "config",
    ]

    config_path = next((candidate for candidate in config_candidates if candidate.exists()), None)

    if config_path is None:
        available_names = sorted(p.name for p in base.iterdir() if p.is_file())
        raise HTTPException(
            status_code=404,
            detail={
                "message": "No existe config.toml/config dentro de la carpeta del caso.",
                "case_path": str(base),
                "available_files": available_names,
            },
        )

    try:
        return load_config_toml(config_path)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail={
                "message": f"No se pudo cargar el archivo de configuración: {config_path.name}",
                "error": str(e),
            },
        )


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