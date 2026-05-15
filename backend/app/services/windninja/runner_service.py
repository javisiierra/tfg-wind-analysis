import os
import subprocess
import time
from pathlib import Path

from app.core.paths import join_base
from app.services.windninja.command_builder import (
    build_windninja_commands,
    get_dates_commands,
)


def run_windninja(cfg):
    base = Path(cfg.general_path)

    wind_ninja_exe = r"C:\WindNinja\WindNinja-3.12.1\bin\WindNinja_cli"
    wx_station_filename = join_base(base, cfg.in_weather_file)
    elevation_file = join_base(base, cfg.out_mdt_tif)
    path_output = join_base(base, cfg.out_wn)
    BASE_DIR = Path(__file__).resolve().parents[3]
    config_file = str(BASE_DIR / "config" / "windninja" / "config.cfg")

    wx_station_filename = str(wx_station_filename)
    elevation_file = str(elevation_file)
    path_output = str(path_output)

    print("wx_station_filename:", wx_station_filename)
    print("elevation_file:", elevation_file)
    print("path_output:", path_output)

    dates_commands, dates_correct = get_dates_commands(wx_station_filename)

    print("Número de fechas correctas en el archivo de estaciones:", dates_correct)
    if dates_correct:
        dates_commands

    mesh_resolution = None
    num_threads = None
    number_time_steps = None
    commands = []
    elapsed_time = None
    returncode = None
    stdout = ""
    stderr = ""
    new_files = []

    if dates_correct:
        print("--------- Ejecutando WindNinja ---------")
        mesh_resolution = cfg.mesh_resolution
        num_threads = cfg.num_threads
        number_time_steps = False
        # number_time_steps = 3

        if number_time_steps:
            dates_commands["--number_time_steps"] = number_time_steps
        else:
            number_time_steps = dates_commands["--number_time_steps"]

        print("--------- Antes de try: ")
        print("wx_station_filename:", wx_station_filename)

        start_time = time.time()
        commands = build_windninja_commands(
            wind_ninja_exe=wind_ninja_exe,
            elevation_file=elevation_file,
            wx_station_filename=wx_station_filename,
            path_output=path_output,
            config_file=config_file,
            mesh_resolution=mesh_resolution,
            num_threads=num_threads,
            dates_commands=dates_commands,
        )

        # 1) Asegura que el directorio existe
        out_dir = Path(path_output)
        out_dir.mkdir(parents=True, exist_ok=True)

        # 2) Snapshot antes
        before = {p.resolve() for p in out_dir.glob("**/*") if p.is_file()}

        t0 = time.time()

        # 3) Ejecuta capturando salida
        res = subprocess.run(commands, capture_output=True, text=True)

        dt = time.time() - t0
        elapsed_time = time.time() - start_time
        returncode = res.returncode
        stdout = res.stdout or ""
        stderr = res.stderr or ""

        print("Return code:", returncode)
        print("Elapsed [s]:", dt)

        if stdout:
            print("\n--- STDOUT (tail) ---\n", stdout[-2000:])
        if stderr:
            print("\n--- STDERR (tail) ---\n", stderr[-2000:])

        # 4) Snapshot después
        after = [p for p in out_dir.glob("**/*") if p.is_file()]
        new_files = [p for p in after if p.resolve() not in before]

        print("\nNuevos ficheros en output_path:", len(new_files))
        for p in sorted(new_files, key=lambda x: x.stat().st_mtime, reverse=True)[:20]:
            print("  ", p)

        # 5) Si no aparece nada, mira también la carpeta del DEM
        dem_dir = Path(elevation_file).parent
        dem_out = [p for p in dem_dir.glob("*") if p.is_file()]
        print("\nCarpeta DEM:", dem_dir)
        print("Ficheros (muestra):", [p.name for p in dem_out[:20]])

        # IMPORTANTE: deja desactivado el borrado hasta verificar salidas reales
        # time.sleep(3); delete_format_files(path_output)

    print(" ")
    print("Print Results")
    print("#" * 80)
    print(f"Mesh_resolution: {mesh_resolution}")
    print(f"Num_threads: {num_threads}")
    print(f"Mumber_time_steps: {number_time_steps}")

    print(" ")
    print(f"Tiempo Total: {elapsed_time} s")
    if number_time_steps:
        print(f"Tiempo Sim_i: {elapsed_time/number_time_steps} s")
    else:
        print("Tiempo Sim_i: N/A")
    print(" ")

    time.sleep(3)

    print(" ")
    print("All Commands")
    for i in range(1, len(commands) - 1, 2):
        print(f" {commands[i]}: {commands[i+1]}")
    print(" ")
    print(commands)
    print(" ")

    return {
        "dates_commands": dates_commands,
        "dates_correct": dates_correct,
        "commands": commands,
        "elapsed_time": elapsed_time,
        "number_time_steps": number_time_steps,
        "mesh_resolution": mesh_resolution,
        "num_threads": num_threads,
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
        "new_files": new_files,
        "path_output": path_output,
        "config_file": config_file,
        "wx_station_filename": wx_station_filename,
        "elevation_file": elevation_file,
    }