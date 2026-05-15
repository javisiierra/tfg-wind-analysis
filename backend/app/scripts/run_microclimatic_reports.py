from pathlib import Path
import traceback

from app.core.config import load_config_toml
from scripts.run_local_pipeline import run_full_pipeline


CONFIGS_DIR = Path("configs")
CONFIG_PATTERN = "*.toml"


def find_config_files(configs_dir: Path, pattern: str = "*.toml") -> list[Path]:
    configs_dir = Path(configs_dir)
    if not configs_dir.exists():
        raise FileNotFoundError(f"No existe el directorio de configuraciones: {configs_dir}")

    files = sorted(configs_dir.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No se encontraron ficheros con patrón '{pattern}' en {configs_dir}")

    return files


def run_case(config_path: Path) -> dict:
    print("=" * 80)
    print(f"Ejecutando caso: {config_path}")
    print("=" * 80)

    cfg = load_config_toml(config_path)
    results = run_full_pipeline(cfg)

    return {
        "config": str(config_path),
        "status": "ok",
        "results": results,
    }


def run_cases(config_paths: list[Path]) -> list[dict]:
    summary = []

    for config_path in config_paths:
        try:
            result = run_case(config_path)
            summary.append(result)
            print(f"[OK] Caso completado: {config_path}")
        except Exception as e:
            print(f"[ERROR] Falló el caso: {config_path}")
            print(f"Motivo: {e}")
            traceback.print_exc()

            summary.append(
                {
                    "config": str(config_path),
                    "status": "error",
                    "error": str(e),
                }
            )

    return summary


def print_summary(summary: list[dict]) -> None:
    print("\n" + "#" * 80)
    print("RESUMEN DE EJECUCIÓN")
    print("#" * 80)

    total = len(summary)
    ok = sum(1 for x in summary if x["status"] == "ok")
    err = total - ok

    print(f"Total casos:   {total}")
    print(f"Correctos:     {ok}")
    print(f"Con errores:   {err}")
    print("")

    if err:
        print("Casos con error:")
        for item in summary:
            if item["status"] == "error":
                print(f" - {item['config']}: {item['error']}")


def main():
    config_files = find_config_files(CONFIGS_DIR, CONFIG_PATTERN)
    summary = run_cases(config_files)
    print_summary(summary)
    return summary


if __name__ == "__main__":
    main()