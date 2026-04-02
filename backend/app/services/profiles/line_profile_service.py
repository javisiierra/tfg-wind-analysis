from pathlib import Path

import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from app.services.towers.towers_validation_service import (
    parse_number,
    parse_xyz_with_autoscale,
)


def build_line_profile_df(
    cfg,
    col_x: str = "X",
    col_y: str = "Y",
    col_z: str = "Z",
    matricula: str = "Structure Comment",
) -> pd.DataFrame:
    # --- Lectura y parseo ---
    xlsx_path = cfg.in_xlsx
    df = pd.read_excel(xlsx_path, engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]

    work = df.copy()
    work["x_m"] = work[col_x].apply(lambda v: parse_xyz_with_autoscale(v, "x"))
    work["y_m"] = work[col_y].apply(lambda v: parse_xyz_with_autoscale(v, "y"))
    work["z_m"] = work[col_z].apply(lambda v: parse_xyz_with_autoscale(v, "z"))
    work = work[np.isfinite(work["x_m"]) & np.isfinite(work["y_m"]) & np.isfinite(work["z_m"])].reset_index(drop=True)

    # --- Distancia acumulada en planta y perfil ---
    dx = work["x_m"].diff()
    dy = work["y_m"].diff()
    work["d_xy_m"] = np.sqrt(dx**2 + dy**2).fillna(0.0)
    work["s_xy_m"] = work["d_xy_m"].cumsum()

    # Labeling
    label_col = "Structure Comment" if "Structure Comment" in work.columns else ("Structure" if "Structure" in work.columns else None)
    work["apoyo"] = work[label_col].astype(str).str.strip() if label_col else [f"{i+1}" for i in range(len(work))]

    return work


def compute_profile_stats(work: pd.DataFrame) -> dict:
    # Índices de los extremos
    idx_max = work["z_m"].idxmax()
    idx_min = work["z_m"].idxmin()

    # Valores
    altura_max = work.loc[idx_max, "z_m"]
    altura_min = work.loc[idx_min, "z_m"]

    # Apoyos asociados
    apoyo_max = work.loc[idx_max, "apoyo"]
    apoyo_min = work.loc[idx_min, "apoyo"]

    # Desnivel
    desnivel = altura_max - altura_min

    print(f"Altura máxima: {altura_max:.2f} m (Apoyo: {apoyo_max})")
    print(f"Altura mínima: {altura_min:.2f} m (Apoyo: {apoyo_min})")
    print(f"Desnivel: {desnivel:.2f} m")

    return {
        "idx_max": idx_max,
        "idx_min": idx_min,
        "altura_max": altura_max,
        "altura_min": altura_min,
        "apoyo_max": apoyo_max,
        "apoyo_min": apoyo_min,
        "desnivel": desnivel,
    }


def plot_profile_by_distance(work: pd.DataFrame, savepath=None):
    mpl.rcParams.update({
        "text.usetex": False,
        "font.family": "serif",
        "mathtext.fontset": "cm",
    })

    fig, ax = plt.subplots(figsize=(9, 4.8))

    fig.patch.set_facecolor("white")
    ax.set_facecolor("#ffe5e0")

    ax.plot(
        work["s_xy_m"],
        work["z_m"],
        marker="o",
        linewidth=1,
    )

    ax.set_xlabel(r"Distancia acumulada entre apoyos (m) [$\sqrt{\Delta E^2 + \Delta N^2}$]")
    ax.set_ylabel(r"Cota $z$ (m)")

    n = len(work)
    step = max(1, n // 20)

    for i in range(0, n, step):
        ax.annotate(
            work["apoyo"].iloc[i],
            (work["s_xy_m"].iloc[i], work["z_m"].iloc[i]),
            textcoords="offset points",
            xytext=(0, 6),
            ha="center",
            fontsize=8,
        )

    ax.grid(True)
    plt.tight_layout()

    if savepath is not None:
        Path(savepath).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(savepath, bbox_inches="tight")

    plt.close(fig)
    return fig, ax


def plot_profile_by_distance_inverted(work: pd.DataFrame, savepath=None):
    fig1, ax1 = plt.subplots(figsize=(9, 4.8))
    ax1.plot(work["s_xy_m"], work["z_m"], marker="o", linewidth=1)

    ax1.set_xlabel("Distancia acumulada entre apoyos (m) [√(ΔE²+ΔN²)]")
    ax1.set_ylabel("Cota z (m)")

    ax1.invert_xaxis()

    n = len(work)
    step = max(1, n // 20)
    for i in range(0, n, step):
        ax1.annotate(
            work["apoyo"].iloc[i],
            (work["s_xy_m"].iloc[i], work["z_m"].iloc[i]),
            textcoords="offset points",
            xytext=(0, 6),
            ha="center",
            fontsize=8,
        )

    ax1.grid(True)
    plt.tight_layout()

    if savepath is not None:
        Path(savepath).parent.mkdir(parents=True, exist_ok=True)
        fig1.savefig(savepath, bbox_inches="tight")

    plt.close(fig1)
    return fig1, ax1


def plot_profile_by_x(work: pd.DataFrame, cfg, savepath=None):
    fig, ax = plt.subplots(figsize=(9, 4.8))

    ax.plot(work["x_m"], work["z_m"], marker="o", linewidth=1)

    ax.set_xlabel("Coordenada X UTM (m)")
    ax.set_ylabel("Cota z (m)")

    ax.invert_xaxis()

    n = len(work)
    step = max(1, n // 20)
    for i in range(0, n, step):
        ax.annotate(
            work["apoyo"].iloc[i],
            (work["x_m"].iloc[i], work["z_m"].iloc[i]),
            textcoords="offset points",
            xytext=(0, 6),
            ha="center",
            fontsize=8
        )

    ax.grid(True)
    plt.tight_layout()

    final_path = savepath if savepath is not None else cfg.out_perfil_file
    Path(final_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(final_path, dpi=300, bbox_inches="tight")

    plt.close(fig)

    return fig, ax