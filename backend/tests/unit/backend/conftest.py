import sys
from pathlib import Path
from types import SimpleNamespace
from importlib.util import find_spec


BACKEND_ROOT = Path(__file__).resolve().parents[3]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


if "fastapi" not in sys.modules and find_spec("fastapi") is None:
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str | None = None):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    sys.modules["fastapi"] = SimpleNamespace(HTTPException=HTTPException)

if find_spec("numpy") is None:
    sys.modules.setdefault(
        "numpy",
        SimpleNamespace(
            array=lambda rows, dtype=object: rows,
            isclose=lambda seq, val, atol=0: [x == val for x in seq],
        ),
    )

if find_spec("pyproj") is None:
    sys.modules.setdefault(
        "pyproj",
        SimpleNamespace(Transformer=SimpleNamespace(from_crs=lambda *a, **k: SimpleNamespace(transform=lambda x, y: (x, y)))),
    )

if find_spec("pandas") is None:
    sys.modules.setdefault("pandas", SimpleNamespace(read_csv=lambda *a, **k: None, to_datetime=lambda v, utc=True: v))
