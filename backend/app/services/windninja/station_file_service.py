from pathlib import Path

def _resolve_station_csv(wx_station_filename: str, station_entry: str) -> str:
    """
    Resuelve rutas de CSV de estación:
    - Si `station_entry` es absoluta -> se usa tal cual.
    - Si es relativa -> se interpreta relativa al directorio de `wx_station_filename`.
    """
    base_dir = Path(wx_station_filename).expanduser().resolve().parent
    s = str(station_entry).strip().strip('"').strip("'")
    p = Path(s)

    if p.is_absolute():
        return str(p)
    return str((base_dir / p).resolve())