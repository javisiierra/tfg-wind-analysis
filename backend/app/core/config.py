from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import tomllib
import geopandas as gpd

from app.core.paths import join_base


def _first_existing(base: Path, candidates: list[str]) -> Optional[Path]:
    for rel in candidates:
        p = base / rel
        if p.exists():
            return p
    return None


def _ensure_path(base: Path, rel: str) -> Path:
    return base / rel


def _infer_lat_lon_from_geometry(path: Path) -> tuple[Optional[float], Optional[float]]:
    try:
        gdf = gpd.read_file(path)

        if gdf.empty:
            return None, None

        if gdf.crs is None:
            # Asunción razonable para tu caso actual
            gdf = gdf.set_crs(epsg=25830)

        gdf = gdf.to_crs(epsg=4326)
        centroid = gdf.union_all().centroid

        return float(centroid.y), float(centroid.x)
    except Exception:
        return None, None


@dataclass(frozen=True)
class Config:
    # --- Meta / control ---
    general_path: Optional[Path] = None
    line: Optional[str] = None
    Station_Name: str = "Station1"
    p: float = 0.20

    # --- Paths (núcleo común) ---
    in_shp: Optional[Path] = None
    out_shp: Optional[Path] = None
    out_rec_shp: Optional[Path] = None
    out_rec_exp_shp: Optional[Path] = None
    out_mdt_tif: Optional[Path] = None

    # --- Alineación con el resto de notebooks ---
    in_xlsx: Optional[Path] = None
    out_apoyos_shp: Optional[Path] = None
    apoyos_epsg_arg: Optional[int] = None

    in_weather_file: Optional[Path] = None
    out_weather_point_file: Optional[Path] = None

    out_perfil_file: Optional[Path] = None
    out_vanos_shp: Optional[Path] = None

    out_wn: Optional[Path] = None
    out_wn_ren: Optional[Path] = None
    out_wn_speed_csv: Optional[Path] = None
    out_wn_dir_csv: Optional[Path] = None
    out_wn_prj_csv: Optional[Path] = None
    out_v_perp_min_shp: Optional[Path] = None

    wr_csv: Optional[Path] = None
    wr_plot: Optional[Path] = None
    wr_title: Optional[str] = None
    
    mesh_resolution: Optional[float] = 100
    num_threads: Optional[int] = 8
    time_zone: Optional[str] = "Europe/Madrid"
    temperature: Optional[float] = 20
    n_directions: Optional[int] = 16
    height: Optional[float] = 15
    
    num_sensores: Optional[int] = 1
    
    weather_source: Optional[str] = "power"

    time_start: Optional[str] = None
    time_end: Optional[str] = None

    wr_n_dir: Optional[int] = 16

    lat: Optional[float] = None
    lon: Optional[float] = None

    apply_rename: bool = False

    def validate(self) -> None:
        if self.p < 0:
            raise ValueError("p debe ser >= 0.")

    @staticmethod
    def from_toml(cfg_path: str | Path) -> "Config":
        cfg_path = Path(cfg_path)
        data: dict[str, Any] = tomllib.loads(cfg_path.read_text(encoding="utf-8"))

        paths = data.get("paths", {})
        params = data.get("params", {})
        case = data.get("case", {})
        wn = data.get("windninja", {})
        source = data.get("source", {})
        time = data.get("time", {})
        wr = data.get("windrose", {})
        location = data.get("location", {})
        rename = data.get("rename", {})

        # La base real del caso es siempre la carpeta donde está el config.toml
        base = cfg_path.parent

        def opt_path(key: str) -> Optional[Path]:
            v = paths.get(key, None)
            if v is None or str(v).strip() == "":
                return None
            return join_base(base, Path(v))

        cfg = Config(
            general_path=base,
            line=case.get("line", data.get("line", None)),
            Station_Name=paths.get("Station_Name", data.get("Station_Name", "Station1")),
            p=float(params.get("p", data.get("p", 0.20))),
            num_sensores=int(params.get("num_sensores", data.get("num_sensores", 1))),

            time_start=time.get("start"),
            time_end=time.get("end"),

            lat=float(location.get("lat", data.get("location", {}).get("lat", 0))),
            lon=float(location.get("lon", data.get("location", {}).get("lon", 0))),

            wr_n_dir=int(wr.get("wr_n_dir", data.get("windrose", {}).get("wr_n_dir", 16))),

            in_shp=opt_path("in_shp"),
            out_shp=opt_path("out_shp"),
            out_rec_shp=opt_path("out_rec_shp"),
            out_rec_exp_shp=opt_path("out_rec_exp_shp"),
            out_mdt_tif=opt_path("out_mdt_tif"),

            in_xlsx=opt_path("in_xlsx"),
            out_apoyos_shp=opt_path("out_apoyos_shp"),
            apoyos_epsg_arg=(int(params["apoyos_epsg_arg"]) if "apoyos_epsg_arg" in params else 25830),

            in_weather_file=opt_path("in_weather_file"),
            out_weather_point_file=opt_path("out_weather_point_file"),

            out_perfil_file=opt_path("out_perfil_file"),
            out_vanos_shp=opt_path("out_vanos_shp"),

            out_wn=opt_path("out_wn"),
            out_wn_ren=opt_path("out_wn_ren"),
            out_wn_speed_csv=opt_path("out_wn_speed_csv"),
            out_wn_dir_csv=opt_path("out_wn_dir_csv"),
            out_wn_prj_csv=opt_path("out_wn_prj_csv"),
            out_v_perp_min_shp=opt_path("out_v_perp_min_shp"),

            wr_csv=opt_path("wr_csv"),
            wr_plot=opt_path("wr_plot"),
            wr_title=paths.get("wr_title", data.get("wr_title", None)),
            
            mesh_resolution=float(wn.get("mesh_resolution")),
            num_threads=int(wn.get("num_threads")),
            time_zone=wn.get("time_zone"),
            temperature=float(wn.get("temperature")),
            n_directions=int(wn.get("n_directions")),
            height=float(wn.get("height")),

            weather_source=source.get("name", "").strip().lower(),
            apply_rename=bool(rename.get("apply", False)),
        )

        cfg.validate()
        return cfg

    @staticmethod
    def from_case_path(case_path: str | Path) -> "Config":
        base = Path(case_path).resolve()

        if not base.exists():
            raise FileNotFoundError(f"No existe la carpeta del caso: {base}")

        if not base.is_dir():
            raise NotADirectoryError(f"La ruta no es una carpeta: {base}")

        line = base.name

        # Entradas por convención / heurística
        in_shp = _first_existing(base, [
            "SHP/dominio.geojson",
            "SHP/dominio.shp",
            f"{line}/{line.replace('_', '-')}.shp",
            f"{line}/{line}.shp",
            f"{line}.shp",
            "Corredoria-Grado.shp",
            "Corredoria_Grado_1_y_2/Corredoria-Grado.shp",
        ])

        in_xlsx = _first_existing(base, [
            "Apoyos/Apoyos Corredoria-Grado.xlsx",
            f"Apoyos/Apoyos {line}.xlsx",
        ])

        in_weather_file = _first_existing(base, [
            "Weather_Input_Data/WN_PointInit_Path.csv",
        ])

        lat, lon = (None, None)
        if in_shp is not None:
            lat, lon = _infer_lat_lon_from_geometry(in_shp)

        cfg = Config(
            general_path=base,
            line=line,
            Station_Name="Station1",
            p=0.20,

            in_shp=in_shp,
            out_shp=_ensure_path(base, "Calculos/extremos_bbox.shp"),
            out_rec_shp=_ensure_path(base, "Calculos/rect_bbox_ejes.shp"),
            out_rec_exp_shp=_ensure_path(base, "Calculos/rect_exp_bbox_ejes.shp"),
            out_mdt_tif=_ensure_path(base, f"MDT_WN/MDT_WN_{line}.tif"),

            in_xlsx=in_xlsx,
            out_apoyos_shp=_ensure_path(base, f"Apoyos/Apoyos {line}.shp"),
            apoyos_epsg_arg=25830,

            in_weather_file=in_weather_file,
            out_weather_point_file=_ensure_path(base, "Weather_Input_Data/WN_input_Point_1.csv"),

            out_perfil_file=_ensure_path(base, f"Calculos/{line}_perfil.png"),
            out_vanos_shp=_ensure_path(base, f"Calculos/{line}_vanos.shp"),

            out_wn=_ensure_path(base, "OUT_WN"),
            out_wn_ren=_ensure_path(base, "OUT_WN_REN"),
            out_wn_speed_csv=None,
            out_wn_dir_csv=None,
            out_wn_prj_csv=None,
            out_v_perp_min_shp=_ensure_path(base, f"Calculos/{line}_v_perp_min.shp"),

            wr_csv=_ensure_path(base, f"WR/{line}_wind_power.csv"),
            wr_plot=_ensure_path(base, f"WR/{line}_wind_power.png"),
            wr_title="",

            mesh_resolution=200.0,
            num_threads=8,
            time_zone="Europe/Madrid",
            temperature=20.0,
            n_directions=36,
            height=15.0,

            num_sensores=1,
            weather_source="power",

            time_start="2023-01-01",
            time_end="2023-12-31",

            wr_n_dir=16,

            lat=lat,
            lon=lon,

            apply_rename=False,
        )

        cfg.validate()
        return cfg


def load_config_toml(cfg_path: str | Path) -> Config:
    return Config.from_toml(cfg_path)


def load_config_from_case(case_path: str | Path) -> Config:
    return Config.from_case_path(case_path)