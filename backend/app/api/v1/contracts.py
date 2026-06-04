from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


PipelineStatus = Literal["ok", "ready"]
DashboardJobStatus = Literal["queued", "running", "finished", "failed"]


class APIErrorDTO(BaseModel):
    code: str
    message: str
    stage: str | None = None


class SupportDTO(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    support_order: int
    support_total: int | None = None


class SpanDTO(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    from_support: str
    to_support: str
    from_order: int | None = None
    to_order: int | None = None
    direction_deg: float


class DomainDTO(BaseModel):
    model_config = ConfigDict(extra="allow")

    domain_shp: str | None = None
    domain_geojson: str | None = None
    source: str | None = None
    buffer_m: float | None = None
    crs: str | None = None


class WorstSupportDTO(BaseModel):
    model_config = ConfigDict(extra="allow")

    from_support: str
    to_support: str
    span_label: str
    critical_metric: float
    critical_metric_unit: str = "m/s"
    critical_reason: str
    direction_deg: float | None = None
    wind_speed: float | None = None
    wind_speed_unit: str = "m/s"
    wind_direction: float | None = None
    angle_relative: float | None = None
    angle_relative_unit: str = "deg"


class PipelineStatusDTO(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: PipelineStatus
    case_path: str | None = None
    message: str | None = None


class DashboardJobResultDTO(BaseModel):
    meteo_summary: dict[str, Any]
    wind_timeseries: list[dict[str, Any]]
    wind_rose: list[dict[str, Any]]


class DashboardJobStatusDTO(BaseModel):
    job_id: str
    status: DashboardJobStatus
    progress: int = Field(ge=0, le=100)
    message: str
    result: DashboardJobResultDTO | None = None
    error: str | None = None


def api_error(code: str, message: str, stage: str | None = None) -> dict[str, Any]:
    return APIErrorDTO(code=code, message=message, stage=stage).model_dump(exclude_none=True)
