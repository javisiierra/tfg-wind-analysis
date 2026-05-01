from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, List

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


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
    if not isinstance(request.year, int) or request.year < 2000 or request.year > 2099:
        raise HTTPException(status_code=400, detail="Year must be a valid year (2000-2099)")
    
    # TODO: Conectar con base de datos de datos meteorológicos
    # Por ahora retorna datos mock
    return MeteoSummary(
        year=request.year,
        avg_velocity=5.43,
        max_velocity=18.76,
        dominant_direction=245,
        windiest_month=7,
        viability_index=0.68,
        data_points=8760
    )


@router.post("/wind-timeseries", response_model=List[WindTimeseries])
async def get_wind_timeseries(request: MeteoRequest):
    """Obtiene las series temporales mensuales de viento."""
    if not isinstance(request.year, int) or request.year < 2000 or request.year > 2099:
        raise HTTPException(status_code=400, detail="Year must be a valid year (2000-2099)")
    
    # TODO: Conectar con base de datos de datos meteorológicos
    # Por ahora retorna datos mock para 12 meses
    months_data = []
    for month in range(1, 13):
        months_data.append(
            WindTimeseries(
                month=month,
                avg_velocity=4.23 + (month * 0.3),
                max_velocity=15.32 + (month * 0.5),
                min_velocity=0.12,
                frequency={
                    "0-2": 0.15,
                    "2-4": 0.30,
                    "4-6": 0.35,
                    "6-8": 0.15,
                    "8-10": 0.04,
                    "10+": 0.01
                }
            )
        )
    return months_data


@router.post("/wind-rose", response_model=List[WindRoseData])
async def get_wind_rose(request: MeteoRequest):
    """Obtiene los datos de rosa de vientos (16 direcciones)."""
    if not isinstance(request.year, int) or request.year < 2000 or request.year > 2099:
        raise HTTPException(status_code=400, detail="Year must be a valid year (2000-2099)")
    
    # TODO: Conectar con base de datos de datos meteorológicos
    # Por ahora retorna datos mock para 16 direcciones
    directions = [
        ("N", 0.08, 0.5, 3.2),
        ("NNE", 0.07, 0.4, 3.5),
        ("NE", 0.09, 0.6, 4.1),
        ("ENE", 0.08, 0.5, 3.8),
        ("E", 0.10, 0.7, 4.5),
        ("ESE", 0.09, 0.6, 4.2),
        ("SE", 0.08, 0.5, 3.9),
        ("SSE", 0.07, 0.4, 3.6),
        ("S", 0.06, 0.3, 3.3),
        ("SSW", 0.07, 0.4, 3.5),
        ("SW", 0.08, 0.5, 3.8),
        ("WSW", 0.09, 0.6, 4.1),
        ("W", 0.10, 0.7, 4.4),
        ("WNW", 0.09, 0.6, 4.0),
        ("NW", 0.08, 0.5, 3.7),
        ("NNW", 0.07, 0.4, 3.4),
    ]
    
    wind_rose = []
    for direction, frequency, min_vel, max_vel in directions:
        wind_rose.append(
            WindRoseData(
                direction=direction,
                frequency=frequency,
                velocity_range={"min": min_vel, "max": max_vel}
            )
        )
    return wind_rose
