from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, model_validator
from typing import Dict, List, Optional, Tuple
import hashlib
import random

from app.services.dashboard.weather_dashboard_service import DashboardDataError, WeatherDashboardService

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])
service = WeatherDashboardService()


class MeteoRequest(BaseModel):
    year: int
    domain_id: Optional[str] = None
    geometry: Optional[Dict] = None
    bbox: Optional[Tuple[float, float, float, float]] = None
    case_path: Optional[str] = None

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


def build_domain_seed(request: MeteoRequest) -> int:
    domain_key = (
        request.domain_id
        or request.case_path
        or str(request.bbox)
        or str(request.geometry)
    )
    raw = f"{request.year}|{domain_key}".encode("utf-8")
    return int(hashlib.sha256(raw).hexdigest()[:16], 16)


@router.post("/meteo-summary", response_model=MeteoSummary)
async def get_meteo_summary(request: MeteoRequest):
    """Obtiene el resumen meteorológico para un año específico."""
    try:
        return MeteoSummary(**service.get_meteo_summary(request.year, request))
    except DashboardDataError as exc:
        raise HTTPException(status_code=exc.http_status, detail={"error_code": exc.error_code, "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/wind-timeseries", response_model=List[WindTimeseries])
async def get_wind_timeseries(request: MeteoRequest):
    """Obtiene las series temporales mensuales de viento."""
    try:
        result = service.get_wind_timeseries(request.year, request)
        return [WindTimeseries(**item, source=result["source"], request_id=result["request_id"], domain_bbox=result["domain_bbox"], time_range=result["time_range"], crs=result["crs"], status=result["status"]) for item in result["items"]]
    except DashboardDataError as exc:
        raise HTTPException(status_code=exc.http_status, detail={"error_code": exc.error_code, "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/wind-rose", response_model=List[WindRoseData])
async def get_wind_rose(request: MeteoRequest):
    """Obtiene los datos de rosa de vientos (16 direcciones)."""
    try:
        result = service.get_wind_rose(request.year, request)
        return [WindRoseData(**item, source=result["source"], request_id=result["request_id"], domain_bbox=result["domain_bbox"], time_range=result["time_range"], crs=result["crs"], status=result["status"]) for item in result["items"]]
    except DashboardDataError as exc:
        raise HTTPException(status_code=exc.http_status, detail={"error_code": exc.error_code, "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
