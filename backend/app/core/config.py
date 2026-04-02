from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import tomllib

from app.core.paths import join_base


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

        # Base de resolución: paths.general_path si existe; si no, carpeta del TOML
        base = Path(paths.get("general_path", cfg_path.parent))

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


def load_config_toml(cfg_path: str | Path) -> Config:
    return Config.from_toml(cfg_path)