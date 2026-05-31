import os
from pathlib import Path
from pathlib import PureWindowsPath

from fastapi import HTTPException


def join_base(base: str | Path, p: str | Path) -> Path:
    base = Path(base)
    p = Path(p)
    return p if p.is_absolute() else (base / p)


def get_cases_root() -> Path:
    return Path(
        os.getenv("CASES_ROOT")
        or os.getenv("HOST_CASES_ROOT")
        or r"C:\Datos_TFG"
    ).expanduser().resolve()


def resolve_case_path(path: str | Path) -> Path:
    raw_path = str(path).strip()
    if not raw_path:
        raise HTTPException(status_code=400, detail="La ruta del caso no puede estar vacía.")

    normalized_raw = raw_path.replace("\\", "/")
    if ".." in normalized_raw.split("/"):
        raise HTTPException(
            status_code=400,
            detail="La ruta del caso no puede contener segmentos '..'.",
        )

    cases_root = get_cases_root()
    host_cases_root = os.getenv("HOST_CASES_ROOT")
    relative_path: str | None = None
    if host_cases_root:
        normalized_host = host_cases_root.replace("\\", "/").rstrip("/")

        if normalized_raw.lower() == normalized_host.lower():
            relative_path = ""

        host_prefix = f"{normalized_host}/"
        if normalized_raw.lower().startswith(host_prefix.lower()):
            relative_path = normalized_raw[len(host_prefix):]

    if relative_path is not None:
        candidate = cases_root / relative_path
    else:
        raw = Path(raw_path).expanduser()
        is_windows_absolute = PureWindowsPath(raw_path).is_absolute()
        candidate = raw if raw.is_absolute() or is_windows_absolute else cases_root / raw

    resolved = candidate.resolve()
    try:
        resolved.relative_to(cases_root)
    except ValueError as exc:
        raise HTTPException(
            status_code=403,
            detail="La ruta del caso debe permanecer dentro de CASES_ROOT.",
        ) from exc

    return resolved


def normalize_case_path(path: str | Path) -> Path:
    """Backward-compatible alias for the safe case path resolver."""
    return resolve_case_path(path)
