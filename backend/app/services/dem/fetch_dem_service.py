import subprocess

from app.utils.geo import utm_rect_to_fetch_dem_bbox


def fetch_dem_from_bounds(cfg, minx2, miny2, maxx2, maxy2):
    epsg_utm = 25830

    corners_xy = [
        (minx2, maxy2),  # NW
        (maxx2, maxy2),  # NE
        (maxx2, miny2),  # SE
        (minx2, miny2),  # SW
    ]

    north, east, south, west = utm_rect_to_fetch_dem_bbox(corners_xy, epsg_utm)

    cmd = [
        "fetch_dem",
        "--bbox", str(north), str(east), str(south), str(west),
        "--buf_units", "kilometers",
        "--src", "srtm",
        "--out_res", "30",
        "--fill_no_data",
        str(cfg.out_mdt_tif)
    ]

    p = subprocess.run(cmd, capture_output=True, text=True)

    print("returncode:", p.returncode)
    print("STDOUT:\n", p.stdout)
    print("STDERR:\n", p.stderr)

    if p.returncode != 0:
        raise RuntimeError("fetch_dem falló; revisa STDERR arriba.")

    return p