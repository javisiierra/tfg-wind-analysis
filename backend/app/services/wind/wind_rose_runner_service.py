from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.wind.source_service import (
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


def run_wind_rose_for_cfg(cfg) -> dict[str, Any]:
    source = cfg.weather_source
    start = parse_date_str(cfg.time_start)
    end = parse_date_str(cfg.time_end)

    if source == "power":
        df = fetch_power_hourly(cfg.lat, cfg.lon, start, end)
    elif source == "era5":
        df = fetch_era5_hourly_point(cfg.lat, cfg.lon, start, end)
    elif source == "aemet":
        raise ValueError("AEMET requiere api_key; este runner a\u00fan no la inyecta.")
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
