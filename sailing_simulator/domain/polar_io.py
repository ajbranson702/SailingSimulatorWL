from __future__ import annotations

import csv
import json
from pathlib import Path

from sailing_simulator.domain.models import Polar


def save_polar(polar: Polar, path: str | Path) -> None:
    target = Path(path)
    if target.suffix.lower() == ".csv":
        save_polar_csv(polar, target)
        return
    save_polar_json(polar, target)


def load_polar(path: str | Path) -> Polar:
    source = Path(path)
    if source.suffix.lower() == ".csv":
        return load_polar_csv(source)
    return load_polar_json(source)


def save_polar_json(polar: Polar, path: str | Path) -> None:
    Path(path).write_text(
        json.dumps(
            {
                "name": polar.name,
                "speeds_by_tws_and_twa": polar.speeds_by_tws_and_twa,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def load_polar_json(path: str | Path) -> Polar:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    speeds = {
        float(tws): {float(twa): float(speed) for twa, speed in angles.items()}
        for tws, angles in data.get("speeds_by_tws_and_twa", {}).items()
    }
    return Polar(name=data.get("name", "Imported Polar"), speeds_by_tws_and_twa=speeds or Polar().speeds_by_tws_and_twa)


def save_polar_csv(polar: Polar, path: str | Path) -> None:
    wind_angles = sorted({angle for speeds in polar.speeds_by_tws_and_twa.values() for angle in speeds})
    with Path(path).open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["TWS/TWA", *[f"{angle:g}" for angle in wind_angles]])
        for wind_speed, speeds in sorted(polar.speeds_by_tws_and_twa.items()):
            writer.writerow([f"{wind_speed:g}", *[speeds.get(angle, "") for angle in wind_angles]])


def load_polar_csv(path: str | Path) -> Polar:
    with Path(path).open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.reader(file)
        rows = [row for row in reader if row and any(cell.strip() for cell in row)]

    if len(rows) < 2:
        raise ValueError("Polar CSV must include a header row and at least one wind-speed row.")

    angles = [float(value) for value in rows[0][1:]]
    speeds_by_tws_and_twa: dict[float, dict[float, float]] = {}
    for row in rows[1:]:
        true_wind_speed = float(row[0])
        speeds_by_tws_and_twa[true_wind_speed] = {}
        for angle, raw_speed in zip(angles, row[1:]):
            if raw_speed.strip():
                speeds_by_tws_and_twa[true_wind_speed][angle] = float(raw_speed)

    return Polar(name=Path(path).stem, speeds_by_tws_and_twa=speeds_by_tws_and_twa)
