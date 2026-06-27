"""Lanzador manual del pipeline.

Las etapas reutilizables viven en ``app.services.pipeline.stages``. Este módulo
solo interpreta argumentos de consola, carga la configuración y ejecuta la
etapa solicitada.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from app.core.config import load_config_toml
from app.services.pipeline.stages import (
    run_full_pipeline,
    run_generate_scenarios,
    run_geometry_and_dem,
    run_line_profile,
    run_rename_stage,
    run_towers,
    run_wind_rose_stage,
    run_windninja_stage,
)


STAGES = ("full", "wind-rose", "windninja", "rename")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ejecuta manualmente una etapa del pipeline usando un config.toml.",
    )
    parser.add_argument(
        "config",
        type=Path,
        help="Ruta al archivo config.toml del caso.",
    )
    parser.add_argument(
        "--stage",
        choices=STAGES,
        default="wind-rose",
        help="Etapa a ejecutar (por defecto: wind-rose).",
    )
    parser.add_argument(
        "--dry-run-rename",
        action="store_true",
        help="En la etapa rename, genera el plan sin mover/copiar archivos.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> dict:
    args = build_parser().parse_args(argv)
    cfg = load_config_toml(args.config)

    if args.stage == "full":
        return run_full_pipeline(cfg)
    if args.stage == "windninja":
        return run_windninja_stage(cfg)
    if args.stage == "rename":
        return run_rename_stage(cfg, apply=not args.dry_run_rename)

    result = run_wind_rose_stage(cfg)
    print("Wind rose completado.")
    print(f"CSV: {result['out_csv_path']}")
    print(f"Rosa: {result['out_plot_path']}")
    print(f"Weibull: {result['out_weibull_path']}")
    return {"wind_rose": result}


if __name__ == "__main__":
    main()
