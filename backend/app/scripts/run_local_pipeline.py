from pathlib import Path

import shutil
from app.core.config import load_config_toml
from app.services.dem.fetch_dem_service import fetch_dem_from_bounds
from app.services.domain.geometry_service import preprocess_geometry
from app.services.profiles.line_profile_service import (
    build_line_profile_df,
    compute_profile_stats,
    plot_profile_by_distance,
    plot_profile_by_distance_inverted,
    plot_profile_by_x,
)
from app.services.scenarios.generate_scenarios_service import (
    first_point_xy_station,
    generate_windninja_input_csv,
)
from app.services.towers.import_towers_service import excel_to_shp
from app.services.towers.towers_to_points_service import (
    build_vanos_df,
    export_vanos_midpoints_shp,
)
from app.services.wind.rename_files_service import run_rename
from app.services.wind.source_service import (
    fetch_aemet_daily_station,
    fetch_era5_hourly_point,
    fetch_power_hourly,
    parse_date_str,
)
from app.services.wind.wind_rose_service import (
    compute_wind_rose_table,
    fit_weibull_2p,
    plot_weibull_fit,
    plot_wind_rose,
)
from app.services.windninja.runner_service import run_windninja


CONFIG_PATH = Path(r"C:\TFG\datos\Corredoria_Grado_1_y_2\config.toml")


def run_geometry_and_dem(cfg):
    geom_result = preprocess_geometry(cfg)

    fetch_dem_from_bounds(
        cfg,
        geom_result["minx2"],
        geom_result["miny2"],
        geom_result["maxx2"],
        geom_result["maxy2"],
    )

    return geom_result


def run_towers(cfg):
    apoyos_df = excel_to_shp(
        xlsx_path=cfg.in_xlsx,
        shp_path=cfg.out_apoyos_shp,
        epsg=cfg.apoyos_epsg_arg,
    )

    vanos_df = build_vanos_df(apoyos_df)

    export_vanos_midpoints_shp(
        vanos_df=vanos_df,
        shp_path=cfg.out_vanos_shp,
        epsg=cfg.apoyos_epsg_arg,
    )

    return {
        "apoyos_df": apoyos_df,
        "vanos_df": vanos_df,
    }


def run_line_profile(cfg):
    work = build_line_profile_df(cfg)
    stats = compute_profile_stats(work)

    out_dir = Path("out") / "line_profile"
    out_dir.mkdir(parents=True, exist_ok=True)

    profile_dist_path = out_dir / "perfil_longitudinal.pdf"
    profile_dist_inv_path = out_dir / "perfil_longitudinal_invertido.pdf"

    plot_profile_by_distance(work, savepath=profile_dist_path)
    plot_profile_by_distance_inverted(work, savepath=profile_dist_inv_path)
    plot_profile_by_x(work, cfg)  # sigue usando cfg.out_perfil_file

    return {
        "work": work,
        "stats": stats,
        "profile_dist_path": profile_dist_path,
        "profile_dist_inv_path": profile_dist_inv_path,
        "profile_x_path": cfg.out_perfil_file,
    }


def run_generate_scenarios(cfg):
    station_name, utmx, utmy = first_point_xy_station(cfg.out_apoyos_shp)

    df = generate_windninja_input_csv(
        cfg=cfg,
        station_name=station_name,
        projection="PROJCS",
        utm_x=utmx,
        utm_y=utmy,
        height=cfg.height,
        temperature=cfg.temperature,
        n_directions=cfg.n_directions,
        wind_speeds=[1],
        output_csv=cfg.out_weather_point_file,
        start_datetime_utc="2025-01-01T00:00:00Z",
        dt_minutes=15,
        ordering="speed_then_dir",
    )

    out_dir = Path("out") / "scenarios"
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg_csv = Path(cfg.out_weather_point_file)
    out_csv = out_dir / cfg_csv.name

    if cfg_csv.exists():
        shutil.copy2(cfg_csv, out_csv)

    return {
        "df": df,
        "cfg_csv_path": cfg_csv,
        "out_csv_path": out_csv,
    }


def run_windninja_stage(cfg):
    result = run_windninja(cfg)

    out_dir = Path("out") / "windninja"
    out_dir.mkdir(parents=True, exist_ok=True)

    command_txt = out_dir / "command.txt"
    summary_txt = out_dir / "run_summary.txt"
    stdout_tail_txt = out_dir / "stdout_tail.txt"
    stderr_tail_txt = out_dir / "stderr_tail.txt"
    new_files_txt = out_dir / "new_files.txt"

    commands = result.get("commands", [])
    elapsed_time = result.get("elapsed_time")
    number_time_steps = result.get("number_time_steps")
    dates_correct = result.get("dates_correct")
    dates_commands = result.get("dates_commands", {})
    returncode = result.get("returncode")
    stdout = result.get("stdout", "")
    stderr = result.get("stderr", "")
    new_files = result.get("new_files", [])
    path_output = result.get("path_output")
    config_file = result.get("config_file")
    wx_station_filename = result.get("wx_station_filename")
    elevation_file = result.get("elevation_file")
    mesh_resolution = result.get("mesh_resolution")
    num_threads = result.get("num_threads")

    # command.txt
    command_txt.write_text(
        " ".join(str(x) for x in commands),
        encoding="utf-8",
    )

    # stdout_tail.txt / stderr_tail.txt
    stdout_tail_txt.write_text(stdout[-2000:] if stdout else "", encoding="utf-8")
    stderr_tail_txt.write_text(stderr[-2000:] if stderr else "", encoding="utf-8")

    # new_files.txt
    new_files_txt.write_text(
        "\n".join(str(p) for p in new_files),
        encoding="utf-8",
    )

    # run_summary.txt
    summary_lines = [
        "WINDNINJA RUN SUMMARY",
        "=" * 80,
        "",
        f"returncode: {returncode}",
        f"output_path: {path_output}",
        f"config_file: {config_file}",
        f"wx_station_filename: {wx_station_filename}",
        f"elevation_file: {elevation_file}",
        f"mesh_resolution: {mesh_resolution}",
        f"num_threads: {num_threads}",
        f"dates_correct: {dates_correct}",
        f"number_time_steps: {number_time_steps}",
        f"elapsed_time_s: {elapsed_time}",
        f"n_new_files: {len(new_files)}",
        "",
        "DATES COMMANDS",
        "-" * 80,
    ]

    for k, v in dates_commands.items():
        summary_lines.append(f"{k}: {v}")

    summary_lines.extend([
        "",
        "COMMAND",
        "-" * 80,
        " ".join(str(x) for x in commands),
        "",
        "NEW FILES (first 50)",
        "-" * 80,
    ])

    for p in new_files[:50]:
        summary_lines.append(str(p))

    summary_txt.write_text("\n".join(summary_lines), encoding="utf-8")

    result["command_txt_path"] = command_txt
    result["summary_txt_path"] = summary_txt
    result["stdout_tail_txt_path"] = stdout_tail_txt
    result["stderr_tail_txt_path"] = stderr_tail_txt
    result["new_files_txt_path"] = new_files_txt

    return result


def run_wind_rose_stage(cfg):
    source = cfg.weather_source
    start = parse_date_str(cfg.time_start)
    end = parse_date_str(cfg.time_end)

    if source == "power":
        df = fetch_power_hourly(cfg.lat, cfg.lon, start, end)
    elif source == "era5":
        df = fetch_era5_hourly_point(cfg.lat, cfg.lon, start, end)
    elif source == "aemet":
        raise ValueError("AEMET requiere api_key; este runner aún no la inyecta.")
    else:
        raise ValueError(f"Fuente de viento no soportada: {source}")

    out_dir = Path("out") / "wind_rose"
    out_dir.mkdir(parents=True, exist_ok=True)

    out_csv = out_dir / "wind_source_data.csv"
    out_plot = out_dir / "wind_rose.png"
    out_weibull = out_dir / "weibull_fit.png"

    table, calm_pct = compute_wind_rose_table(df)
    plot_wind_rose(table, calm_pct=calm_pct, title=cfg.wr_title, savepath=out_plot)

    res = fit_weibull_2p(df["WS10M"].values)
    plot_weibull_fit(df["WS10M"].values, res["k"], res["c"], savepath=out_weibull)

    df.to_csv(out_csv, index=True)

    if cfg.wr_csv is not None:
        Path(cfg.wr_csv).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(cfg.wr_csv, index=True)

    return {
        "df": df,
        "table": table,
        "calm_pct": calm_pct,
        "weibull": res,
        "out_csv_path": out_csv,
        "out_plot_path": out_plot,
        "out_weibull_path": out_weibull,
        "cfg_csv_path": cfg.wr_csv,
    }


def run_rename_stage(cfg):
    cases_csv = Path(cfg.out_weather_point_file)
    out_dir = Path(cfg.out_wn)
    dest_dir = Path(cfg.out_wn_ren)

    report_dir = Path("out") / "rename"
    report_dir.mkdir(parents=True, exist_ok=True)

    diag_csv = report_dir / "rename_diagnostics.csv"
    summary_txt = report_dir / "rename_summary.txt"
    plan_csv = report_dir / "rename_plan.csv"

    apply_flag = getattr(cfg, "apply_rename", False)

    plan_df, stats, diag_df = run_rename(
        cases_csv=cases_csv,
        out_dir=out_dir,
        dest_dir=dest_dir,
        diag_csv=diag_csv,
        summary_txt=summary_txt,
        plan_csv=plan_csv,
        prefix="MDT_WN_Corredoria_Grado_point",
        recursive=False,
        apply=apply_flag,
    )

    print(f"[RENAME] apply={apply_flag}")

    return {
        "plan_df": plan_df,
        "stats": stats,
        "diag_df": diag_df,
        "diag_csv_path": diag_csv,
        "summary_txt_path": summary_txt,
        "plan_csv_path": plan_csv,
        "dest_dir": dest_dir,
        "apply": apply_flag,
    }


def run_full_pipeline(cfg):
    results = {}

    results["geometry_dem"] = run_geometry_and_dem(cfg)
    results["towers"] = run_towers(cfg)
    results["line_profile"] = run_line_profile(cfg)
    results["scenarios"] = run_generate_scenarios(cfg)

    return results


def main():
    cfg = load_config_toml(CONFIG_PATH)

    print("=== WIND ROSE ===")
    wind_rose = run_wind_rose_stage(cfg)

    print("Wind rose completado.")
    print(f"CSV: {wind_rose['out_csv_path']}")
    print(f"Rosa: {wind_rose['out_plot_path']}")
    print(f"Weibull: {wind_rose['out_weibull_path']}")

    return {
        "wind_rose": wind_rose,
    }


if __name__ == "__main__":
    main()