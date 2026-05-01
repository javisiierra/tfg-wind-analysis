from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, model_validator
from typing import Dict, List, Optional, Tuple
import hashlib
import random

from app.services.dashboard.weather_dashboard_service import WeatherDashboardService

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])
service = WeatherDashboardService()


class MeteoRequest(BaseModel):
    year: int
    domain_id: Optional[str] = None
    geometry: Optional[Dict] = None
    bbox: Optional[Tuple[float, float, float, float]] = None
    case_path: Optional[str] = None
    use_mock_fallback: bool = True

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


class WindTimeseries(BaseModel):
    month: int
    avg_velocity: float
    max_velocity: float
    min_velocity: float
    frequency: Dict[str, float]


class WindRoseData(BaseModel):
    direction: str
    frequency: float
    velocity_range: Dict[str, float]


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
        return MeteoSummary(**service.get_meteo_summary(request.year, case_path=request.case_path, fallback_to_mock=request.use_mock_fallback))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/wind-timeseries", response_model=List[WindTimeseries])
async def get_wind_timeseries(request: MeteoRequest):
    """Obtiene las series temporales mensuales de viento."""
    try:
        return [WindTimeseries(**item) for item in service.get_wind_timeseries(request.year, case_path=request.case_path, fallback_to_mock=request.use_mock_fallback)]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/wind-rose", response_model=List[WindRoseData])
async def get_wind_rose(request: MeteoRequest):
    """Obtiene los datos de rosa de vientos (16 direcciones)."""
    try:
        return [WindRoseData(**item) for item in service.get_wind_rose(request.year, case_path=request.case_path, fallback_to_mock=request.use_mock_fallback)]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
