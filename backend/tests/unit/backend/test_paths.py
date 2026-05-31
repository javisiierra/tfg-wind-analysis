from pathlib import Path

import pytest
from fastapi import HTTPException

from app.core.paths import normalize_case_path, resolve_case_path


def test_normalize_case_path_maps_host_root_to_container_root(monkeypatch):
    monkeypatch.setenv("CASES_ROOT", "/data")
    monkeypatch.setenv("HOST_CASES_ROOT", "C:/Datos_TFG")

    assert normalize_case_path("C:/Datos_TFG/linea") == Path("/data/linea").resolve()


def test_normalize_case_path_maps_relative_case_to_container_root(monkeypatch):
    monkeypatch.setenv("CASES_ROOT", "/data")
    monkeypatch.setenv("HOST_CASES_ROOT", "C:/Datos_TFG")

    assert normalize_case_path("linea") == Path("/data/linea").resolve()


def test_resolve_case_path_accepts_path_inside_cases_root(monkeypatch, tmp_path):
    cases_root = tmp_path / "cases"
    case_path = cases_root / "linea"
    case_path.mkdir(parents=True)
    monkeypatch.setenv("CASES_ROOT", str(cases_root))
    monkeypatch.delenv("HOST_CASES_ROOT", raising=False)

    assert resolve_case_path(case_path) == case_path.resolve()


def test_resolve_case_path_rejects_parent_traversal(monkeypatch, tmp_path):
    monkeypatch.setenv("CASES_ROOT", str(tmp_path / "cases"))
    monkeypatch.delenv("HOST_CASES_ROOT", raising=False)

    with pytest.raises(HTTPException) as exc_info:
        resolve_case_path("../outside")

    assert exc_info.value.status_code == 400
    assert "segmentos '..'" in exc_info.value.detail


def test_resolve_case_path_rejects_absolute_path_outside_cases_root(monkeypatch, tmp_path):
    monkeypatch.setenv("CASES_ROOT", str(tmp_path / "cases"))
    monkeypatch.delenv("HOST_CASES_ROOT", raising=False)

    with pytest.raises(HTTPException) as exc_info:
        resolve_case_path(tmp_path / "outside")

    assert exc_info.value.status_code == 403
    assert "dentro de CASES_ROOT" in exc_info.value.detail
