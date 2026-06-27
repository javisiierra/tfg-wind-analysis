from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString

from app.core.paths import normalize_case_path


DOMAIN_CRS_EPSG = 25830
DEFAULT_DOMAIN_BUFFER_M = 200.0


class DomainGenerationError(ValueError):
    pass


@dataclass(frozen=True)
class DomainGenerationResult:
    domain_shp: str
    domain_geojson: str
    source: str
    buffer_m: float
    crs: str = f"EPSG:{DOMAIN_CRS_EPSG}"

    def to_dict(self) -> dict[str, str | float]:
        return asdict(self)


class DomainGenerationService:
    """Servicio encargado de generar y leer los archivos del dominio de simulación."""

    def __init__(
        self,
        default_buffer_m: float = DEFAULT_DOMAIN_BUFFER_M,
        domain_crs_epsg: int = DOMAIN_CRS_EPSG,
    ) -> None:
        self.default_buffer_m = self._validate_buffer(default_buffer_m)
        self.domain_crs_epsg = domain_crs_epsg

    def canonical_shp_path(self, case_path: str | Path) -> Path:
        return normalize_case_path(case_path) / "SHP" / "dominio.shp"

    def canonical_geojson_path(self, case_path: str | Path) -> Path:
        return normalize_case_path(case_path) / "SHP" / "dominio.geojson"

    def find_existing_domain_path(self, case_path: str | Path) -> Path | None:
        for candidate in (
            self.canonical_shp_path(case_path),
            self.canonical_geojson_path(case_path),
        ):
            if candidate.exists():
                return candidate
        return None

    def read_domain_bounds_wgs84(self, case_path: str | Path) -> tuple[list[float], str] | None:
        for candidate in (
            self.canonical_geojson_path(case_path),
            self.canonical_shp_path(case_path),
        ):
            if not candidate.exists():
                continue

            domain = self._read_vector(candidate, label="dominio")
            domain_wgs84 = domain.to_crs(epsg=4326)
            min_lon, min_lat, max_lon, max_lat = map(float, domain_wgs84.total_bounds)
            if min_lon >= max_lon or min_lat >= max_lat:
                raise DomainGenerationError(f"El dominio tiene límites no válidos: {candidate}")
            return [min_lon, min_lat, max_lon, max_lat], candidate.name

        return None

    def generate_from_trace(
        self,
        case_path: str | Path,
        trace_path: str | Path,
        buffer_m: float | None = None,
    ) -> DomainGenerationResult:
        trace = self._read_vector(Path(trace_path), label="traza")
        source_geometry = trace.geometry.union_all()
        if source_geometry.is_empty:
            raise DomainGenerationError("La traza no contiene geometrías válidas.")
        return self._persist_domain(case_path, source_geometry, "trace", buffer_m)

    def generate_from_supports(
        self,
        case_path: str | Path,
        supports_path: str | Path,
        buffer_m: float | None = None,
    ) -> DomainGenerationResult:
        supports = self._read_vector(Path(supports_path), label="apoyos")
        order_column = next(
            (column for column in ("support_order", "support_or") if column in supports.columns),
            None,
        )
        if order_column is not None:
            supports = supports.sort_values(order_column, kind="stable")

        coords = [
            (geometry.x, geometry.y)
            for geometry in supports.geometry
            if geometry is not None and not geometry.is_empty and geometry.geom_type == "Point"
        ]
        if len(coords) < 2:
            raise DomainGenerationError("Se necesitan al menos 2 apoyos puntuales para generar el dominio.")

        return self._persist_domain(case_path, LineString(coords), "supports", buffer_m)

    def _read_vector(self, path: Path, label: str) -> gpd.GeoDataFrame:
        if not path.exists():
            raise DomainGenerationError(f"No existe el archivo de {label}: {path}")

        try:
            gdf = gpd.read_file(path)
        except Exception as exc:
            raise DomainGenerationError(f"No se pudo leer el archivo de {label}: {path}") from exc

        if gdf.empty or not gdf.geometry.notna().any():
            raise DomainGenerationError(f"La capa de {label} está vacía.")

        if gdf.crs is None:
            gdf = gdf.set_crs(epsg=self.domain_crs_epsg)

        try:
            return gdf.to_crs(epsg=self.domain_crs_epsg)
        except Exception as exc:
            raise DomainGenerationError(f"El CRS de la capa de {label} no es válido.") from exc

    def _persist_domain(
        self,
        case_path: str | Path,
        source_geometry,
        source: str,
        buffer_m: float | None,
    ) -> DomainGenerationResult:
        resolved_buffer = self._validate_buffer(
            self.default_buffer_m if buffer_m is None else buffer_m
        )
        domain_geometry = source_geometry.buffer(resolved_buffer)
        if domain_geometry.is_empty:
            raise DomainGenerationError("No se pudo construir un dominio válido.")

        domain = gpd.GeoDataFrame(
            {
                "source": [source],
                "buffer_m": [resolved_buffer],
                "crs_epsg": [self.domain_crs_epsg],
            },
            geometry=[domain_geometry],
            crs=f"EPSG:{self.domain_crs_epsg}",
        )
        shp_path = self.canonical_shp_path(case_path)
        geojson_path = self.canonical_geojson_path(case_path)
        shp_path.parent.mkdir(parents=True, exist_ok=True)

        domain.to_file(shp_path, driver="ESRI Shapefile", encoding="UTF-8")
        domain.to_crs(epsg=4326).to_file(geojson_path, driver="GeoJSON", encoding="UTF-8")

        return DomainGenerationResult(
            domain_shp=str(shp_path),
            domain_geojson=str(geojson_path),
            source=source,
            buffer_m=resolved_buffer,
        )

    @staticmethod
    def _validate_buffer(buffer_m: float) -> float:
        try:
            resolved = float(buffer_m)
        except (TypeError, ValueError) as exc:
            raise DomainGenerationError("El buffer debe ser un número en metros.") from exc
        if resolved <= 0:
            raise DomainGenerationError("El buffer debe ser mayor que 0 metros.")
        return resolved
