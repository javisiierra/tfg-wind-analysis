import os
from pathlib import Path
import pandas as pd

from app.services.windninja.station_file_service import _resolve_station_csv

def get_dates_commands(wx_station_filename):
    print()
    print("CURRENT DIRECTORY:", os.getcwd())
    print()

    wx_station_filename = str(Path(wx_station_filename).expanduser().resolve())
    df0 = pd.read_csv(wx_station_filename, encoding="utf-8-sig")

    # Rutas a los CSV individuales (robusto con rutas relativas/absolutas)
    p1 = _resolve_station_csv(wx_station_filename, df0["Station_File_List"].iloc[0])

    df1 = pd.read_csv(p1, parse_dates=["date_time"], encoding="utf-8-sig")

    bool3 = True  # Solo un archivo, se asume correcto

    dates_commands = {}
    if bool3:
        print(f"CORRECT DATES Dataframes.len = {len(df1)}\n")

        date_start = df1["date_time"].iloc[0]
        date_stop  = df1["date_time"].iloc[-1]

        dates_commands["--number_time_steps"] = len(df1)
        dates_commands["--start_year"]   = date_start.year
        dates_commands["--start_month"]  = date_start.month
        dates_commands["--start_day"]    = date_start.day
        dates_commands["--start_hour"]   = date_start.hour
        dates_commands["--start_minute"] = date_start.minute

        dates_commands["--stop_year"]    = date_stop.year
        dates_commands["--stop_month"]   = date_stop.month
        dates_commands["--stop_day"]     = date_stop.day
        dates_commands["--stop_hour"]    = date_stop.hour
        dates_commands["--stop_minute"]  = date_stop.minute

    dates_correct = bool3
    return dates_commands, dates_correct

def get_dates_commands2(wx_station_filename):
    print()
    print("CURRENT DIRECTORY:", os.getcwd())
    print()

    wx_station_filename = str(Path(wx_station_filename).expanduser().resolve())
    df0 = pd.read_csv(wx_station_filename, encoding="utf-8-sig")

    # Rutas a los CSV individuales (robusto con rutas relativas/absolutas)
    p1 = _resolve_station_csv(wx_station_filename, df0["Station_File_List"].iloc[0])
    p2 = _resolve_station_csv(wx_station_filename, df0["Station_File_List"].iloc[1])

    df1 = pd.read_csv(p1, parse_dates=["date_time"], encoding="utf-8-sig")
    df2 = pd.read_csv(p2, parse_dates=["date_time"], encoding="utf-8-sig")

    bool1 = len(df1) == len(df2)
    bool2 = (df1["date_time"].values == df2["date_time"].values).sum() == len(df1)
    bool3 = bool1 and bool2

    dates_commands = {}
    if bool3:
        print(f"CORRECT DATES Dataframes.len = {len(df1)}\n")

        date_start = df1["date_time"].iloc[0]
        date_stop  = df1["date_time"].iloc[-1]

        dates_commands["--number_time_steps"] = len(df1)
        dates_commands["--start_year"]   = date_start.year
        dates_commands["--start_month"]  = date_start.month
        dates_commands["--start_day"]    = date_start.day
        dates_commands["--start_hour"]   = date_start.hour
        dates_commands["--start_minute"] = date_start.minute

        dates_commands["--stop_year"]    = date_stop.year
        dates_commands["--stop_month"]   = date_stop.month
        dates_commands["--stop_day"]     = date_stop.day
        dates_commands["--stop_hour"]    = date_stop.hour
        dates_commands["--stop_minute"]  = date_stop.minute

    dates_correct = bool3
    return dates_commands, dates_correct

def build_windninja_commands(
    wind_ninja_exe,
    elevation_file,
    wx_station_filename,
    path_output,
    config_file,
    mesh_resolution,
    num_threads,
    dates_commands,
):
    list_dates_commands = []
    for di in dates_commands:
        list_dates_commands.append(di)
        list_dates_commands.append(f"{dates_commands[di]:02d}")
        print(f"{di} {dates_commands[di]:02d}")

    commands = [
        wind_ninja_exe,
        "--elevation_file", elevation_file,
        "--wx_station_filename", wx_station_filename,
        "--output_path", path_output,
        "--config_file", config_file,
        "--time_zone", "Europe/London",
        "--mesh_resolution", f"{mesh_resolution}",
        "--num_threads", f"{num_threads}",
        *list_dates_commands,
    ]

    return commands