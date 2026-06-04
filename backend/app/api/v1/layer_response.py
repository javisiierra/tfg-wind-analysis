import json
import logging
from pathlib import Path
from typing import Any

import geopandas as gpd
from fastapi import HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

_LEGACY_LAYER_ALIASES = {
    "ID",
    "SUPPORT_ID",
    "SUPPORT_OR",
    "SUPPORT_ORDER",
    "SUPPORT_TO",
    "SUPPORT_TOTAL",
    "SUP_ORDER",
    "SUP_TOTAL",
    "alpha",
    "alpha_eff",
    "angle_relative",
    "critical_metric",
    "direccio",
    "direccion",
    "direction",
    "from_ap",
    "from_idx",
    "from_ord",
    "from_order",
    "from_supp",
    "from_suppo",
    "from_support",
    "from_support_id",
    "span_labe",
    "support_id",
    "support_or",
    "support_order",
    "support_to",
    "support_total",
    "sup_order",
    "sup_total",
    "to_ap",
    "to_idx",
    "to_ord",
    "to_order",
    "to_supp",
    "to_support",
    "to_support_id",
    "v_perp",
    "vano_id",
    "vperp_min",
    "w_dir",
    "w_speed",
    "wind_dir",
    "wind_direction",
    "wind_speed",
}


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


def _as_int(value: Any) -> int | None:
    try:
        return int(float(value)) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def _drop_legacy_aliases(props: dict[str, Any], canonical_names: set[str]) -> None:
    for alias in _LEGACY_LAYER_ALIASES - canonical_names:
        props.pop(alias, None)


def _normalize_support_properties(props: dict[str, Any], index: int, total: int) -> None:
    support_order = _as_int(
        _first_property(
            props,
            ["support_order", "support_or", "sup_order", "SUPPORT_ORDER", "SUPPORT_OR", "SUP_ORDER"],
        )
    ) or index
    support_total = _as_int(
        _first_property(
            props,
            ["support_total", "support_to", "sup_total", "SUPPORT_TOTAL", "SUPPORT_TO", "SUP_TOTAL"],
        )
    ) or total
    support_id = _support_label_from_value(
        _first_property(props, ["id", "ID", "support_id", "SUPPORT_ID", "apoyo", "APOYO"])
    ) or f"AP-{support_order}"

    _drop_legacy_aliases(props, {"id", "support_order", "support_total"})
    props.update(id=support_id, support_order=support_order, support_total=support_total)


def _normalize_span_properties(props: dict[str, Any], index: int) -> None:
    from_order = _as_int(_first_property(props, ["from_order", "from_ord", "from_idx", "from_ap"]))
    to_order = _as_int(_first_property(props, ["to_order", "to_ord", "to_idx", "to_ap"]))
    from_support = _support_label_from_value(
        _first_property(props, ["from_support", "from_support_id", "from_supp", "from_suppo", "from_ap"])
    ) or _support_label_from_value(from_order)
    to_support = _support_label_from_value(
        _first_property(props, ["to_support", "to_support_id", "to_supp", "to_ap"])
    ) or _support_label_from_value(to_order)
    span_id = str(_first_property(props, ["id", "vano_id", "MAT"]) or f"V-{index}")
    direction_deg = _as_float(
        _first_property(props, ["direction_deg", "direccion", "direccio", "direction", "bearing", "azimuth"])
    )

    _drop_legacy_aliases(
        props,
        {"id", "from_support", "to_support", "from_order", "to_order", "direction_deg"},
    )
    props.update(id=span_id, from_support=from_support, to_support=to_support)
    if from_order is not None:
        props["from_order"] = from_order
    if to_order is not None:
        props["to_order"] = to_order
    if direction_deg is not None:
        props["direction_deg"] = direction_deg


def _normalize_domain_properties(props: dict[str, Any]) -> None:
    crs = _first_property(props, ["crs", "crs_epsg"])
    if crs is not None and not str(crs).upper().startswith("EPSG:"):
        crs = f"EPSG:{crs}"
    if crs is not None:
        props["crs"] = str(crs)


def normalize_layer_geojson(geojson: dict[str, Any], layer_name: str) -> dict[str, Any]:
    features = geojson.get("features", [])

    for index, feature in enumerate(features, start=1):
        props = feature.get("properties") or {}
        feature["properties"] = props
        if layer_name == "apoyos":
            _normalize_support_properties(props, index, len(features))
        elif layer_name == "vanos":
            _normalize_span_properties(props, index)
        elif layer_name == "dominio":
            _normalize_domain_properties(props)

    if layer_name == "worst_supports":
        return _enrich_worst_supports_geojson(geojson)

    return geojson


def _enrich_worst_supports_geojson(geojson: dict[str, Any]) -> dict[str, Any]:
    enriched_count = 0

    for feature in geojson.get("features", []):
        props = feature.get("properties") or {}
        feature["properties"] = props

        vperp_min = _first_property(props, ["vperp_min", "v_perp", "critical_metric"])
        w_speed = _first_property(props, ["w_speed", "wind_speed"])
        w_dir = _first_property(props, ["w_dir", "wind_dir", "wind_direction"])
        alpha = _first_property(props, ["alpha", "alpha_eff", "angle_relative"])
        direction_deg = _first_property(props, ["direction_deg", "direccion", "direccio", "direction"])
        from_support = _first_property(props, ["from_support", "from_supp", "from_suppo", "from_ap"])
        to_support = _first_property(props, ["to_support", "to_supp", "to_ap"])
        from_order = _first_property(props, ["from_order", "from_ord", "from_idx"])
        to_order = _first_property(props, ["to_order", "to_ord", "to_idx"])

        from_support = _support_label_from_value(from_support) or _support_label_from_value(from_order)
        to_support = _support_label_from_value(to_support) or _support_label_from_value(to_order)
        span_label = _first_property(props, ["span_label", "span_labe"])
        if span_label is None and from_support is not None and to_support is not None:
            span_label = f"{from_support} -> {to_support}"

        _drop_legacy_aliases(
            props,
            {
                "from_support",
                "to_support",
                "from_order",
                "to_order",
                "span_label",
                "critical_metric",
                "critical_metric_unit",
                "critical_reason",
                "direction_deg",
                "wind_speed",
                "wind_speed_unit",
                "wind_direction",
                "angle_relative",
                "angle_relative_unit",
            },
        )

        if vperp_min is not None:
            props["critical_metric"] = _as_float(vperp_min)
            props["critical_metric_unit"] = "m/s"
            props.setdefault(
                "critical_reason",
                "Menor componente perpendicular sobre el vano entre escenarios WindNinja",
            )
            enriched_count += 1

        if w_speed is not None:
            props["wind_speed"] = _as_float(w_speed)
            props["wind_speed_unit"] = "m/s"

        if w_dir is not None:
            props["wind_direction"] = _as_float(w_dir)

        if alpha is not None:
            props["angle_relative"] = _as_float(alpha)
            props["angle_relative_unit"] = "deg"

        if direction_deg is not None:
            props["direction_deg"] = _as_float(direction_deg)

        if from_support is not None:
            props["from_support"] = from_support

        if to_support is not None:
            props["to_support"] = to_support

        if from_order is not None:
            props["from_order"] = _as_int(from_order)

        if to_order is not None:
            props["to_order"] = _as_int(to_order)

        if span_label is not None:
            props["span_label"] = span_label

    logger.info(
        "worst_supports GeoJSON enriched",
        extra={
            "features": len(geojson.get("features", [])),
            "enriched_features": enriched_count,
            "canonical_properties": [
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

        geojson = normalize_layer_geojson(geojson, layer_name)

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
        geojson = json.loads(geojson_path.read_text(encoding="utf-8"))
        return JSONResponse(content=normalize_layer_geojson(geojson, layer_name))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"No se pudo leer el GeoJSON de {layer_name}: {e}",
        )
