from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
from shapely.geometry import LineString

from app.core.paths import normalize_case_path


class VanosGenerationError(ValueError):
    """Error controlado al generar vanos desde apoyos."""


def canonical_vanos_shp_path(case_path: str | Path) -> Path:
    return normalize_case_path(case_path) / "SHP" / "vanos.shp"


def canonical_vanos_geojson_path(case_path: str | Path) -> Path:
    return normalize_case_path(case_path) / "SHP" / "vanos.geojson"


def vanos_candidate_paths(case_path: str | Path, cfg: Any | None = None) -> list[Path]:
    case_root = normalize_case_path(case_path)
    candidates: list[Path] = []

    if cfg is not None and getattr(cfg, "out_vanos_shp", None):
        candidates.append(Path(cfg.out_vanos_shp))

    candidates.extend(
        [
            canonical_vanos_shp_path(case_root),
            case_root / "Calculos" / f"{case_root.name}_vanos.shp",
        ]
    )

    unique: list[Path] = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    return unique


def find_existing_vanos_path(case_path: str | Path, cfg: Any | None = None) -> Path | None:
    for candidate in vanos_candidate_paths(case_path, cfg):
        if candidate.exists():
            return candidate
    return None


def find_supports_path(case_path: str | Path, cfg: Any | None = None) -> Path | None:
    case_root = normalize_case_path(case_path)
    candidates: list[Path] = []

    if cfg is not None and getattr(cfg, "out_apoyos_shp", None):
        candidates.append(Path(cfg.out_apoyos_shp))

    candidates.append(case_root / "Apoyos" / "apoyos.shp")

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _feature_count(path: Path) -> int:
    try:
        return int(len(gpd.read_file(path)))
    except Exception:
        return 0


def _remove_shapefile(path: Path) -> None:
    for suffix in [".shp", ".shx", ".dbf", ".prj", ".cpg"]:
        component = path.with_suffix(suffix)
        if component.exists():
            component.unlink()


def _support_identifier(row: Any, fallback_order: int) -> str:
    for field in ["id", "ID", "support_id", "SUPPORT_ID", "apoyo", "APOYO", "cod_apoyo", "COD_APOYO"]:
        value = row.get(field)
        if value is not None and str(value).strip():
            return str(value)
    return f"AP-{fallback_order}"


def _ordered_supports(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    order_candidates = ["support_order", "SUPPORT_ORDER", "sup_order", "SUP_ORDER", "support_or", "SUPPORT_OR"]
    for field in order_candidates:
        if field in gdf.columns:
            return gdf.sort_values(field, kind="stable").reset_index(drop=True)

    sortable = gdf.copy()
    sortable["_sort_x"] = sortable.geometry.x
    return sortable.sort_values("_sort_x", kind="stable").drop(columns=["_sort_x"]).reset_index(drop=True)


def generate_vanos_from_supports(case_path: str | Path, cfg: Any | None = None) -> dict[str, Any]:
    case_root = normalize_case_path(case_path)
    existing_vanos = find_existing_vanos_path(case_root, cfg)

    if existing_vanos is not None:
        return {
            "status": "ok",
            "message": "La capa de vanos ya existe",
            "created": False,
            "vanos_count": _feature_count(existing_vanos),
            "output_shp": str(existing_vanos),
            "output_geojson": str(canonical_vanos_geojson_path(case_root)),
        }

    supports_path = find_supports_path(case_root, cfg)
    if supports_path is None:
        raise VanosGenerationError("No existen apoyos para generar vanos.")

    supports = gpd.read_file(supports_path)
    if supports.empty:
        raise VanosGenerationError("La capa de apoyos está vacía.")

    if supports.crs is None:
        supports = supports.set_crs(epsg=getattr(cfg, "apoyos_epsg_arg", None) or 25830)

    supports = supports[supports.geometry.notna()].copy()
    supports = supports[supports.geometry.geom_type == "Point"].copy()
    supports = _ordered_supports(supports)

    if len(supports) < 2:
        raise VanosGenerationError("Se necesitan al menos 2 apoyos para generar vanos.")

    records: list[dict[str, Any]] = []
    for index in range(len(supports) - 1):
        from_row = supports.iloc[index]
        to_row = supports.iloc[index + 1]
        p1 = from_row.geometry
        p2 = to_row.geometry

        from_order = index + 1
        to_order = index + 2
        dx = p2.x - p1.x
        dy = p2.y - p1.y
        direction = (np.degrees(np.arctan2(dx, dy)) + 360.0) % 360.0

        records.append(
            {
                "id": f"V-{index + 1}",
                "vano_id": f"V-{index + 1}",
                "from_support": _support_identifier(from_row, from_order),
                "to_support": _support_identifier(to_row, to_order),
                "from_order": from_order,
                "to_order": to_order,
                "direccion": float(direction),
                "geometry": LineString([p1, p2]),
            }
        )

    vanos = gpd.GeoDataFrame(records, geometry="geometry", crs=supports.crs)
    output_shp = canonical_vanos_shp_path(case_root)
    output_geojson = canonical_vanos_geojson_path(case_root)
    output_shp.parent.mkdir(parents=True, exist_ok=True)

    _remove_shapefile(output_shp)
    vanos.to_file(output_shp, driver="ESRI Shapefile", encoding="UTF-8")
    vanos.to_file(output_geojson, driver="GeoJSON")

    return {
        "status": "ok",
        "message": f"Generados {len(vanos)} vanos desde apoyos",
        "created": True,
        "vanos_count": len(vanos),
        "output_shp": str(output_shp),
        "output_geojson": str(output_geojson),
    }
