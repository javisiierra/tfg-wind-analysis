from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, model_validator
from typing import Dict, List, Optional, Tuple
import hashlib
import random

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


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
        seed = build_domain_seed(request)
        rng = random.Random(seed)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return MeteoSummary(
        year=request.year,
        avg_velocity=round(rng.uniform(3.8, 8.2), 2),
        max_velocity=round(rng.uniform(12.5, 26.0), 2),
        dominant_direction=round(rng.uniform(0, 359), 1),
        windiest_month=rng.randint(1, 12),
        viability_index=round(rng.uniform(0.25, 0.88), 2),
        data_points=8760
    )


@router.post("/wind-timeseries", response_model=List[WindTimeseries])
async def get_wind_timeseries(request: MeteoRequest):
    """Obtiene las series temporales mensuales de viento."""
    seed = build_domain_seed(request)
    rng = random.Random(seed + 101)

    months_data = []
    for month in range(1, 13):
        avg_velocity = round(rng.uniform(3.0, 8.5) + month * 0.05, 2)
        max_velocity = round(avg_velocity + rng.uniform(5.0, 12.0), 2)
        min_velocity = round(max(0.0, avg_velocity - rng.uniform(2.0, 3.5)), 2)

        bins = [rng.uniform(0.03, 0.30) for _ in range(6)]
        total = sum(bins)
        normalized_bins = [round(value / total, 4) for value in bins]
        months_data.append(
            WindTimeseries(
                month=month,
                avg_velocity=avg_velocity,
                max_velocity=max_velocity,
                min_velocity=min_velocity,
                frequency={
                    "0-2": normalized_bins[0],
                    "2-4": normalized_bins[1],
                    "4-6": normalized_bins[2],
                    "6-8": normalized_bins[3],
                    "8-10": normalized_bins[4],
                    "10+": normalized_bins[5]
                }
            )
        )
    return months_data


@router.post("/wind-rose", response_model=List[WindRoseData])
async def get_wind_rose(request: MeteoRequest):
    """Obtiene los datos de rosa de vientos (16 direcciones)."""
    seed = build_domain_seed(request)
    rng = random.Random(seed + 202)
    directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]

    raw_freq = [rng.uniform(0.02, 0.12) for _ in directions]
    total = sum(raw_freq)
    wind_rose = []
    for idx, direction in enumerate(directions):
        min_vel = round(rng.uniform(0.2, 1.4), 2)
        max_vel = round(min_vel + rng.uniform(2.0, 5.5), 2)
        wind_rose.append(
            WindRoseData(
                direction=direction,
                frequency=round(raw_freq[idx] / total, 4),
                velocity_range={"min": min_vel, "max": max_vel}
            )
        )
    return wind_rose
