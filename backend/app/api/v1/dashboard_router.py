from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, List

from app.services.dashboard.weather_dashboard_service import WeatherDashboardService

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])
service = WeatherDashboardService()


class MeteoRequest(BaseModel):
    year: int


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


@router.post("/meteo-summary", response_model=MeteoSummary)
async def get_meteo_summary(request: MeteoRequest):
    """Obtiene el resumen meteorológico para un año específico."""
    try:
        return MeteoSummary(**service.get_meteo_summary(request.year))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/wind-timeseries", response_model=List[WindTimeseries])
async def get_wind_timeseries(request: MeteoRequest):
    """Obtiene las series temporales mensuales de viento."""
    try:
        return [WindTimeseries(**item) for item in service.get_wind_timeseries(request.year)]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/wind-rose", response_model=List[WindRoseData])
async def get_wind_rose(request: MeteoRequest):
    """Obtiene los datos de rosa de vientos (16 direcciones)."""
    try:
        return [WindRoseData(**item) for item in service.get_wind_rose(request.year)]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
