import geopandas as gpd
import numpy as np
from shapely.geometry import Point, Polygon

from app.services.domain.reprojection_service import ensure_25830_crs


def iter_coords(geom):
    """Return the list of (x, y) points with all vertices of the geometry."""
    if geom is None or geom.is_empty:
        return []

    gt = geom.geom_type

    if gt == "Point":
        return [(geom.x, geom.y)]

    if gt in ("LineString", "LinearRing"):
        return list(geom.coords)

    if gt == "Polygon":
        coords = list(geom.exterior.coords)
        # Si quieres incluir agujeros interiores:
        # for ring in geom.interiors:
        #     coords.extend(list(ring.coords))
        return coords

    if gt.startswith("Multi") or gt == "GeometryCollection":
        coords = []
        for g in geom.geoms:
            coords.extend(iter_coords(g))
        return coords

    raise ValueError(f"Tipo geométrico no soportado: {gt}")


def add_matches(arr, mask, label, pts, labels):
    """
    add_matches.

    Notes
    -----
    Auto-generated docstring. Please refine parameter/return descriptions if needed.
    """
    for fid, vidx, x, y in arr[mask]:
        pts.append(Point(float(x), float(y)))
        labels.append((label, int(fid), int(vidx), float(x), float(y)))


def preprocess_geometry(cfg):
    gdf = gpd.read_file(cfg.in_shp)
    gdf = ensure_25830_crs(gdf)

    minx, miny, maxx, maxy = gdf.total_bounds

    rows = []
    for fid, geom in zip(gdf.index, gdf.geometry):
        for vidx, c in enumerate(iter_coords(geom)):
            x, y = c[0], c[1]
            rows.append((fid, vidx, float(x), float(y)))

    arr = np.array(rows, dtype=object)
    xs = arr[:, 2].astype(float)
    ys = arr[:, 3].astype(float)

    tol = 1e-12

    # Seleccionar los vértices que alcanzan extremos
    pts = []
    labels = []

    add_matches(arr, np.isclose(xs, minx, atol=tol), "x_min", pts, labels)
    add_matches(arr, np.isclose(xs, maxx, atol=tol), "x_max", pts, labels)
    add_matches(arr, np.isclose(ys, miny, atol=tol), "y_min", pts, labels)
    add_matches(arr, np.isclose(ys, maxy, atol=tol), "y_max", pts, labels)

    # --- Construir GeoDataFrame de salida ---
    out_gdf = gpd.GeoDataFrame(
        {
            "extremo": [t[0] for t in labels],
            "feat_id": [t[1] for t in labels],
            "vert_id": [t[2] for t in labels],
            "x":       [t[3] for t in labels],
            "y":       [t[4] for t in labels],
        },
        geometry=pts,
        crs="EPSG:25830"
    )

    # (Opcional) eliminar duplicados exactos (p.ej., si un punto cumple x_min y y_min)
    out_gdf = out_gdf.drop_duplicates(subset=["x", "y"]).reset_index(drop=True)

    # --- Exportar a Shapefile ---
    out_gdf.to_file(cfg.out_shp, driver="ESRI Shapefile", encoding="UTF-8")

    print(f"Exportado: {cfg.out_shp}  (n={len(out_gdf)} puntos)")
    print("BBox:", (minx, miny, maxx, maxy))

    # rows: lista de tuplas (fid, vidx, x, y)
    arr = np.array(rows, dtype=object)
    xs = arr[:, 2].astype(float)
    ys = arr[:, 3].astype(float)

    minx, maxx = xs.min(), xs.max()
    miny, maxy = ys.min(), ys.max()

    # Polígono del rectángulo (cerrado)
    rect = Polygon([
        (minx, miny),
        (maxx, miny),
        (maxx, maxy),
        (minx, maxy),
        (minx, miny)
    ])

    rect_gdf = gpd.GeoDataFrame(
        {"tipo": ["bbox_ejes"], "minx": [minx], "miny": [miny], "maxx": [maxx], "maxy": [maxy]},
        geometry=[rect],
        crs="EPSG:25830"
    )

    rect_gdf.to_file(cfg.out_rec_shp, driver="ESRI Shapefile", encoding="UTF-8")
    print(f"Exportado: {cfg.out_rec_shp}")

    w = maxx - minx
    h = maxy - miny
    cx = (minx + maxx) / 2
    cy = (miny + maxy) / 2
    delta = ((w + h) / 2) * cfg.p

    minx2 = minx - delta
    maxx2 = maxx + delta
    miny2 = miny - delta
    maxy2 = maxy + delta

    rect1 = Polygon([
        (minx2, miny2),
        (maxx2, miny2),
        (maxx2, maxy2),
        (minx2, maxy2),
        (minx2, miny2)
    ])

    out = gpd.GeoDataFrame(
        {
            "tipo": ["bbox_expandido"],
            "minx": [minx2],
            "miny": [miny2],
            "maxx": [maxx2],
            "maxy": [maxy2],
            "cx": [cx],
            "cy": [cy],
            "delta": [delta],
        },
        geometry=[rect1],
        crs="EPSG:25830"
    )

    out.to_file(cfg.out_rec_exp_shp, driver="ESRI Shapefile", encoding="UTF-8")
    print(f"Exportado: {cfg.out_rec_exp_shp}")

    return {
        "gdf": gdf,
        "rows": rows,
        "arr": arr,
        "xs": xs,
        "ys": ys,
        "minx": minx,
        "miny": miny,
        "maxx": maxx,
        "maxy": maxy,
        "minx2": minx2,
        "miny2": miny2,
        "maxx2": maxx2,
        "maxy2": maxy2,
        "out_gdf": out_gdf,
        "rect_gdf": rect_gdf,
        "out_rec_exp_gdf": out,
    }