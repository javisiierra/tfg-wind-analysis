from __future__ import annotations

from collections import Counter
from pathlib import Path
import re

import pandas as pd


# Si tus ficheros terminan exactamente en _vel.asc / _vel.prj (sin 100m_):
SUFFIX_RE = re.compile(r"(_(?:ang|cld|vel)\.(?:asc|prj))$", re.IGNORECASE)

# Si en realidad terminan como _100m_vel.asc / _100m_vel.prj y quieres conservar "100m_",
# comenta la línea anterior y usa esta:
# SUFFIX_RE = re.compile(r"(_[^_]*?(?:ang|cld|vel)\.(?:asc|prj))$", re.IGNORECASE)

EXPECTED_SUFFIXES = {
    "_ang.asc", "_ang.prj",
    "_cld.asc", "_cld.prj",
    "_vel.asc", "_vel.prj",
}

WN_FILE_RE = re.compile(
    r"^(?P<prefix>.+?)_"
    r"(?P<dt>\d{2}-\d{2}-\d{4}_\d{4})_"
    r"(?P<res>\d+(?:\.\d+)?m)_"
    r"(?P<var>ang|cld|vel)\."
    r"(?P<ext>asc|prj)$",
    re.IGNORECASE
)


# ============================================================
# FUNCIONES DE FORMATEO
# ============================================================

def fmt_datetime(dt_str: str) -> str:
    dt = pd.to_datetime(dt_str, utc=True, errors="raise")
    return dt.strftime("%m-%d-%Y_%H%M")


def fmt_dir(deg: float) -> str:
    s = f"{deg:.1f}"
    int_part, dec_part = s.split(".")
    return f"{int(int_part):03d}_{dec_part}"


def fmt_speed(spd: float) -> str:
    s = f"{spd:.1f}"
    int_part, dec_part = s.split(".")
    return f"{int(int_part):02d}_{dec_part}"


# ============================================================
# LISTADO DE FICHEROS
# ============================================================

def iter_files(out_dir: Path, recursive: bool):
    return out_dir.rglob("*") if recursive else out_dir.glob("*")


def list_candidate_files(out_dir: Path, recursive: bool) -> dict[str, Path]:
    """
    Devuelve un mapa:
      nombre_de_fichero -> Path completo
    Solo para ficheros que cumplen SUFFIX_RE.
    """
    if recursive:
        it = out_dir.rglob("*")
    else:
        it = out_dir.glob("*")

    name_to_path: dict[str, Path] = {}
    for p in it:
        if p.is_file() and SUFFIX_RE.search(p.name):
            # Nota: si hubiera colisiones de nombre en subcarpetas distintas,
            # la última sobrescribiría. Si ese es tu caso, conviene guardar relative_path.
            name_to_path[p.name] = p
    return name_to_path


def list_candidate_files_index(out_dir: Path, recursive: bool) -> list[Path]:
    files = []
    for p in iter_files(out_dir, recursive):
        if p.is_file() and WN_FILE_RE.match(p.name):
            files.append(p)
    return files


def build_index_by_datetime(out_dir: Path, recursive: bool) -> dict[str, dict[str, Path]]:
    """
    Índice:
    {
        '01-04-2025_1745': {
            '_ang.asc': Path(...),
            '_ang.prj': Path(...),
            '_cld.asc': Path(...),
            '_cld.prj': Path(...),
            '_vel.asc': Path(...),
            '_vel.prj': Path(...),
        },
        ...
    }
    """
    idx: dict[str, dict[str, Path]] = {}

    for p in list_candidate_files_index(out_dir, recursive):
        m = WN_FILE_RE.match(p.name)
        if not m:
            continue

        dt_key = m.group("dt")
        suffix = f"_{m.group('var').lower()}.{m.group('ext').lower()}"

        if dt_key not in idx:
            idx[dt_key] = {}

        idx[dt_key][suffix] = p

    return idx


# ============================================================
# PLAN DE RENOMBRADO
# ============================================================

def build_plan_names_only(
    cases_csv: Path,
    out_dir: Path,
    prefix: str,
    date_col: str,
    dir_col: str,
    speed_col: str,
    recursive: bool,
) -> tuple[pd.DataFrame, dict]:
    if not cases_csv.exists():
        raise FileNotFoundError(f"No existe CASES_CSV: {cases_csv}")
    if not out_dir.exists() or not out_dir.is_dir():
        raise NotADirectoryError(f"No existe OUT_DIR o no es un directorio: {out_dir}")

    df = pd.read_csv(cases_csv)
    for c in (date_col, dir_col, speed_col):
        if c not in df.columns:
            raise KeyError(f"Columna '{c}' no encontrada en {cases_csv}. Columnas: {list(df.columns)}")

    df["dt_key"] = df[date_col].map(fmt_datetime)
    df["dir_key"] = df[dir_col].map(fmt_dir)
    df["spd_key"] = df[speed_col].map(fmt_speed)

    df["target_base"] = (
        prefix + "_" +
        df["dir_key"] + "_" +
        df["spd_key"] + "_" +
        df["dt_key"]
    )

    name_to_path = list_candidate_files(out_dir, recursive=recursive)
    candidate_names = list(name_to_path.keys())

    plan_rows = []
    missing_cases = []
    incomplete_cases = []

    for _, row in df.iterrows():
        dt_key = row["dt_key"]
        base = row["target_base"]

        matches = []
        for n in candidate_names:
            m = re.search(r"\d{2}-\d{2}-\d{4}_\d{4}", n)
            if m and m.group(0) == dt_key:
                matches.append(n)

        if not matches:
            missing_cases.append(dt_key)
            continue

        # extrae sufijos distintos encontrados
        found: dict[str, str] = {}  # suffix -> old_name
        for old_name in matches:
            m = SUFFIX_RE.search(old_name)
            if not m:
                continue
            suffix = m.group(1).lower()
            found[suffix] = old_name

        # Verificación suave: deben existir 6 ficheros distintos
        if len(found) != 6:
            incomplete_cases.append((dt_key, f"se encontraron {len(found)} ficheros (esperados 6)"))

        for suffix, old_name in found.items():
            new_name = base + suffix
            plan_rows.append((old_name, new_name, dt_key, suffix))

    plan_df = pd.DataFrame(plan_rows, columns=["old_name", "new_name", "dt_key", "suffix"])

    # calcular timestamps únicos encontrados
    timestamps_found = set()
    for name in candidate_names:
        m = re.search(r"\d{2}-\d{2}-\d{4}_\d{4}", name)
        if m:
            timestamps_found.add(m.group(0))

    stats = {
        "n_cases": int(df.shape[0]),
        "n_candidates": int(len(candidate_names)),
        "n_datetimes_found": len(timestamps_found),
        "n_complete_cases": int(df.shape[0] - len(missing_cases)),
        "n_renames": int(plan_df.shape[0]),
        "missing_cases": missing_cases,
        "incomplete_cases": incomplete_cases,
    }

    return plan_df, stats


# ============================================================
# APLICACIÓN DEL PLAN
# ============================================================

def apply_plan_names_only2(plan_df: pd.DataFrame, out_dir: Path, recursive: bool) -> dict:
    """
    Aplica el renombrado usando:
      old_path = (ruta real del fichero antiguo)
      new_path = old_path.with_name(new_name)
    Para resolver old_name->Path, se crea un diccionario name->Path desde el directorio.
    """
    name_to_path = list_candidate_files(out_dir, recursive=recursive)

    missing_files = []
    collisions = []
    applied = 0

    for _, r in plan_df.iterrows():
        old_name = str(r["old_name"])
        new_name = str(r["new_name"])

        old_path = name_to_path.get(old_name)
        if old_path is None or not old_path.exists():
            missing_files.append(old_name)
            continue

        new_path = old_path.with_name(new_name)
        if new_path.exists():
            collisions.append(new_name)
            continue

        old_path.rename(new_path)
        applied += 1

        # actualiza el diccionario para renombres posteriores
        del name_to_path[old_name]
        name_to_path[new_name] = new_path

    return {"applied": applied, "missing_files": missing_files, "collisions": collisions}


def apply_plan_names_only(plan_df: pd.DataFrame, out_dir: Path, dest_dir: Path, recursive: bool) -> dict:
    """
    Aplica el renombrado MOVIENDO los ficheros desde out_dir a dest_dir con el nombre nuevo.
    El plan contiene solo nombres (old_name, new_name).
    """
    dest_dir.mkdir(parents=True, exist_ok=True)

    name_to_path = list_candidate_files(out_dir, recursive=recursive)

    missing_files = []
    collisions = []
    applied = 0

    for _, r in plan_df.iterrows():
        old_name = str(r["old_name"])
        new_name = str(r["new_name"])

        old_path = name_to_path.get(old_name)
        if old_path is None or not old_path.exists():
            missing_files.append(old_name)
            continue

        dest_path = dest_dir / new_name
        if dest_path.exists():
            collisions.append(new_name)
            continue

        # mueve + renombra
        old_path.replace(dest_path)
        applied += 1

        # actualiza diccionario
        del name_to_path[old_name]

    return {"applied": applied, "missing_files": missing_files, "collisions": collisions}


# ============================================================
# DIAGNÓSTICO Y RESUMEN
# ============================================================

def build_diagnostics_df(
    cases_csv: Path,
    out_dir: Path,
    recursive: bool,
    prefix: str,
    date_col: str,
    dir_col: str,
    speed_col: str,
) -> pd.DataFrame:
    """
    Genera un dataframe de diagnóstico por timestamp esperado.
    """
    df = pd.read_csv(cases_csv).copy()

    df["dt_key"] = df[date_col].map(fmt_datetime)
    df["dir_key"] = df[dir_col].map(fmt_dir)
    df["spd_key"] = df[speed_col].map(fmt_speed)

    df["target_base"] = (
        prefix + "_" +
        df["dir_key"] + "_" +
        df["spd_key"] + "_" +
        df["dt_key"]
    )

    idx = build_index_by_datetime(out_dir, recursive=recursive)

    rows = []
    for _, row in df.iterrows():
        dt_key = row["dt_key"]
        found = idx.get(dt_key, {})

        found_suffixes = set(found.keys())
        missing_suffixes = sorted(EXPECTED_SUFFIXES - found_suffixes)
        extra_suffixes = sorted(found_suffixes - EXPECTED_SUFFIXES)

        rows.append({
            "date_time_original": row[date_col],
            "dt_key": dt_key,
            "dir_deg": row[dir_col],
            "speed": row[speed_col],
            "target_base": row["target_base"],
            "n_found": len(found_suffixes),
            "is_complete": found_suffixes == EXPECTED_SUFFIXES,
            "is_missing": len(found_suffixes) == 0,
            "missing_suffixes": ";".join(missing_suffixes),
            "extra_suffixes": ";".join(extra_suffixes),
            "found_suffixes": ";".join(sorted(found_suffixes)),
        })

    diag_df = pd.DataFrame(rows)
    return diag_df


def summarize_directory(dir_path: Path, recursive: bool = True) -> dict:
    """
    Resume el contenido real de un directorio.
    """
    files = [p for p in (dir_path.rglob("*") if recursive else dir_path.glob("*")) if p.is_file()]
    ext_counter = Counter(p.suffix.lower() for p in files)

    ts_counter = Counter()
    unmatched = []

    for p in files:
        m = WN_FILE_RE.match(p.name)
        if m:
            ts_counter[m.group("dt")] += 1
        else:
            unmatched.append(p.name)

    return {
        "path": str(dir_path.resolve()),
        "n_files": len(files),
        "ext_counter": dict(ext_counter),
        "n_timestamps": len(ts_counter),
        "timestamp_counter_distribution": dict(Counter(ts_counter.values())),
        "unmatched_examples": unmatched[:20],
    }


def write_summary_txt(path: Path, stats: dict, diag_df: pd.DataFrame, out_summary: dict, ren_summary: dict | None = None):
    """
    Escribe un resumen legible en texto.
    """
    lines = []
    lines.append("RENAME SUMMARY")
    lines.append("=" * 80)
    lines.append("")
    lines.append("PLAN")
    lines.append(f"n_cases               : {stats.get('n_cases')}")
    lines.append(f"n_candidates          : {stats.get('n_candidates')}")
    lines.append(f"n_datetimes_found     : {stats.get('n_datetimes_found')}")
    lines.append(f"n_complete_cases      : {stats.get('n_complete_cases')}")
    lines.append(f"n_renames             : {stats.get('n_renames')}")
    lines.append("")

    if "apply_result" in stats:
        ar = stats["apply_result"]
        lines.append("APPLY RESULT")
        lines.append(f"applied               : {ar.get('applied')}")
        lines.append(f"missing_files         : {len(ar.get('missing_files', []))}")
        lines.append(f"collisions            : {len(ar.get('collisions', []))}")
        lines.append("")

    lines.append("DIAGNOSTICS")
    lines.append(f"rows                  : {len(diag_df)}")
    lines.append(f"complete              : {int(diag_df['is_complete'].sum())}")
    lines.append(f"missing               : {int(diag_df['is_missing'].sum())}")
    lines.append(f"incomplete            : {int((~diag_df['is_complete'] & ~diag_df['is_missing']).sum())}")
    lines.append("")

    lines.append("OUT_WN")
    lines.append(f"path                  : {out_summary['path']}")
    lines.append(f"n_files               : {out_summary['n_files']}")
    lines.append(f"n_timestamps          : {out_summary['n_timestamps']}")
    lines.append(f"ext_counter           : {out_summary['ext_counter']}")
    lines.append(f"timestamp_distribution: {out_summary['timestamp_counter_distribution']}")
    if out_summary["unmatched_examples"]:
        lines.append(f"unmatched_examples    : {out_summary['unmatched_examples']}")
    lines.append("")

    if ren_summary is not None:
        lines.append("OUT_WN_REN")
        lines.append(f"path                  : {ren_summary['path']}")
        lines.append(f"n_files               : {ren_summary['n_files']}")
        lines.append(f"n_timestamps          : {ren_summary['n_timestamps']}")
        lines.append(f"ext_counter           : {ren_summary['ext_counter']}")
        lines.append(f"timestamp_distribution: {ren_summary['timestamp_counter_distribution']}")
        if ren_summary["unmatched_examples"]:
            lines.append(f"unmatched_examples    : {ren_summary['unmatched_examples']}")
        lines.append("")

    missing_rows = diag_df[diag_df["is_missing"]]
    if not missing_rows.empty:
        lines.append("MISSING CASES (first 20)")
        for _, r in missing_rows.head(20).iterrows():
            lines.append(f"  {r['dt_key']}")
        lines.append("")

    incomplete_rows = diag_df[(~diag_df["is_complete"]) & (~diag_df["is_missing"])]
    if not incomplete_rows.empty:
        lines.append("INCOMPLETE CASES (first 20)")
        for _, r in incomplete_rows.head(20).iterrows():
            lines.append(f"  {r['dt_key']} -> found={r['found_suffixes']} missing={r['missing_suffixes']}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================

def run_rename(
    cases_csv: Path,
    out_dir: Path,
    dest_dir: Path,
    diag_csv: Path,
    summary_txt: Path,
    plan_csv: Path,
    prefix: str,
    date_col: str = "date_time",
    dir_col: str = "Direction(degrees)",
    speed_col: str = "Speed",
    recursive: bool = False,
    apply: bool = True,
) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    plan_df, stats = build_plan_names_only(
        cases_csv=cases_csv,
        out_dir=out_dir,
        prefix=prefix,
        date_col=date_col,
        dir_col=dir_col,
        speed_col=speed_col,
        recursive=recursive,
    )

    plan_df[["old_name", "new_name"]].to_csv(plan_csv, index=False, encoding="utf-8")

    print(f"[OK] Plan guardado en: {plan_csv}")
    print(f"     Casos CSV:              {stats['n_cases']}")
    print(f"     Ficheros candidatos:    {stats['n_candidates']}")
    print(f"     Date-times encontrados: {stats['n_datetimes_found']}")
    print(f"     Casos completos:        {stats['n_complete_cases']}")
    print(f"     Renombrados previstos:  {stats['n_renames']}")

    if stats["missing_cases"]:
        print(f"[WARN] Casos sin match: {len(stats['missing_cases'])}")
        print("       Ejemplos:", stats["missing_cases"][:10])

    if stats["incomplete_cases"]:
        print(f"[WARN] Casos incompletos: {len(stats['incomplete_cases'])}")
        print("       Ejemplo:", stats["incomplete_cases"][0])

    if apply:
        res = apply_plan_names_only(
            plan_df,
            out_dir=out_dir,
            dest_dir=dest_dir,
            recursive=recursive,
        )
        print(f"[OK] Movidos+renombrados: {res['applied']}")
        if res["missing_files"]:
            print(f"[WARN] Missing files: {len(res['missing_files'])}")
        if res["collisions"]:
            print(f"[WARN] Colisiones: {len(res['collisions'])}")

        stats["apply_result"] = res

    diag_df = build_diagnostics_df(
        cases_csv=cases_csv,
        out_dir=out_dir if not apply else dest_dir,
        recursive=recursive,
        prefix=prefix,
        date_col=date_col,
        dir_col=dir_col,
        speed_col=speed_col,
    )
    diag_df.to_csv(diag_csv, index=False, encoding="utf-8")

    out_summary = summarize_directory(out_dir, recursive=True)
    ren_summary = summarize_directory(dest_dir, recursive=True) if dest_dir.exists() else None

    write_summary_txt(
        path=summary_txt,
        stats=stats,
        diag_df=diag_df,
        out_summary=out_summary,
        ren_summary=ren_summary,
    )

    print(f"[OK] Diagnóstico CSV: {diag_csv}")
    print(f"[OK] Resumen TXT:     {summary_txt}")

    return plan_df, stats, diag_df