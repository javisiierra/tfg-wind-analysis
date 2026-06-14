from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from app.services.wind import wind_rose_runner_service as service


def _cfg(tmp_path: Path, source: str, wr_csv: Path | None = None):
    return SimpleNamespace(
        weather_source=source,
        time_start="2024-01-01",
        time_end="2024-01-02",
        lat=43.36,
        lon=-5.85,
        wr_title="Demo wind rose",
        wr_csv=wr_csv,
    )


def _wind_df():
    return pd.DataFrame(
        {
            "WS10M": [1.0, 2.0, 3.0],
            "WD10M": [10.0, 90.0, 180.0],
        },
        index=pd.date_range("2024-01-01", periods=3, freq="h"),
    )


def _stub_processing(monkeypatch):
    calls = {}
    table = pd.DataFrame({"[0, 2)": [100.0]}, index=["000-022"])

    def _compute(df):
        calls["compute_df"] = df
        return table, 0.0

    def _plot_wind(table_arg, *, calm_pct, title, savepath):
        calls["wind_plot"] = {
            "table": table_arg,
            "calm_pct": calm_pct,
            "title": title,
            "savepath": savepath,
        }

    def _fit(values):
        calls["fit_values"] = list(values)
        return {"k": 2.0, "c": 5.0}

    def _plot_weibull(values, k, c, savepath):
        calls["weibull_plot"] = {
            "values": list(values),
            "k": k,
            "c": c,
            "savepath": savepath,
        }

    monkeypatch.setattr(service, "compute_wind_rose_table", _compute)
    monkeypatch.setattr(service, "plot_wind_rose", _plot_wind)
    monkeypatch.setattr(service, "fit_weibull_2p", _fit)
    monkeypatch.setattr(service, "plot_weibull_fit", _plot_weibull)
    return calls


def test_run_wind_rose_for_cfg_power_fetches_and_writes_outputs(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    calls = _stub_processing(monkeypatch)
    source_df = _wind_df()

    def _fetch_power(lat, lon, start, end):
        calls["fetch_power"] = (lat, lon, start, end)
        return source_df

    monkeypatch.setattr(service, "fetch_power_hourly", _fetch_power)
    cfg_csv = tmp_path / "case" / "WR" / "wind_power.csv"

    result = service.run_wind_rose_for_cfg(_cfg(tmp_path, "power", wr_csv=cfg_csv))

    assert calls["fetch_power"] == (43.36, -5.85, date(2024, 1, 1), date(2024, 1, 2))
    assert result["out_csv_path"] == Path("out") / "wind_rose" / "wind_source_data.csv"
    assert result["out_plot_path"] == Path("out") / "wind_rose" / "wind_rose.png"
    assert result["out_weibull_path"] == Path("out") / "wind_rose" / "weibull_fit.png"
    assert result["cfg_csv_path"] == cfg_csv
    assert (tmp_path / result["out_csv_path"]).exists()
    assert cfg_csv.exists()
    assert calls["wind_plot"]["title"] == "Demo wind rose"
    assert calls["weibull_plot"]["k"] == 2.0
    assert calls["weibull_plot"]["c"] == 5.0


def test_run_wind_rose_for_cfg_era5_fetches(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    calls = _stub_processing(monkeypatch)

    def _fetch_era5(lat, lon, start, end):
        calls["fetch_era5"] = (lat, lon, start, end)
        return _wind_df()

    monkeypatch.setattr(service, "fetch_era5_hourly_point", _fetch_era5)

    result = service.run_wind_rose_for_cfg(_cfg(tmp_path, "era5"))

    assert calls["fetch_era5"] == (43.36, -5.85, date(2024, 1, 1), date(2024, 1, 2))
    assert result["cfg_csv_path"] is None
    assert (tmp_path / result["out_csv_path"]).exists()


def test_run_wind_rose_for_cfg_aemet_keeps_current_error(tmp_path):
    with pytest.raises(ValueError, match="AEMET requiere api_key"):
        service.run_wind_rose_for_cfg(_cfg(tmp_path, "aemet"))
