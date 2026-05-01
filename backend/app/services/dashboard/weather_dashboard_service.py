from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, box, shape

from app.services.weather.era5_service import (
    analyze_wind_for_dashboard,
    download_era5_for_bbox_year,
    load_era5_dataset,
)

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
        candidates = [
            base / "SHP" / "dominio.geojson",
            base / "SHP" / "dominio.shp",
        ]

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

    def _read_vector_bounds(self, candidate: Path, default_crs: int = 25830) -> tuple[float, float, float, float, Any] | None:
        if not candidate.exists():
            return None

        try:
            gdf = gpd.read_file(candidate)
        except Exception:
            logger.exception("Could not read vector file", extra={"path": str(candidate)})
            return None

        if gdf.empty or not gdf.geometry.notna().any():
            return None

        if gdf.crs is None:
            gdf = gdf.set_crs(epsg=default_crs)

        minx, miny, maxx, maxy = map(float, gdf.total_bounds)

        if minx >= maxx or miny >= maxy:
            return None

        return minx, miny, maxx, maxy, gdf.crs

    def _read_supports_excel_bounds(self, base: Path) -> tuple[float, float, float, float, Any] | None:
        apoyos_dir = base / "Apoyos"
        if not apoyos_dir.exists():
            return None

        excel_candidates = [
            *apoyos_dir.glob("*.xlsx"),
            *apoyos_dir.glob("*.xls"),
        ]

        for candidate in excel_candidates:
            try:
                df = pd.read_excel(candidate)
            except Exception:
                logger.exception("Could not read supports Excel", extra={"path": str(candidate)})
                continue

            if df.empty:
                continue

            normalized_cols = {str(col).strip().lower(): col for col in df.columns}

            x_col = (
                normalized_cols.get("x")
                or normalized_cols.get("utm_x")
                or normalized_cols.get("este")
                or normalized_cols.get("easting")
                or normalized_cols.get("coord_x")
                or normalized_cols.get("coordenada_x")
            )
            y_col = (
                normalized_cols.get("y")
                or normalized_cols.get("utm_y")
                or normalized_cols.get("norte")
                or normalized_cols.get("northing")
                or normalized_cols.get("coord_y")
                or normalized_cols.get("coordenada_y")
            )

            lon_col = (
                normalized_cols.get("lon")
                or normalized_cols.get("longitud")
                or normalized_cols.get("longitude")
            )
            lat_col = (
                normalized_cols.get("lat")
                or normalized_cols.get("latitud")
                or normalized_cols.get("latitude")
            )

            if x_col and y_col:
                coords = df[[x_col, y_col]].dropna()
                if coords.empty:
                    continue

                coords[x_col] = pd.to_numeric(coords[x_col], errors="coerce")
                coords[y_col] = pd.to_numeric(coords[y_col], errors="coerce")
                coords = coords.dropna()

                if coords.empty:
                    continue

                geometry = [Point(xy) for xy in zip(coords[x_col], coords[y_col])]
                gdf = gpd.GeoDataFrame(coords, geometry=geometry, crs="EPSG:25830")

                minx, miny, maxx, maxy = map(float, gdf.total_bounds)
                if minx < maxx and miny < maxy:
                    return minx, miny, maxx, maxy, gdf.crs

            if lon_col and lat_col:
                coords = df[[lon_col, lat_col]].dropna()
                if coords.empty:
                    continue

                coords[lon_col] = pd.to_numeric(coords[lon_col], errors="coerce")
                coords[lat_col] = pd.to_numeric(coords[lat_col], errors="coerce")
                coords = coords.dropna()

                if coords.empty:
                    continue

                geometry = [Point(xy) for xy in zip(coords[lon_col], coords[lat_col])]
                gdf = gpd.GeoDataFrame(coords, geometry=geometry, crs="EPSG:4326")

                minx, miny, maxx, maxy = map(float, gdf.total_bounds)
                if minx < maxx and miny < maxy:
                    return minx, miny, maxx, maxy, gdf.crs

        return None

    def _read_case_supports_bounds(self, base: Path) -> tuple[float, float, float, float, Any] | None:
        candidates = [
            base / "Apoyos" / "apoyos.shp",
            base / "Apoyos" / "apoyos.geojson",
            base / "SHP" / "apoyos.shp",
            base / "SHP" / "apoyos.geojson",
        ]

        for candidate in candidates:
            bounds = self._read_vector_bounds(candidate)
            if bounds is not None:
                return bounds

        return self._read_supports_excel_bounds(base)

    def _read_case_trace_bounds(self, base: Path) -> tuple[float, float, float, float, Any] | None:
        candidates = [
            base / "SHP" / "traza.shp",
            base / "SHP" / "traza.geojson",
            base / f"{base.name}.shp",
            base / f"{base.name}.geojson",
        ]

        for candidate in candidates:
            bounds = self._read_vector_bounds(candidate)
            if bounds is not None:
                return bounds

        return None

    def _generate_case_domain(self, base: Path) -> bool:
        source_bounds = self._read_case_trace_bounds(base)

        if source_bounds is None:
            source_bounds = self._read_case_supports_bounds(base)

        if source_bounds is None:
            return False

        minx, miny, maxx, maxy, crs = source_bounds

        width = maxx - minx
        height = maxy - miny
        buffer_value = max(100.0, max(width, height) * 0.10)

        domain_polygon = box(
            minx - buffer_value,
            miny - buffer_value,
            maxx + buffer_value,
            maxy + buffer_value,
        )

        domain_gdf = gpd.GeoDataFrame(
            {"tipo": ["dominio"]},
            geometry=[domain_polygon],
            crs=crs,
        )

        shp_path = base / "SHP" / "dominio.shp"
        geojson_path = base / "SHP" / "dominio.geojson"

        shp_path.parent.mkdir(parents=True, exist_ok=True)

        domain_gdf.to_file(shp_path, driver="ESRI Shapefile", encoding="UTF-8")
        domain_gdf.to_crs(epsg=4326).to_file(geojson_path, driver="GeoJSON", encoding="UTF-8")

        logger.info(
            "Dashboard domain generated automatically",
            extra={
                "case_path": str(base),
                "domain_shp": str(shp_path),
                "domain_geojson": str(geojson_path),
            },
        )

        return True

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
                generated = self._generate_case_domain(base)
                logger.info(
                    "Dashboard tried to generate missing domain",
                    extra={"case_path": str(base), "generated": generated},
                )
                domain_bounds = self._read_case_domain_bounds(base)

            if domain_bounds is None:
                raise DashboardDataError(
                    "No existe dominio en SHP/dominio.geojson o SHP/dominio.shp, y no se pudo generar automáticamente desde SHP/traza.shp, SHP/traza.geojson, Apoyos/apoyos.shp, Apoyos/apoyos.geojson ni desde Excel en Apoyos.",
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

    def _load_year_data(
        self,
        year: int,
        domain: Any | None = None,
        progress_cb=None,
    ) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
        self._validate_year(year)
        resolved = self._resolve_domain_descriptor(domain)

        time_range = {
            "start": f"{year}-01-01",
            "end": f"{year}-12-31",
        }

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
            if progress_cb:
                progress_cb(40, "Solicitud ERA5 enviada a Copernicus. Esperando procesamiento...")

            dataset_path = download_era5_for_bbox_year(
                bbox,
                year,
                progress_cb=progress_cb,
            )

            if progress_cb:
                progress_cb(80, "ERA5 descargado. Leyendo dataset...")

            df = load_era5_dataset(dataset_path)

            if progress_cb:
                progress_cb(90, "Calculando métricas meteorológicas...")

        except Exception as exc:
            detail = str(exc)
            lowered = detail.lower()

            logger.exception(
                "ERA5 fetch/read failed",
                extra={
                    "year": year,
                    "domain_source": resolved.get("source"),
                },
            )

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

            if "required licences not accepted" in lowered and "reanalysis-era5-single-levels" in lowered:
                raise DashboardDataError(
                    "No se pudo descargar ERA5 porque no se han aceptado las licencias del dataset "
                    "reanalysis-era5-single-levels en Copernicus CDS.",
                    "ERA5_DOWNLOAD_FAILED",
                    500,
                ) from exc

            if "cdsapi" in lowered and "instala" in lowered:
                raise DashboardDataError(
                    "No se pudo descargar o leer ERA5: falta la dependencia del cliente CDS (cdsapi).",
                    "ERA5_DOWNLOAD_FAILED",
                    500,
                ) from exc

            if "no se encontró variable temporal en era5" in lowered:
                raise DashboardDataError(
                    "No se pudo leer el NetCDF de ERA5 por un formato temporal no soportado.",
                    "ERA5_DOWNLOAD_FAILED",
                    500,
                ) from exc

            raise DashboardDataError(
                "No se pudo descargar o leer ERA5 por un error de formato/lectura del NetCDF.",
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

    def get_dashboard_bundle(
        self,
        year: int,
        domain: Any | None = None,
        progress_cb=None,
    ) -> dict[str, Any]:
        if progress_cb:
            progress_cb(30, "Comprobando caché ERA5...")

        df, _, meta = self._load_year_data(
            year,
            domain,
            progress_cb=progress_cb,
        )

        metrics = analyze_wind_for_dashboard(df)

        return {
            "meteo_summary": {
                **metrics["meteo_summary"],
                **meta,
            },
            "wind_timeseries": [
                {
                    **item,
                    **meta,
                }
                for item in metrics["wind_timeseries"]
            ],
            "wind_rose": [
                {
                    **item,
                    **meta,
                }
                for item in metrics["wind_rose"]
            ],
        }

    def get_meteo_summary(
        self,
        year: int,
        domain: Any | None = None,
    ) -> dict[str, Any]:
        df, _, meta = self._load_year_data(year, domain)
        metrics = analyze_wind_for_dashboard(df)

        return {
            **metrics["meteo_summary"],
            **meta,
        }

    def get_wind_timeseries(
        self,
        year: int,
        domain: Any | None = None,
    ) -> dict[str, Any]:
        df, _, meta = self._load_year_data(year, domain)
        metrics = analyze_wind_for_dashboard(df)

        return {
            "items": metrics["wind_timeseries"],
            **meta,
        }

    def get_wind_rose(
        self,
        year: int,
        domain: Any | None = None,
    ) -> dict[str, Any]:
        df, _, meta = self._load_year_data(year, domain)
        metrics = analyze_wind_for_dashboard(df)

        return {
            "items": metrics["wind_rose"],
            **meta,
        }