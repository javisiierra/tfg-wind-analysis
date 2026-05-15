import os
from pathlib import Path


def join_base(base: str | Path, p: str | Path) -> Path:
    base = Path(base)
    p = Path(p)
    return p if p.is_absolute() else (base / p)


def normalize_case_path(path: str | Path) -> Path:
    raw_path = str(path)
    cases_root = os.getenv("CASES_ROOT")
    host_cases_root = os.getenv("HOST_CASES_ROOT")

    if cases_root and host_cases_root:
        normalized_raw = raw_path.replace("\\", "/")
        normalized_host = host_cases_root.replace("\\", "/").rstrip("/")

        if normalized_raw.lower() == normalized_host.lower():
            return Path(cases_root)

        host_prefix = f"{normalized_host}/"
        if normalized_raw.lower().startswith(host_prefix.lower()):
            relative = normalized_raw[len(host_prefix):]
            return Path(cases_root) / relative

    return Path(raw_path)
