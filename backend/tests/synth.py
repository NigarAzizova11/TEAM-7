"""SİNTETİK test məlumatı (REAL DEYİL).

dayanacaqlar.csv faylının real formatını təqlid edir: `ID,AD,ID,LONGITUDE,LATITUDE,Tip`
(təkrarlanan ID başlığı, sıfırla başlayan stop_id, boş Tip, eyni adlı müxtəlif dayanacaqlar).
Real fayl layihəyə daxil edilməyib; bu yalnız avtomatik testlər üçündür.
"""
from __future__ import annotations

from pathlib import Path

N_STOPS = 3600
LAT0, LAT_STEP = 40.330, 0.0020
LON0, LON_STEP = 49.800, 0.0025
GRID = 60


def synthetic_rows() -> list[list[str]]:
    rows = []
    i = 0
    for a in range(GRID):
        for b in range(GRID):
            i += 1
            lat = LAT0 + a * LAT_STEP
            lon = LON0 + b * LON_STEP
            name = "Eyni Ad" if i % 50 == 0 else f"Sintetik dayanacaq {i}"
            tip = "" if i % 3 == 0 else "Avtobus"
            rows.append([str(i), name, f"{i:05d}", f"{lon:.6f}", f"{lat:.6f}", tip])
    assert len(rows) == N_STOPS
    return rows


def write_csv(path: Path, rows: list[list[str]] | None = None, header: str = "ID,AD,ID,LONGITUDE,LATITUDE,Tip", bom: bool = False) -> Path:
    rows = rows if rows is not None else synthetic_rows()
    lines = [header] + [",".join(f'"{c}"' if "," in c else c for c in r) for r in rows]
    data = "\n".join(lines) + "\n"
    path.write_bytes((("﻿" if bom else "") + data).encode("utf-8"))
    return path
