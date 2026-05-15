from pathlib import Path
from types import SimpleNamespace
import importlib
import sys
import types

import pytest

from app.services.dem import fetch_dem_service as dem
from app.services.windninja import command_builder as cb

sys.modules.setdefault("xarray", types.SimpleNamespace(open_dataset=lambda _: None, Dataset=object))
sys.modules.setdefault("pandas", types.SimpleNamespace(to_datetime=lambda v, utc=True: v))
era5 = importlib.import_module("app.services.weather.era5_service")


def test_fetch_dem_builds_command_and_handles_success(monkeypatch):
    monkeypatch.setattr(dem, "utm_rect_to_fetch_dem_bbox", lambda *_: (50, 2, 40, -3))
    monkeypatch.setattr(dem.shutil, "which", lambda name: "/usr/local/bin/fetch_dem")
    captured = {}

    def fake_run(cmd, capture_output, text, env):
        captured["cmd"] = cmd
        captured["env"] = env
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(dem.subprocess, "run", fake_run)
    cfg = SimpleNamespace(out_mdt_tif="/tmp/mdt.tif")

    result = dem.fetch_dem_from_bounds(cfg, 1, 2, 3, 4)
    assert result.returncode == 0
    assert captured["cmd"][0] == "/usr/local/bin/fetch_dem"
    assert "--bbox" in captured["cmd"]


def test_fetch_dem_passes_srtm_api_key(monkeypatch):
    monkeypatch.setattr(dem, "utm_rect_to_fetch_dem_bbox", lambda *_: (50, 2, 40, -3))
    monkeypatch.setattr(dem.shutil, "which", lambda name: "/usr/local/bin/fetch_dem")
    monkeypatch.setenv("OPENTOPOGRAPHY_API_KEY", "secret")
    captured = {}

    def fake_run(cmd, capture_output, text, env):
        captured["env"] = env
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(dem.subprocess, "run", fake_run)
    cfg = SimpleNamespace(out_mdt_tif="/tmp/mdt.tif")

    dem.fetch_dem_from_bounds(cfg, 1, 2, 3, 4)

    assert captured["env"]["CUSTOM_SRTM_API_KEY"] == "secret"


def test_fetch_dem_reports_missing_srtm_api_key(monkeypatch):
    monkeypatch.setattr(dem, "utm_rect_to_fetch_dem_bbox", lambda *_: (50, 2, 40, -3))
    monkeypatch.setattr(dem.shutil, "which", lambda name: "/usr/local/bin/fetch_dem")

    def fake_run(cmd, capture_output, text, env):
        return SimpleNamespace(
            returncode=252,
            stdout="",
            stderr="ERROR 1: SRTM download failed. No API key specified.",
        )

    monkeypatch.setattr(dem.subprocess, "run", fake_run)
    cfg = SimpleNamespace(out_mdt_tif="/tmp/mdt.tif")

    with pytest.raises(RuntimeError, match="falta la API key de OpenTopography"):
        dem.fetch_dem_from_bounds(cfg, 1, 2, 3, 4)


def test_fetch_dem_reports_bad_srtm_api_key(monkeypatch):
    monkeypatch.setattr(dem, "utm_rect_to_fetch_dem_bbox", lambda *_: (50, 2, 40, -3))
    monkeypatch.setattr(dem.shutil, "which", lambda name: "/usr/local/bin/fetch_dem")

    def fake_run(cmd, capture_output, text, env):
        return SimpleNamespace(
            returncode=252,
            stdout="",
            stderr="ERROR 1: HTTP error code : 401\nERROR 1: Failed to download file, bad API key.",
        )

    monkeypatch.setattr(dem.subprocess, "run", fake_run)
    cfg = SimpleNamespace(out_mdt_tif="/tmp/mdt.tif")

    with pytest.raises(RuntimeError, match="OpenTopography rechazo la API key"):
        dem.fetch_dem_from_bounds(cfg, 1, 2, 3, 4)


def test_fetch_dem_reports_missing_binary(monkeypatch):
    monkeypatch.setattr(dem, "utm_rect_to_fetch_dem_bbox", lambda *_: (50, 2, 40, -3))
    monkeypatch.setattr(dem.shutil, "which", lambda name: None)

    cfg = SimpleNamespace(out_mdt_tif="/tmp/mdt.tif")

    with pytest.raises(RuntimeError, match="No se encontró el ejecutable 'fetch_dem'"):
        dem.fetch_dem_from_bounds(cfg, 1, 2, 3, 4)


def test_get_dates_commands_parses_station_file(tmp_path: Path, monkeypatch):
    master = tmp_path / "stations.csv"
    child = tmp_path / "st01.csv"
    master.write_text("Station_File_List\nst01.csv\n", encoding="utf-8")
    child.write_text("date_time\n2024-01-01T00:00:00Z\n2024-01-01T01:00:00Z\n", encoding="utf-8")

    class _Series:
        def __init__(self, values):
            self.iloc = values

    class _Frame:
        def __init__(self, rows):
            self._rows = rows

        def __getitem__(self, key):
            return _Series([r[key] for r in self._rows])

        def __len__(self):
            return len(self._rows)

    def _read_csv(path, **_kwargs):
        if str(path).endswith("stations.csv"):
            return _Frame([{"Station_File_List": "st01.csv"}])
        return _Frame(
            [
                {"date_time": SimpleNamespace(year=2024, month=1, day=1, hour=0, minute=0)},
                {"date_time": SimpleNamespace(year=2024, month=1, day=1, hour=1, minute=0)},
            ]
        )

    monkeypatch.setattr(cb.pd, "read_csv", _read_csv)
    cmds, ok = cb.get_dates_commands(str(master))

    assert ok is True
    assert cmds["--number_time_steps"] == 2
    assert cmds["--start_year"] == 2024


def test_build_windninja_commands_formats_dates():
    commands = cb.build_windninja_commands(
        "WindNinja_cli", "dem.tif", "stations.csv", "out", "cfg.cfg", 100, 4,
        {"--start_month": 1, "--stop_month": 12},
    )
    assert commands[0] == "WindNinja_cli"
    assert "--start_month" in commands
    assert "01" in commands


def test_expand_bbox_validates_and_expands():
    out = era5._expand_bbox_for_era5_grid([0, 0, 0.1, 0.1], min_size_deg=0.75)
    assert (out[2] - out[0]) >= 0.75

    with pytest.raises(ValueError):
        era5._expand_bbox_for_era5_grid([1, 1, 0, 0])


def test_analyze_hourly_wind_dataset_uses_uv_conversion(monkeypatch):
    class FakeDS(dict):
        coords = {"time": [0, 1]}
        variables = {"u10": 1, "v10": 1}
        dims = {"time": 2}

        def __init__(self):
            self["u10"] = SimpleNamespace(dims=("time",), values=[1.0, 2.0])
            self["v10"] = SimpleNamespace(dims=("time",), values=[0.0, 0.0])
            self["time"] = SimpleNamespace(values=["2024-01-01", "2024-01-01T01:00:00Z"])

        def close(self):
            return None

    monkeypatch.setattr(era5.xr, "open_dataset", lambda _: FakeDS())
    monkeypatch.setattr(era5, "uv_to_ws_wd", lambda u, v: ([1.0, 2.0], [180.0, 190.0]))

    class FakeDF:
        columns = ["WS10M", "WD10M"]
        index = SimpleNamespace(name=None)

        def replace(self, *_a, **_k):
            return self

        def dropna(self):
            return self

        def sort_index(self):
            return self

        def __len__(self):
            return 2

    monkeypatch.setattr(era5, "pd", types.SimpleNamespace(
        to_datetime=lambda *a, **k: ["t1", "t2"],
        DatetimeIndex=lambda v: v,
        DataFrame=lambda *a, **k: FakeDF(),
    ))
    monkeypatch.setattr(era5, "np", types.SimpleNamespace(
        asarray=lambda v: types.SimpleNamespace(ravel=lambda: v),
        inf=float("inf"),
        nan=float("nan"),
    ))

    df = era5.analyze_hourly_wind_dataset("dummy.nc")
    assert df.columns == ["WS10M", "WD10M"]
    assert len(df) == 2
