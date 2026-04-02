from __future__ import annotations

from typing import Optional, Sequence

import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.special import gamma
from scipy.stats import kstest, weibull_min


def compute_wind_rose_table(
    df: pd.DataFrame,
    *,
    speed_col: str = "WS10M",
    dir_col: str = "WD10M",
    n_sectors: int = 16,
    speed_bins: Sequence[float] = (0, 2, 4, 6, 8, 10, 15, np.inf),
    calm_threshold: float = 0.5,
) -> tuple[pd.DataFrame, float]:
    """
    Devuelve:
      - tabla (%) por sector direccional x tramo de velocidad
      - porcentaje de calmas

    Convención de dirección:
      0° = Norte, 90° = Este (meteorológica, dirección de procedencia).
    """
    work = df[[speed_col, dir_col]].copy()
    work = work.replace([np.inf, -np.inf], np.nan).dropna()
    if work.empty:
        raise ValueError("No hay datos válidos en speed_col/dir_col.")

    ws = work[speed_col].astype(float).to_numpy()
    wd = np.mod(work[dir_col].astype(float).to_numpy(), 360.0)

    calm_mask = ws < float(calm_threshold)
    calm_pct = 100.0 * calm_mask.mean()

    # Excluir calmas de la rosa
    ws = ws[~calm_mask]
    wd = wd[~calm_mask]
    if ws.size == 0:
        # tabla vacía pero consistente
        labels = [f"{i:03.0f}-{(i + 360 / n_sectors):03.0f}" for i in np.arange(0, 360, 360 / n_sectors)]
        cols = pd.IntervalIndex.from_breaks(speed_bins, closed="left")
        return pd.DataFrame(0.0, index=labels, columns=[str(c) for c in cols]), calm_pct

    # Sectores centrados en N: bins desplazados medio sector
    sector_width = 360.0 / n_sectors
    sector_edges = np.linspace(-sector_width / 2, 360.0 - sector_width / 2, n_sectors + 1)
    wd_shift = (wd + sector_width / 2) % 360.0
    sector_idx = np.floor(wd_shift / sector_width).astype(int) % n_sectors

    # Tramos de velocidad
    speed_bins = np.asarray(speed_bins, dtype=float)
    if len(speed_bins) < 2 or not np.all(np.diff(speed_bins) > 0):
        raise ValueError("speed_bins debe ser estrictamente creciente y tener al menos 2 bordes.")
    speed_idx = np.digitize(ws, speed_bins, right=False) - 1
    valid = (speed_idx >= 0) & (speed_idx < len(speed_bins) - 1)

    sector_idx = sector_idx[valid]
    speed_idx = speed_idx[valid]

    counts = np.zeros((n_sectors, len(speed_bins) - 1), dtype=float)
    for si, vi in zip(sector_idx, speed_idx):
        counts[si, vi] += 1.0

    # A porcentaje sobre el total NO-calma
    counts_pct = 100.0 * counts / counts.sum()

    # Etiquetas
    sector_labels = []
    for k in range(n_sectors):
        a = (k * sector_width) % 360.0
        b = ((k + 1) * sector_width) % 360.0
        sector_labels.append(f"{a:03.0f}-{b:03.0f}")

    bin_labels = []
    for a, b in zip(speed_bins[:-1], speed_bins[1:]):
        if np.isinf(b):
            bin_labels.append(f"[{a:g}, inf)")
        else:
            bin_labels.append(f"[{a:g}, {b:g})")

    table = pd.DataFrame(counts_pct, index=sector_labels, columns=bin_labels)
    return table, calm_pct


def plot_wind_rose(
    table_pct: pd.DataFrame,
    *,
    calm_pct: Optional[float] = None,
    title: Optional[str] = None,
    cmap: str = "viridis",
    figsize: tuple[float, float] = (8, 8),
    savepath: Optional[str] = None,
):
    """
    Dibuja una rosa de vientos apilada a partir de una tabla (%) sector x bins velocidad.
    `table_pct` debe venir de `compute_wind_rose_table`.
    """
    if table_pct.empty:
        raise ValueError("table_pct está vacía.")

    n_sectors = len(table_pct.index)
    theta = np.linspace(0.0, 2 * np.pi, n_sectors, endpoint=False)
    width = 2 * np.pi / n_sectors

    fig = plt.figure(figsize=figsize)
    ax = fig.add_subplot(111, polar=True)

    # Convención meteorológica: Norte arriba, sentido horario
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)

    vals = table_pct.to_numpy()
    bottoms = np.zeros(n_sectors)

    colors = mpl.colormaps[cmap](np.linspace(0.15, 0.95, vals.shape[1]))

    for j, col in enumerate(table_pct.columns):
        ax.bar(theta, vals[:, j], width=width, bottom=bottoms, align="edge", label=str(col), color=colors[j], edgecolor="white", linewidth=0.5)
        bottoms += vals[:, j]

    if title:
        if calm_pct is not None:
            ax.set_title(f"{title}\nCalmas: {calm_pct:.1f}%", va="bottom")
        else:
            ax.set_title(title, va="bottom")
    elif calm_pct is not None:
        ax.set_title(f"Calmas: {calm_pct:.1f}%", va="bottom")

    ax.legend(loc="lower left", bbox_to_anchor=(1.05, 0.0), title="Velocidad")
    fig.tight_layout()

    if savepath:
        fig.savefig(savepath, dpi=150, bbox_inches="tight")
    
    plt.close(fig)
    return fig, ax


def fit_weibull_2p(
    ws: np.ndarray | Sequence[float],
):
    """
    fit_weibull_2p.

    Notes
    -----
    Auto-generated docstring. Please refine parameter/return descriptions if needed.
    """
    ws = np.asarray(ws, dtype=float)
    ws = ws[np.isfinite(ws) & (ws > 0)]
    if ws.size < 10:
        raise ValueError("Se necesitan al menos 10 valores de velocidad > 0 para ajustar Weibull.")

    # Ajuste MLE con loc fijado a 0
    k, loc, c = weibull_min.fit(ws, floc=0)

    # Estadísticos básicos
    mean_emp = ws.mean()
    std_emp = ws.std(ddof=1)

    mean_theo = c * gamma(1.0 + 1.0 / k)
    var_theo = c**2 * (gamma(1.0 + 2.0 / k) - gamma(1.0 + 1.0 / k) ** 2)
    std_theo = np.sqrt(var_theo)

    # Bondad de ajuste KS
    D, p_value = kstest(ws, "weibull_min", args=(k, 0, c))

    return {
        "k": float(k),  # shape
        "c": float(c),  # scale
        "mean_emp": float(mean_emp),
        "std_emp": float(std_emp),
        "mean_weibull": float(mean_theo),
        "std_weibull": float(std_theo),
        "ks_D": float(D),
        "ks_pvalue": float(p_value),
        "n": int(ws.size),
    }


def plot_weibull_fit(
    ws: np.ndarray | Sequence[float],
    k: float,
    c: float,
    bins: int = 30,
    density: bool = True,
    title: Optional[str] = None,
    savepath: Optional[str] = None,
):
    """
    Dibuja histograma empírico + PDF Weibull ajustada y CDF empírica vs CDF Weibull.
    """
    ws = np.asarray(ws, dtype=float)
    ws = ws[np.isfinite(ws) & (ws >= 0)]

    x = np.linspace(0, max(ws.max() * 1.05, c * 4), 500)
    pdf = weibull_min.pdf(x, k, loc=0, scale=c)
    cdf = weibull_min.cdf(x, k, loc=0, scale=c)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))

    # Hist + PDF
    ax = axes[0]
    ax.hist(ws, bins=bins, density=density, alpha=0.35)
    ax.plot(x, pdf, linewidth=2)
    ax.set_xlabel("Velocidad del viento")
    ax.set_ylabel("Densidad" if density else "Frecuencia")
    ax.set_title(title or f"Weibull ajustada (k={k:.3f}, c={c:.3f})")
    ax.grid(True, alpha=0.25)

    # CDF empírica + CDF ajustada
    ax = axes[1]
    ws_sorted = np.sort(ws)
    ecdf_y = np.arange(1, len(ws_sorted) + 1) / len(ws_sorted)
    ax.step(ws_sorted, ecdf_y, where="post", label="ECDF")
    ax.plot(x, cdf, label="CDF Weibull", linewidth=2)
    ax.set_xlabel("Velocidad del viento")
    ax.set_ylabel("Probabilidad acumulada")
    ax.set_title("CDF empírica vs Weibull")
    ax.grid(True, alpha=0.25)
    ax.legend()

    fig.tight_layout()
    if savepath:
        fig.savefig(savepath, dpi=150, bbox_inches="tight")

    plt.close(fig)
    return fig, axes