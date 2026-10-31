"""Demo marşrut strukturunu və son GPS/bildiriş məlumatını yaddaşa yükləyir.

Marşrut xətti real yol geometriyası DEYİL: ardıcıl dayanacaqları birləşdirən sxematik xəttdir.
Avtobusun xətt boyunca məsafəsi YALNIZ lat/lon-dan proyeksiya ilə tapılır (real GPS ilə eyni yol).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from bisect import bisect_right

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import Settings
from ..geo import Polyline
from ..models import Bus, CrowdReport, Direction, DirectionStop, GpsPosition, Route
from .crowd import ReportSeries


@dataclass
class StopInfo:
    seq: int
    pk: int
    stop_id: str
    name: str
    lat: float
    lon: float
    d: float  # xətt boyunca məsafə (m)


@dataclass
class GpsPoint:
    t: datetime
    lat: float
    lon: float
    speed: float | None
    progress: float  # xətt boyunca proyeksiya olunmuş məsafə (m)
    offset: float  # xəttdən kənarlaşma (m)


@dataclass
class DirData:
    direction: Direction
    route: Route
    stops: list[StopInfo]
    poly: Polyline
    buses: list[Bus]  # is_active=True olanlar
    gps: dict[int, list[GpsPoint]] = field(default_factory=dict)
    reports: dict[int, ReportSeries] = field(default_factory=dict)
    _gps_times: dict[int, list[datetime]] = field(default_factory=dict)

    @property
    def length(self) -> float:
        return self.poly.length

    def bus_codes(self) -> dict[int, str]:
        return {b.id: b.code for b in self.buses}

    def has_fresh_gps(self, bus_id: int, t: datetime, stale_seconds: int) -> bool:
        times = self._gps_times.get(bus_id)
        if not times:
            return False
        i = bisect_right(times, t) - 1
        return i >= 0 and (t - times[i]).total_seconds() <= stale_seconds

    def active_at(self, settings: Settings):
        """t anında AKTİV (is_active və təzə GPS-i olan) avtobusların id siyahısını verən funksiya."""

        def fn(t: datetime) -> list[int]:
            return [b.id for b in self.buses if self.has_fresh_gps(b.id, t, settings.gps_stale_seconds)]

        return fn

    def last_gps(self, bus_id: int) -> GpsPoint | None:
        pts = self.gps.get(bus_id)
        return pts[-1] if pts else None


def build_poly(stops: list[StopInfo]) -> Polyline:
    return Polyline.from_points([(s.lat, s.lon) for s in stops])


_STOP_D_CACHE: dict[tuple, list[float]] = {}


def stop_infos(direction: Direction) -> tuple[list[StopInfo], Polyline]:
    rows = sorted(direction.stops, key=lambda ds: ds.seq)
    raw = [
        StopInfo(ds.seq, ds.stop.id, ds.stop.stop_id, ds.stop.name, ds.stop.lat, ds.stop.lon, 0.0) for ds in rows
    ]
    if direction.geometry:  # real AYNA xətt geometriyası: dayanacaqları xətt boyunca monoton yerləşdir
        poly = Polyline.from_points([(la, lo) for la, lo in direction.geometry])
        key = (direction.id, len(direction.geometry), tuple(direction.geometry[0]), tuple(direction.geometry[-1]), tuple(s.pk for s in raw))
        ds = _STOP_D_CACHE.get(key)
        if ds is None:
            ds = poly.project_stops([(s.lat, s.lon) for s in raw])
            if len(_STOP_D_CACHE) > 200:
                _STOP_D_CACHE.clear()
            _STOP_D_CACHE[key] = ds
        for s, d in zip(raw, ds):
            s.d = d
    else:  # sxematik demo xətti: dayanacaqları düz xətlərlə birləşdirir
        poly = build_poly(raw)
        for i, s in enumerate(raw):
            s.d = poly.cum[i]
    return raw, poly


def load_all(session: Session, now: datetime, settings: Settings, lookback_minutes: float | None = None) -> list[DirData]:
    """Bütün demo istiqamətlər üçün son `lookback_minutes` GPS + (lookback+pəncərə) bildirişlər."""
    lookback = lookback_minutes or max(
        settings.interval_lookback_minutes,
        settings.persistence_cap_minutes + 1,
        settings.slow_lookback_minutes,
    )
    directions = (
        session.execute(
            select(Direction)
            .join(Route)
            .where(Route.is_demo.is_(True))
            .options(
                selectinload(Direction.stops).selectinload(DirectionStop.stop),
                selectinload(Direction.buses),
                selectinload(Direction.route),
            )
            .order_by(Route.id, Direction.ordinal)
        )
        .scalars()
        .all()
    )
    out: list[DirData] = []
    all_bus_ids: list[int] = []
    for d in directions:
        stops, poly = stop_infos(d)
        buses = [b for b in d.buses if b.is_active]
        out.append(DirData(direction=d, route=d.route, stops=stops, poly=poly, buses=buses))
        all_bus_ids += [b.id for b in buses]
    if not all_bus_ids:
        return out

    gps_from = now - timedelta(minutes=lookback) - timedelta(seconds=settings.gps_stale_seconds)
    gps_rows = session.execute(
        select(GpsPosition)
        .where(GpsPosition.bus_id.in_(all_bus_ids), GpsPosition.recorded_at >= gps_from, GpsPosition.recorded_at <= now)
        .order_by(GpsPosition.bus_id, GpsPosition.recorded_at)
    ).scalars()
    gps_by_bus: dict[int, list[GpsPosition]] = {}
    for r in gps_rows:
        gps_by_bus.setdefault(r.bus_id, []).append(r)

    rep_from = now - timedelta(minutes=lookback + settings.crowd_window_minutes)
    rep_rows = session.execute(
        select(CrowdReport)
        .where(CrowdReport.bus_id.in_(all_bus_ids), CrowdReport.created_at > rep_from, CrowdReport.created_at <= now)
        .order_by(CrowdReport.bus_id, CrowdReport.created_at)
    ).scalars()
    rep_by_bus: dict[int, list[tuple[datetime, int, str]]] = {}
    for r in rep_rows:
        rep_by_bus.setdefault(r.bus_id, []).append((r.created_at, r.level, r.source))

    for dd in out:
        for b in dd.buses:
            pts: list[GpsPoint] = []
            hint: float | None = None
            for r in gps_by_bus.get(b.id, []):
                # real xətt özünü kəsə bilər: əvvəlki mövqeyə yaxın hissəni seç
                prog, off = dd.poly.project_hint(r.lat, r.lon, hint)
                hint = prog
                pts.append(GpsPoint(r.recorded_at, r.lat, r.lon, r.speed_mps, prog, off))
            dd.gps[b.id] = pts
            dd._gps_times[b.id] = [p.t for p in pts]
            if b.id in rep_by_bus:
                dd.reports[b.id] = ReportSeries(rep_by_bus[b.id])
    return out


def unwrap(points: list[GpsPoint], length: float) -> list[tuple[datetime, float]]:
    """Dövrə vuran xəttdə (son dayanacaqdan başa qayıdış) proqresi fasiləsiz ardıcıllığa çevir."""
    out: list[tuple[datetime, float]] = []
    offset = 0.0
    prev: float | None = None
    for p in points:
        if prev is not None and p.progress - prev < -length / 2:
            offset += length
        out.append((p.t, p.progress + offset))
        prev = p.progress
    return out


def displacement_speed(points: list[GpsPoint], length: float) -> list[tuple[datetime, float]]:
    """Ardıcıl GPS nöqtələri arasında (xətt boyunca) hesablanmış orta sürət (m/s), (t_son, sürət)."""
    un = unwrap(points, length)
    res: list[tuple[datetime, float]] = []
    for (t1, p1), (t2, p2) in zip(un, un[1:]):
        dt = (t2 - t1).total_seconds()
        if dt <= 0:
            continue
        res.append((t2, max(0.0, (p2 - p1)) / dt))
    return res
