import pandas as pd


def parse_number(value) -> float:
    """
    Convierte a float:
    - Si viene como número de Excel (int/float), lo convierte directamente.
    - Si viene como string, acepta:
        1.234.567,89  (EU)
        1234567,89    (EU sin miles)
        1234567.89    (US)
        1.234.567     (miles)
    Nota: NO intenta “inventar” decimales: eso se hace en la fase de escalado.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        raise ValueError("Valor vacío/NaN")

    # Si ya es numérico (Excel), no hay separadores que interpretar
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)

    s = str(value).strip()
    if s == "":
        raise ValueError("Cadena vacía")

    s = s.replace(" ", "").replace("'", "")

    # EU: punto miles + coma decimal
    if "," in s and "." in s:
        return float(s.replace(".", "").replace(",", "."))

    # EU: coma decimal
    if "," in s and "." not in s:
        return float(s.replace(",", "."))

    # Solo puntos: si hay >1, asume miles
    if "." in s and s.count(".") > 1:
        return float(s.replace(".", ""))

    # Resto: float estándar
    return float(s)


def parse_xyz_with_autoscale(value, kind: str) -> float:
    """
    Convierte a float y corrige el caso típico de Excel “sin decimales”
    donde el valor real está en milésimas (×1/1000), eligiendo la versión
    que cae en el rango plausible para cada coordenada.

    kind: 'x', 'y', 'z'
    """
    v = parse_number(value)

    # Rangos plausibles (ETRS89/UTM): ajusta si procede
    ranges = {
        "x": (100_000.0, 900_000.0),
        "y": (0.0, 10_000_000.0),
        "z": (-500.0, 9_000.0),
    }
    lo, hi = ranges[kind]

    # Si ya está en rango, OK
    if lo <= v <= hi:
        return v

    # Probar escalado milésimas (muy típico en estos ficheros)
    v1 = v / 1000.0
    if lo <= v1 <= hi:
        return v1

    # (Opcional) Si trabajases con centésimas, podrías habilitar /100, pero aquí no lo activo para no “inventar”.
    # v2 = v / 100.0

    return v  # si no encaja, devuelve el valor original (para detectar anomalías)