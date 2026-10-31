"""Sıxlıq hesablaması: izah edilə bilən orta bal + açıq hədlər.

Aşağı=1, Orta=2, Yüksək=3.
- Avtobus balı = son `crowd_window_minutes` (default 5) dəqiqənin bildirişlərinin ortası.
  Pəncərə (t - pəncərə, t] şəklindədir: ən köhnə sərhəd daxil DEYİL.
- Bildiriş yoxdursa nəticə None-dur ("Məlumat yoxdur"); heç vaxt "Aşağı" sayılmır.
- Xətt balı = yalnız aktual məlumatı olan AKTİV avtobusların balının ortası.
  Əhatə (məlumatı olan / aktiv) `line_min_coverage_ratio`-dan az olarsa xətt nəticəsi yoxdur.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..config import Settings

LEVEL_VALUE = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
LEVEL_NAME = {1: "LOW", 2: "MEDIUM", 3: "HIGH"}


def classify(avg: float, s: Settings) -> str:
    if avg >= s.crowd_high_min:
        return "HIGH"
    if avg <= s.crowd_low_max:
        return "LOW"
    return "MEDIUM"


class ReportSeries:
    """Bir avtobusun bildirişləri (vaxta görə sıralı)."""

    def __init__(self, items: list[tuple[datetime, int, str]]):
        items = sorted(items, key=lambda x: x[0])
        self.times = [i[0] for i in items]
        self.levels = [i[1] for i in items]
        self.sources = [i[2] for i in items]

    def window(self, t: datetime, minutes: float) -> list[int]:
        """(t - minutes, t] aralığındakı indekslər."""
        lo = bisect_right(self.times, t - timedelta(minutes=minutes))
        hi = bisect_right(self.times, t)
        return list(range(lo, hi))


@dataclass
class BusCrowd:
    score: float | None
    level: str | None
    count: int
    user_count: int
    demo_count: int
    latest_age_seconds: float | None


def bus_crowd_at(series: ReportSeries | None, t: datetime, s: Settings) -> BusCrowd:
    if series is None:
        return BusCrowd(None, None, 0, 0, 0, None)
    idx = series.window(t, s.crowd_window_minutes)
    if len(idx) < max(1, s.bus_min_reports):
        return BusCrowd(None, None, len(idx), 0, 0, None)
    avg = sum(series.levels[i] for i in idx) / len(idx)
    demo = sum(1 for i in idx if series.sources[i] == "demo_seed")
    latest = max(series.times[i] for i in idx)
    return BusCrowd(
        score=round(avg, 3),
        level=classify(avg, s),
        count=len(idx),
        user_count=len(idx) - demo,
        demo_count=demo,
        latest_age_seconds=max(0.0, (t - latest).total_seconds()),
    )


@dataclass
class LineCrowd:
    score: float | None
    level: str | None  # None => nəticə yoxdur
    active_buses: int
    buses_with_data: int
    coverage_ratio: float
    reason: str | None  # level None olanda səbəb: no_active_buses | no_data | low_coverage
    latest_report_age_seconds: float | None

    @property
    def is_high(self) -> bool:
        return self.level == "HIGH"


def line_crowd_at(
    series_by_bus: dict[int, ReportSeries],
    active_bus_ids: list[int],
    t: datetime,
    s: Settings,
) -> LineCrowd:
    if not active_bus_ids:
        return LineCrowd(None, None, 0, 0, 0.0, "no_active_buses", None)
    scores: list[float] = []
    ages: list[float] = []
    for bid in active_bus_ids:
        bc = bus_crowd_at(series_by_bus.get(bid), t, s)
        if bc.score is not None:
            scores.append(bc.score)
            if bc.latest_age_seconds is not None:
                ages.append(bc.latest_age_seconds)
    n_active, n_data = len(active_bus_ids), len(scores)
    ratio = n_data / n_active
    latest_age = min(ages) if ages else None
    if n_data == 0:
        return LineCrowd(None, None, n_active, 0, 0.0, "no_data", None)
    if ratio < s.line_min_coverage_ratio:
        return LineCrowd(None, None, n_active, n_data, ratio, "low_coverage", latest_age)
    avg = sum(scores) / n_data
    return LineCrowd(round(avg, 3), classify(avg, s), n_active, n_data, ratio, None, latest_age)


def high_persistence_seconds(
    series_by_bus: dict[int, ReportSeries],
    active_at,  # Callable[[datetime], list[int]]
    now: datetime,
    s: Settings,
) -> int:
    """Xəttin AKTUAL məlumatla fasiləsiz YÜKSƏK olduğu müddət (saniyə, addım=persistence_step_seconds).

    `now`, `now-step`, `now-2*step`, ... nöqtələrinin HƏR BİRİNDƏ xətt nəticəsi hesablanır
    (həmin anda etibarlı bildirişlərlə və həmin anda aktiv avtobuslarla). Hər hansı bir
    nöqtədə məlumat köhnəlibsə / əhatə azdırsa / sıxlıq YÜKSƏK deyilsə, davamlılıq orada kəsilir.
    Beləliklə bir köhnə bildiriş 10 dəqiqə sonra təkbaşına xəbərdarlıq yarada bilməz.
    """
    step = s.persistence_step_seconds
    threshold = s.high_crowd_minutes * 60
    cap = max(s.persistence_cap_minutes * 60, threshold + step)

    def high(t: datetime) -> bool:
        return line_crowd_at(series_by_bus, active_at(t), t, s).is_high

    if not high(now):
        return 0
    k = 0
    while (k + 1) * step <= cap and high(now - timedelta(seconds=(k + 1) * step)):
        k += 1
    return k * step
