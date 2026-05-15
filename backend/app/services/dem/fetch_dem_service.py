import subprocess
import shutil
import os

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

    fetch_dem_bin = shutil.which("fetch_dem")
    if fetch_dem_bin is None:
        raise RuntimeError(
            "No se encontró el ejecutable 'fetch_dem' en el contenedor. "
            "Reconstruye el backend con WindNinja/fetch_dem: "
            "docker compose -f docker-compose.yml -f docker-compose.windninja.yml up --build"
        )

    cmd = [
        fetch_dem_bin,
        "--bbox", str(north), str(east), str(south), str(west),
        "--buf_units", "kilometers",
        "--src", "srtm",
        "--out_res", "30",
        "--fill_no_data",
        str(cfg.out_mdt_tif)
    ]

    env = os.environ.copy()
    srtm_api_key = (
        env.get("CUSTOM_SRTM_API_KEY")
        or env.get("HAVE_CLI_SRTM_API_KEY")
        or env.get("SRTM_API_KEY")
        or env.get("OPENTOPOGRAPHY_API_KEY")
    )
    if srtm_api_key:
        env["CUSTOM_SRTM_API_KEY"] = srtm_api_key

    p = subprocess.run(cmd, capture_output=True, text=True, env=env)

    print("returncode:", p.returncode)
    print("STDOUT:\n", p.stdout)
    print("STDERR:\n", p.stderr)

    if p.returncode != 0:
        detail = p.stderr.strip() or p.stdout.strip() or "sin salida de error"
        if "No API key specified" in detail:
            raise RuntimeError(
                "fetch_dem no pudo descargar SRTM porque falta la API key de OpenTopography. "
                "Configura CUSTOM_SRTM_API_KEY=<tu-api-key> en .env y reinicia el backend."
            )
        raise RuntimeError(f"fetch_dem falló: {detail}")

    return p
