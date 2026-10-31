"""GPS simulyatoru (backend daxilində). Real GPS çıxışı hələ yoxdur: bütün avtobuslar SİMULYASİYADIR.

Hərəkət marşrut xətti (real AYNA geometriyası, yoxdursa sxematik demo xətti) boyunca sabit nominal sürətlə gedir; ssenarilər yalnız
`direction.sim_params` ilə təsvir olunur:
  slow_segments: [{start_m, end_m, factor}]   -> həmin hissədə sürət * factor
  halt: {bus_code, progress_m}                -> bu avtobus həmin nöqtəyə çatanda dayanır
Simulyator GPS-i (lat/lon/sürət) DB-yə yazır; analiz kodu isə bu nöqtələri xətlə proyeksiya edərək
real GPS ilə eyni yolla işləyir (simulyatorun daxili 'progress' dəyəri analizə verilmir).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import Settings
from ..geo import Polyline
from ..models import Bus, Direction, DirectionStop, GpsPosition
from .transit import stop_infos

MAX_GAP_SECONDS = 120  # server dayanıbsa simulyasiyanı "pauza" kimi davam etdir


def step_bus(bus: Bus, direction: Direction, poly: Polyline, now: datetime, tick_seconds: int) -> GpsPosition | None:
    """Avtobusu `now` anına qədər irəli apar və GPS nöqtəsi qaytar (session-a əlavə etmir)."""
    length = poly.length
    if bus.last_tick_at is None:
        bus.last_tick_at = now
        lat, lon, heading = poly.point_at(bus.progress_m)
        return GpsPosition(bus_id=bus.id, recorded_at=now, lat=lat, lon=lon, speed_mps=0.0, heading_deg=heading)

    dt = (now - bus.last_tick_at).total_seconds()
    if dt <= 0:
        return None
    if dt > MAX_GAP_SECONDS:
        dt = float(tick_seconds)

    params = direction.sim_params or {}
    speed = direction.nominal_speed_mps
    if bus.mode == "halted":
        speed = 0.0
    else:
        for seg in params.get("slow_segments", []):
            if seg["start_m"] <= bus.progress_m < seg["end_m"]:
                speed *= float(seg["factor"])
        advance = speed * dt
        halt = params.get("halt")
        if halt and halt.get("bus_code") == bus.code:
            to_halt = (float(halt["progress_m"]) - bus.progress_m) % length
            if to_halt <= advance:
                bus.progress_m = float(halt["progress_m"])
                bus.mode = "halted"
                speed = 0.0
                advance = 0.0
        bus.progress_m = (bus.progress_m + advance) % length

    bus.last_tick_at = now
    lat, lon, heading = poly.point_at(bus.progress_m)
    return GpsPosition(bus_id=bus.id, recorded_at=now, lat=lat, lon=lon, speed_mps=round(speed, 3), heading_deg=heading)


def _load_dirs(session: Session) -> list[tuple[Direction, Polyline]]:
    directions = (
        session.execute(
            select(Direction).where(Direction.buses.any(Bus.is_active.is_(True))).options(
                selectinload(Direction.stops).selectinload(DirectionStop.stop),
                selectinload(Direction.buses),
            )
        )
        .scalars()
        .all()
    )
    out = []
    for d in directions:
        if not d.stops:
            continue
        _, poly = stop_infos(d)  # real AYNA geometriyası (varsa) və ya sxematik demo xətti: analizlə eyni xətt
        out.append((d, poly))
    return out


def tick(session: Session, now: datetime, settings: Settings) -> int:
    """Bütün aktiv avtobusları `now` anına irəli apar. Yazılan GPS sayını qaytarır."""
    n = 0
    for direction, poly in _load_dirs(session):
        for bus in direction.buses:
            if not bus.is_active:
                continue
            pt = step_bus(bus, direction, poly, now, settings.sim_tick_seconds)
            if pt is not None:
                session.add(pt)
                n += 1
    session.flush()
    return n


def backfill(session: Session, start: datetime, end: datetime, step_seconds: int, settings: Settings) -> int:
    """`start`-dan `end`-ə qədər eyni addım funksiyası ilə tarixçə GPS-i yarat (vahid kod yolu)."""
    dirs = _load_dirs(session)
    for direction, poly in dirs:
        for bus in direction.buses:
            if bus.is_active:
                bus.last_tick_at = None
    n = 0
    t = start
    # ilk nöqtə (start anında mövqe)
    for direction, poly in dirs:
        for bus in direction.buses:
            if bus.is_active:
                pt = step_bus(bus, direction, poly, t, settings.sim_tick_seconds)
                if pt:
                    session.add(pt)
                    n += 1
    while t < end:
        t = min(t + timedelta(seconds=step_seconds), end)
        for direction, poly in dirs:
            for bus in direction.buses:
                if bus.is_active:
                    pt = step_bus(bus, direction, poly, t, settings.sim_tick_seconds)
                    if pt:
                        session.add(pt)
                        n += 1
    session.flush()
    return n
