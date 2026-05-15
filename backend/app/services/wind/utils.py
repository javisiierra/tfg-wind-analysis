from __future__ import annotations

from typing import Tuple

import numpy as np


def uv_to_ws_wd(u: np.ndarray, v: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Convert U/V wind components into speed and meteorological direction.

    Returns:
        tuple[np.ndarray, np.ndarray]:
            - WS in m/s
            - WD in meteorological degrees (0-360, direction *from* where wind blows)
    """
    ws = np.sqrt(u * u + v * v)
    wd = (np.degrees(np.arctan2(-u, -v)) + 360.0) % 360.0
    return ws, wd
