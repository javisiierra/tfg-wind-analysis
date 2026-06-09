from pathlib import Path

from app.core.paths import normalize_case_path


def test_normalize_case_path_maps_host_root_to_container_root(monkeypatch):
    monkeypatch.setenv("CASES_ROOT", "/data")
    monkeypatch.setenv("HOST_CASES_ROOT", "C:/Ruta/A/Tus/Casos")

    assert normalize_case_path("C:/Ruta/A/Tus/Casos/linea") == Path("/data/linea")


def test_normalize_case_path_maps_relative_case_to_container_root(monkeypatch):
    monkeypatch.setenv("CASES_ROOT", "/data")
    monkeypatch.setenv("HOST_CASES_ROOT", "C:/Ruta/A/Tus/Casos")

    assert normalize_case_path("linea") == Path("/data/linea")
