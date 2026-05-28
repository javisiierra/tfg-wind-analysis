import json
import logging
from pathlib import Path
from typing import Any

import geopandas as gpd
from fastapi import HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def _first_property(props: dict[str, Any], names: list[str]) -> Any:
    for name in names:
        value = props.get(name)
        if value is not None and value != "":
            return value
    return None


def _support_label_from_value(value: Any) -> str | None:
    if value is None or value == "":
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.replace(".", "", 1).isdigit():
            return f"AP-{int(float(text))}"
    except ValueError:
        pass
    return text


def _enrich_worst_supports_geojson(geojson: dict[str, Any]) -> dict[str, Any]:
    enriched_count = 0

    for feature in geojson.get("features", []):
        props = feature.get("properties") or {}
        feature["properties"] = props

        vperp_min = _first_property(props, ["vperp_min", "v_perp", "critical_metric"])
        w_speed = _first_property(props, ["w_speed", "wind_speed"])
        w_dir = _first_property(props, ["w_dir", "wind_dir", "wind_direction"])
        alpha = _first_property(props, ["alpha", "alpha_eff", "angle_relative"])
        from_support = _first_property(props, ["from_support", "from_supp", "from_suppo", "from_ap"])
        to_support = _first_property(props, ["to_support", "to_supp", "to_ap"])
        from_order = _first_property(props, ["from_order", "from_ord", "from_idx"])
        to_order = _first_property(props, ["to_order", "to_ord", "to_idx"])

        from_support = _support_label_from_value(from_support) or _support_label_from_value(from_order)
        to_support = _support_label_from_value(to_support) or _support_label_from_value(to_order)
        span_label = _first_property(props, ["span_label", "span_labe"])
        if span_label is None and from_support is not None and to_support is not None:
            span_label = f"{from_support} -> {to_support}"

        if vperp_min is not None:
            props.setdefault("critical_metric", vperp_min)
            props.setdefault("critical_metric_unit", "m/s")
            props.setdefault(
                "critical_reason",
                "Menor componente perpendicular sobre el vano entre escenarios WindNinja",
            )
            enriched_count += 1

        if w_speed is not None:
            props.setdefault("wind_speed", w_speed)
            props.setdefault("wind_speed_unit", "m/s")

        if w_dir is not None:
            props.setdefault("wind_direction", w_dir)

        if alpha is not None:
            props.setdefault("angle_relative", alpha)
            props.setdefault("angle_relative_unit", "deg")

        if from_support is not None:
            props.setdefault("from_support", from_support)
            props.setdefault("from_support_id", from_support)

        if to_support is not None:
            props.setdefault("to_support", to_support)
            props.setdefault("to_support_id", to_support)

        if from_order is not None:
            props.setdefault("from_order", from_order)

        if to_order is not None:
            props.setdefault("to_order", to_order)

        if span_label is not None:
            props.setdefault("span_label", span_label)

    logger.info(
        "worst_supports GeoJSON enriched",
        extra={
            "features": len(geojson.get("features", [])),
            "enriched_features": enriched_count,
            "aliases": [
                "critical_metric",
                "critical_metric_unit",
                "critical_reason",
                "wind_speed",
                "wind_speed_unit",
                "wind_direction",
                "angle_relative",
                "angle_relative_unit",
            ],
        },
    )

    return geojson


def shapefile_to_geojson_response(shp_path: Path, layer_name: str):
    if not shp_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No existe el shapefile de {layer_name}: {shp_path}",
        )

    try:
        gdf = gpd.read_file(shp_path)

        if gdf.empty:
            raise HTTPException(
                status_code=404,
                detail=f"El shapefile de {layer_name} está vacío: {shp_path}",
            )

        if gdf.crs is None:
            gdf = gdf.set_crs(epsg=25830)

        gdf = gdf.to_crs(epsg=4326)
        geojson = json.loads(gdf.to_json())

        if layer_name == "worst_supports":
            geojson = _enrich_worst_supports_geojson(geojson)

        return JSONResponse(content=geojson)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"No se pudo leer el shapefile de {layer_name}: {e}",
        )


def geojson_file_to_geojson_response(geojson_path: Path, layer_name: str):
    if not geojson_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No existe el GeoJSON de {layer_name}: {geojson_path}",
        )

    try:
        return JSONResponse(content=json.loads(geojson_path.read_text(encoding="utf-8")))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"No se pudo leer el GeoJSON de {layer_name}: {e}",
        )
