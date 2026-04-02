from pyproj import Transformer

def utm_rect_to_fetch_dem_bbox(corners_xy, epsg_utm):
    """
    corners_xy: iterable con 4 tuplas (x, y) UTM [m]
    epsg_utm: EPSG del sistema UTM de entrada (p.ej. 25830, 32630)
    Devuelve: (north, east, south, west) en grados (lon/lat WGS84)
    """
    t = Transformer.from_crs(f"EPSG:{epsg_utm}", "EPSG:4326", always_xy=True)

    lons, lats = [], []
    for x, y in corners_xy:
        lon, lat = t.transform(x, y)
        lons.append(lon)
        lats.append(lat)

    north = max(lats)
    south = min(lats)
    east  = max(lons)
    west  = min(lons)

    print(f"Esquina NW: ({north:.6f}, {west:.6f})")
    print(f"Esquina SE: ({south:.6f}, {east:.6f})")
    print(f"Esquina NE: ({north:.6f}, {east:.6f})")
    print(f"Esquina SW: ({south:.6f}, {west:.6f})")

    return north, east, south, west