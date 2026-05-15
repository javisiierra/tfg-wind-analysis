from pathlib import Path

def join_base(base: str | Path, p: str | Path) -> Path:
    base = Path(base)
    p = Path(p)
    return p if p.is_absolute() else (base / p)