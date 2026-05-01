from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from app.core.config import load_config_from_case
from app.services.wind.source_service import fetch_era5_hourly_point, fetch_power_hourly


@dataclass
class Era5Service:
    fallback_to_mock: bool = True

    def _resolve_point(self, case_path: str | None) -> tuple[float, float]:
        if case_path:
            cfg = load_config_from_case(Path(case_path))
            if cfg.lat is not None and cfg.lon is not None:
                return float(cfg.lat), float(cfg.lon)
        return 40.4168, -3.7038

    def fetch_hourly(self, year: int, case_path: str | None = None, fallback_to_mock: bool | None = None) -> pd.DataFrame:
        lat, lon = self._resolve_point(case_path)
        start = date(year, 1, 1)
        end = date(year, 12, 31)
        fallback = self.fallback_to_mock if fallback_to_mock is None else fallback_to_mock

        try:
            return fetch_era5_hourly_point(lat=lat, lon=lon, start=start, end=end)
        except Exception:
            if not fallback:
                raise
            return fetch_power_hourly(lat=lat, lon=lon, start=start, end=end)
