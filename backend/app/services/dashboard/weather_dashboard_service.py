from __future__ import annotations

from dataclasses import dataclass, field
import logging
from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4

import geopandas as gpd
import pandas as pd
from shapely.geometry import box, shape

from app.services.weather.era5_service import analyze_wind, download_era5_for_bbox_year, era5_cache_target_path, load_era5_dataset


logger = logging.getLogger(__name__)


class DashboardDataError(Exception):
    def __init__(self, message: str, error_code: str, http_status: int):
        super().__init__(message)
        self.error_code = error_code
        self.http_status = http_status


@dataclass
class WeatherDashboardService:
    start_year: int = 2000
    end_year: int = 2099

    def _validate_year(self, year: int) -> None:
        if not isinstance(year, int) or year < self.start_year or year > self.end_year:
            raise DashboardDataError(
                f"Year must be a valid year ({self.start_year}-{self.end_year})",
                error_code="INVALID_YEAR",
                http_status=422,
            )


    def _read_case_domain_bounds(self, base: Path) -> tuple[list[float], str] | None:
        candidates = [base / "SHP" / "dominio.geojson", base / "SHP" / "dominio.shp"]
        for candidate in candidates:
            if not candidate.exists():
                continue
            try:
                gdf = gpd.read_file(candidate)
            except Exception as exc:
                raise DashboardDataError(
                    f"Could not read domain file: {candidate.name}",
                    "INVALID_CASE_DOMAIN",
                    422,
                ) from exc

            if gdf.empty or not gdf.geometry.notna().any():
                continue

            gdf_wgs84 = gdf.to_crs(epsg=4326) if gdf.crs is not None else gdf
            min_lon, min_lat, max_lon, max_lat = map(float, gdf_wgs84.total_bounds)
            if min_lon >= max_lon or min_lat >= max_lat:
                continue

            return [min_lon, min_lat, max_lon, max_lat], candidate.name

        return None

    def _generate_case_domain(self, base: Path) -> None:
        trace_candidates = [base / "SHP" / "traza.shp", base / f"{base.name}.shp"]
        trace_path = next((candidate for candidate in trace_candidates if candidate.exists()), None)
        if trace_path is None:
            return

        try:
            trace_gdf = gpd.read_file(trace_path)
        except Exception:
            return

        if trace_gdf.empty or not trace_gdf.geometry.notna().any():
            return

        if trace_gdf.crs is None:
            trace_gdf = trace_gdf.set_crs(epsg=25830)

        minx, miny, maxx, maxy = trace_gdf.total_bounds
        if minx >= maxx or miny >= maxy:
            return

        buffer_value = max(100.0, max((maxx - minx), (maxy - miny)) * 0.05)
        domain_polygon = box(minx - buffer_value, miny - buffer_value, maxx + buffer_value, maxy + buffer_value)
        domain_gdf = gpd.GeoDataFrame({"tipo": ["dominio"]}, geometry=[domain_polygon], crs=trace_gdf.crs)

        shp_path = base / "SHP" / "dominio.shp"
        geojson_path = base / "SHP" / "dominio.geojson"
        shp_path.parent.mkdir(parents=True, exist_ok=True)
        domain_gdf.to_file(shp_path, driver="ESRI Shapefile", encoding="UTF-8")
        domain_gdf.to_file(geojson_path, driver="GeoJSON", encoding="UTF-8")

    def _resolve_domain_descriptor(self, domain: Any) -> dict[str, Any]:
        descriptor = domain.model_dump() if hasattr(domain, "model_dump") else dict(domain or {})

        bbox = descriptor.get("bbox")
        if bbox is not None:
            min_lon, min_lat, max_lon, max_lat = map(float, bbox)
            if min_lon >= max_lon or min_lat >= max_lat:
                raise DashboardDataError("Invalid bbox: expected min < max", "INVALID_BBOX", 422)
            return {
                "lat": (min_lat + max_lat) / 2.0,
                "lon": (min_lon + max_lon) / 2.0,
                "bbox": [min_lon, min_lat, max_lon, max_lat],
                "source": "bbox",
                "crs": "EPSG:4326",

            }

        geometry = descriptor.get("geometry")
        if geometry is not None:
            try:
                geom = shape(geometry)
            except Exception as exc:
                raise DashboardDataError("Invalid geometry payload", "INVALID_GEOJSON", 422) from exc
            min_lon, min_lat, max_lon, max_lat = map(float, geom.bounds)
            return {
                "lat": (min_lat + max_lat) / 2.0,
                "lon": (min_lon + max_lon) / 2.0,
                "bbox": [min_lon, min_lat, max_lon, max_lat],
                "source": "geometry",
                "crs": "EPSG:4326",

            }

        case_path = descriptor.get("case_path")
        if case_path:
            base = Path(case_path)
            domain_bounds = self._read_case_domain_bounds(base)
            if domain_bounds is None:
                self._generate_case_domain(base)
                domain_bounds = self._read_case_domain_bounds(base)

            if domain_bounds is None:
                raise DashboardDataError(
                    "falta dominio y no se pudo generar desde apoyos",
                    "INVALID_CASE_DOMAIN",
                    400,
                )

            bbox, filename = domain_bounds
            min_lon, min_lat, max_lon, max_lat = bbox
            return {
                "lat": (min_lat + max_lat) / 2.0,
                "lon": (min_lon + max_lon) / 2.0,
                "bbox": bbox,
                "source": f"case_path:{filename}",
                "crs": "EPSG:4326",
                "case_path": str(base),

            }

        raise DashboardDataError(
            "Provide one valid domain source (bbox, geometry, or case_path)",
            "MISSING_DOMAIN",
            400,
        )

    def _load_year_data(self, year: int, domain: Any | None = None) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
        self._validate_year(year)
        resolved = self._resolve_domain_descriptor(domain)
        time_range = {"start": f"{year}-01-01", "end": f"{year}-12-31"}
        meta = {
            "source": "era5",
            "request_id": str(uuid4()),
            "domain_bbox": resolved["bbox"],
            "time_range": time_range,
            "crs": resolved.get("crs", "EPSG:4326"),
            "status": "ok",
        }

        bbox = resolved["bbox"]
        try:
            dataset_path = download_era5_for_bbox_year(bbox, year)
            df = load_era5_dataset(dataset_path)
        except Exception as exc:
            detail = str(exc)
            lowered = detail.lower()
            logger.exception("ERA5 fetch/read failed", extra={"year": year, "domain_source": resolved.get("source")})
            if "dominio.geojson" in lowered or "dominio.shp" in lowered or "dominio válido" in lowered:
                raise DashboardDataError(
                    "No se pudo descargar o leer ERA5: el dominio del case_path es inválido o no existe (esperado SHP/dominio.geojson o SHP/dominio.shp).",
                    "ERA5_DOWNLOAD_FAILED",
                    500,
                ) from exc
            if ".cdsapirc" in lowered or "missing/incomplete configuration file" in lowered:
                raise DashboardDataError(
                    "No se pudieron descargar datos ERA5 porque faltan credenciales de Copernicus CDS API.",
                    "ERA5_DOWNLOAD_FAILED",
                    500,
                ) from exc
            if "copernicus cds api" in lowered or "cdsapi_url" in lowered or "cdsapi_key" in lowered:
                raise DashboardDataError(
                    "No se pudieron descargar datos ERA5 porque faltan credenciales de Copernicus CDS API.",
                    "ERA5_DOWNLOAD_FAILED",
                    500,
                ) from exc
            if "cdsapi" in lowered and "instala" in lowered:
                raise DashboardDataError(
                    "No se pudo descargar o leer ERA5: falta la dependencia del cliente CDS (cdsapi).",
                    "ERA5_DOWNLOAD_FAILED",
                    500,
                ) from exc
            raise DashboardDataError(
                "No se pudo descargar o leer ERA5 por un error del proveedor o de red.",
                "ERA5_DOWNLOAD_FAILED",
                500,
            ) from exc

        if df.empty:
            raise DashboardDataError(
                f"No meteorological data available for year {year}",
                "NO_DATA",
                404,
            )
        return df, resolved, meta


    def get_dashboard_bundle(self, year: int, domain: Any | None = None, progress_cb=None) -> dict[str, Any]:
        if progress_cb:
            progress_cb(30, "Comprobando caché ERA5...")
        df, resolved, meta = self._load_year_data(year, domain)

        if progress_cb:
            cache_file = Path(era5_cache_target_path(resolved["bbox"], year))
            if cache_file.exists() and cache_file.stat().st_size > 0:
                progress_cb(45, "Usando datos ERA5 cacheados")
            else:
                progress_cb(45, "Descargando ERA5...")
            progress_cb(70, "Leyendo dataset...")
            progress_cb(85, "Calculando métricas...")

        metrics = analyze_wind(df)
        return {
            "meteo_summary": {**metrics["meteo_summary"], **meta},
            "wind_timeseries": [{**item, **meta} for item in metrics["timeseries"]],
            "wind_rose": [{**item, **meta} for item in metrics["wind_rose"]],
        }

    def get_meteo_summary(self, year: int, domain: Any | None = None) -> dict[str, Any]:
        df, _, meta = self._load_year_data(year, domain)
        metrics = analyze_wind(df)
        summary = metrics["meteo_summary"]

        return {
            **summary,
            **meta,
        }

    def get_wind_timeseries(self, year: int, domain: Any | None = None) -> dict[str, Any]:
        df, _, meta = self._load_year_data(year, domain)
        metrics = analyze_wind(df)
        return {"items": metrics["timeseries"], **meta}

    def get_wind_rose(self, year: int, domain: Any | None = None) -> dict[str, Any]:
        df, _, meta = self._load_year_data(year, domain)
        metrics = analyze_wind(df)
        return {"items": metrics["wind_rose"], **meta}
