import geopandas as gpd
import numpy as np
from pathlib import Path
from shapely.geometry import Point, Polygon


def ensure_25830_crs(gdf):
    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=25830)
    elif gdf.crs.to_epsg() != 25830:
        gdf = gdf.to_crs(epsg=25830)

    return gdf


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
        return coords

    if gt.startswith("Multi") or gt == "GeometryCollection":
        coords = []
        for g in geom.geoms:
            coords.extend(iter_coords(g))
        return coords

    raise ValueError(f"Tipo geométrico no soportado: {gt}")


def add_matches(arr, mask, label, pts, labels):
    for fid, vidx, x, y in arr[mask]:
        pts.append(Point(float(x), float(y)))
        labels.append((label, int(fid), int(vidx), float(x), float(y)))


def _ensure_output_parent(path):
    if path is not None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)


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
    _ensure_output_parent(cfg.out_shp)
    out_gdf.to_file(cfg.out_shp, driver="ESRI Shapefile", encoding="UTF-8")

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

    _ensure_output_parent(cfg.out_rec_shp)
    rect_gdf.to_file(cfg.out_rec_shp, driver="ESRI Shapefile", encoding="UTF-8")

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

    _ensure_output_parent(cfg.out_rec_exp_shp)
    out.to_file(cfg.out_rec_exp_shp, driver="ESRI Shapefile", encoding="UTF-8")

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
