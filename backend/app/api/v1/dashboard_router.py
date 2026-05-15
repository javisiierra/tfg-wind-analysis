from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, model_validator
from typing import Any, Dict, List, Literal, Optional, Tuple
import logging

from app.services.dashboard.weather_dashboard_service import DashboardDataError, WeatherDashboardService
from app.services.dashboard.job_store import DashboardJobStore

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])
service = WeatherDashboardService()
job_store = DashboardJobStore()
logger = logging.getLogger(__name__)


class MeteoRequest(BaseModel):
    year: int
    domain_id: Optional[str] = None
    geometry: Optional[Dict] = None
    bbox: Optional[Tuple[float, float, float, float]] = None
    case_path: Optional[str] = None
    source: Optional[str] = None

    @model_validator(mode="after")
    def validate_domain(self):
        if self.year < 2000 or self.year > 2099:
            raise ValueError("Year must be a valid year (2000-2099)")

        domain_fields = [
            bool(self.domain_id and self.domain_id.strip()),
            self.geometry is not None,
            self.bbox is not None,
            bool(self.case_path and self.case_path.strip()),
        ]
        if sum(domain_fields) != 1:
            raise ValueError("Provide exactly one geographic domain identifier: domain_id, geometry, bbox or case_path")

        if self.bbox is not None:
            min_lon, min_lat, max_lon, max_lat = self.bbox
            if min_lon >= max_lon or min_lat >= max_lat:
                raise ValueError("Invalid bbox: expected min < max")
        return self


class MeteoSummary(BaseModel):
    year: int
    avg_velocity: float
    max_velocity: float
    dominant_direction: float
    windiest_month: int
    viability_index: float
    data_points: int
    source: str
    request_id: str
    domain_bbox: Optional[Tuple[float, float, float, float]] = None
    time_range: Dict[str, str]
    crs: str
    status: str


class WindTimeseries(BaseModel):
    month: int
    avg_velocity: float
    max_velocity: float
    min_velocity: float
    frequency: Dict[str, float]
    source: str
    request_id: str
    domain_bbox: Optional[Tuple[float, float, float, float]] = None
    time_range: Dict[str, str]
    crs: str
    status: str


class WindRoseData(BaseModel):
    direction: str
    frequency: float
    velocity_range: Dict[str, float]
    source: str
    request_id: str
    domain_bbox: Optional[Tuple[float, float, float, float]] = None
    time_range: Dict[str, str]
    crs: str
    status: str


class StartJobResponse(BaseModel):
    job_id: str
    status: Literal["queued"]


class DashboardJobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "running", "finished", "failed"]
    progress: int
    message: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


def _run_dashboard_job(job_id: str, request: MeteoRequest) -> None:
    try:
        job_store.update(job_id, status="running", progress=15, message="Resolviendo dominio/bbox...")
        result = service.get_dashboard_bundle(
            year=request.year,
            domain=request,
            progress_cb=lambda progress, message: job_store.update(job_id, status="running", progress=progress, message=message),
        )
        job_store.update(job_id, status="finished", progress=100, message="Análisis completado", result=result, error=None)
    except DashboardDataError as exc:
        logger.exception("Dashboard async job failed", extra={"job_id": job_id})
        job_store.update(job_id, status="failed", progress=100, message="No se pudo completar el análisis.", error=str(exc), result=None)
    except Exception as exc:
        logger.exception("Unexpected dashboard async job failure", extra={"job_id": job_id})
        job_store.update(job_id, status="failed", progress=100, message="Fallo inesperado durante el análisis.", error="Error interno al procesar datos ERA5.", result=None)


@router.post("/meteo-summary/start", response_model=StartJobResponse)
async def start_meteo_summary_job(request: MeteoRequest):
    job_id = job_store.create(message="Job creado", progress=5)
    job_store.start_background(job_id, _run_dashboard_job, request)
    return StartJobResponse(job_id=job_id, status="queued")


@router.get("/meteo-summary/status/{job_id}", response_model=DashboardJobStatus)
async def get_meteo_summary_job_status(job_id: str):
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job_id no encontrado")
    return DashboardJobStatus(**job)


@router.post("/meteo-summary", response_model=MeteoSummary)
async def get_meteo_summary(request: MeteoRequest):
    try:
        return MeteoSummary(**service.get_meteo_summary(request.year, request))
    except DashboardDataError as exc:
        raise HTTPException(status_code=exc.http_status, detail={"error_code": exc.error_code, "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/wind-timeseries", response_model=List[WindTimeseries])
async def get_wind_timeseries(request: MeteoRequest):
    try:
        result = service.get_wind_timeseries(request.year, request)
        return [WindTimeseries(**item, source=result["source"], request_id=result["request_id"], domain_bbox=result["domain_bbox"], time_range=result["time_range"], crs=result["crs"], status=result["status"]) for item in result["items"]]
    except DashboardDataError as exc:
        raise HTTPException(status_code=exc.http_status, detail={"error_code": exc.error_code, "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/wind-rose", response_model=List[WindRoseData])
async def get_wind_rose(request: MeteoRequest):
    try:
        result = service.get_wind_rose(request.year, request)
        return [WindRoseData(**item, source=result["source"], request_id=result["request_id"], domain_bbox=result["domain_bbox"], time_range=result["time_range"], crs=result["crs"], status=result["status"]) for item in result["items"]]
    except DashboardDataError as exc:
        raise HTTPException(status_code=exc.http_status, detail={"error_code": exc.error_code, "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
