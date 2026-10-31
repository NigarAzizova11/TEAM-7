"""Analiz mühərriki: sıxlıq davamlılığı (10 dəqiqə), interval/qruplaşma, mümkün yol ləngiməsi,
qeyri-adi dayanma, tutum çatışmazlığı ehtimalı. Bütün hədlər `Settings`-dədir.

Vacib: bunlar DEMO qaydalarıdır; təsdiqlənmiş nəqliyyat standartı deyil. Nəticələr YALNIZ
ehtimal ifadələri ilə verilir (qəza/sürücü günahı qəti iddia edilmir) və operatora tövsiyədir,
sürücüyə heç bir avtomatik əmr göndərilmir.
"""
from __future__ import annotations

import math
import statistics
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import Settings
from ..geo import haversine_m
from ..models import Alert
from .crowd import BusCrowd, LineCrowd, bus_crowd_at, high_persistence_seconds, line_crowd_at
from .transit import DirData, displacement_speed, load_all, unwrap

MAX_SAMPLE_GAP_S = 45  # bundan böyük GPS boşluğu üzərindən interpolyasiya etmə

KIND_HIGH_CROWD = "HIGH_CROWD_10MIN"
KIND_BUNCHING = "BUNCHING"
KIND_SLOWDOWN = "POSSIBLE_SLOWDOWN"
KIND_UNUSUAL_STOP = "UNUSUAL_STOP"
MANAGED_KINDS = (KIND_HIGH_CROWD, KIND_BUNCHING, KIND_SLOWDOWN, KIND_UNUSUAL_STOP)

HIGH_CROWD_TITLE = "Əlavə avtobus ehtiyatı ayrılmalıdır"  # məcburi mətn


def fmt_dur(seconds: float) -> str:
    seconds = int(round(seconds))
    m, s = divmod(seconds, 60)
    if m == 0:
        return f"{s} san"
    return f"{m} dəq {s} san" if s else f"{m} dəq"


@dataclass
class Finding:
    kind: str
    dedup_key: str
    route_id: int
    direction_id: int
    title: str
    event: str
    possible_cause: str
    evidence: dict[str, Any]
    recommendation: str


@dataclass
class DirAnalysis:
    dd: DirData
    now: datetime
    line: LineCrowd
    high_for_seconds: int
    intervals: dict[str, Any]
    bunching: dict[str, Any] | None
    diagnosis: str  # capacity | interval | unclear
    bus_crowd: dict[int, BusCrowd]
    findings: list[Finding] = field(default_factory=list)


# ---------------------------------------------------------------- keçid hadisələri / interval


def pass_events(dd: DirData, now: datetime, s: Settings) -> dict[int, list[tuple[datetime, int]]]:
    """Hər dayanacaq üçün (keçmə vaxtı, bus_id) siyahısı; GPS seqmentləri arasında interpolyasiya ilə."""
    length = dd.length
    start = now - timedelta(minutes=s.interval_lookback_minutes)
    events: dict[int, list[tuple[datetime, int]]] = {st.seq: [] for st in dd.stops}
    for b in dd.buses:
        un = unwrap(dd.gps.get(b.id, []), length)
        for (t1, p1), (t2, p2) in zip(un, un[1:]):
            if t2 <= start or t2 > now or p2 <= p1:
                continue
            if (t2 - t1).total_seconds() > MAX_SAMPLE_GAP_S:
                continue
            for st in dd.stops:
                k = math.floor((p1 - st.d) / length) + 1
                c = st.d + k * length
                if p1 < c <= p2:
                    t = t1 + (t2 - t1) * ((c - p1) / (p2 - p1))
                    if start < t <= now:
                        events[st.seq].append((t, b.id))
    for lst in events.values():
        lst.sort()
    return events


def analyze_intervals(
    dd: DirData, events: dict[int, list[tuple[datetime, int]]], s: Settings
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    target = dd.direction.target_interval_seconds
    gaps: list[float] = []
    flagged: list[dict[str, Any]] = []
    codes = dd.bus_codes()
    for st in dd.stops:
        ev = events.get(st.seq, [])
        for (t1, b1), (t2, b2) in zip(ev, ev[1:]):
            if b1 != b2:
                gaps.append((t2 - t1).total_seconds())
        last_flag = None
        for (t1, b1), (t2, b2), (t3, b3) in zip(ev, ev[1:], ev[2:]):
            if b1 == b2 or b2 == b3:
                continue
            g_small = (t2 - t1).total_seconds()
            g_large = (t3 - t2).total_seconds()
            if g_small < s.bunch_small_ratio * target and g_large > s.bunch_large_ratio * target:
                last_flag = {
                    "stop": st.name,
                    "stop_id": st.stop_id,
                    "leader": codes.get(b1, str(b1)),
                    "follower": codes.get(b2, str(b2)),
                    "gap_small_s": round(g_small),
                    "gap_large_s": round(g_large),
                }
        if last_flag:
            flagged.append(last_flag)

    if len(gaps) >= 3:
        stats = {
            "median_s": round(statistics.median(gaps)),
            "min_s": round(min(gaps)),
            "max_s": round(max(gaps)),
            "samples": len(gaps),
        }
    else:
        stats = {"median_s": None, "min_s": None, "max_s": None, "samples": len(gaps)}
    stats["target_s"] = target

    bunching = None
    if len(flagged) >= s.bunch_min_stops:
        pair_counts: dict[tuple[str, str], int] = {}
        for f in flagged:
            key = (f["leader"], f["follower"])
            pair_counts[key] = pair_counts.get(key, 0) + 1
        pair = max(pair_counts, key=lambda k: pair_counts[k])
        same = [f for f in flagged if (f["leader"], f["follower"]) == pair]
        bunching = {
            "pair": list(pair),
            "gap_small_s": round(statistics.median(f["gap_small_s"] for f in same)),
            "gap_large_s": round(statistics.median(f["gap_large_s"] for f in same)),
            "stops_flagged": len(flagged),
            "example_stops": [f["stop"] for f in same[:3]],
        }
    return stats, bunching


# ---------------------------------------------------------------- mümkün yol ləngiməsi


def detect_slowdown(dd: DirData, now: datetime, s: Settings) -> dict[str, Any] | None:
    length = dd.length
    since = now - timedelta(minutes=s.slow_lookback_minutes)
    stop_d = [st.d for st in dd.stops]
    samples: list[tuple[int, int, float]] = []  # (bus_id, segment_idx, speed)
    for b in dd.buses:
        pts = dd.gps.get(b.id, [])
        un = unwrap(pts, length)
        for i in range(1, len(pts)):
            if pts[i].t <= since:
                continue
            dt = (pts[i].t - pts[i - 1].t).total_seconds()
            if dt <= 0 or dt > MAX_SAMPLE_GAP_S:
                continue
            speed = max(0.0, un[i][1] - un[i - 1][1]) / dt
            seg = bisect_right(stop_d, pts[i].progress) - 1
            if seg < 0 or seg >= len(stop_d) - 1:
                continue
            samples.append((b.id, seg, speed))
    moving = [sp for _, _, sp in samples if sp > s.eta_stopped_speed_mps]
    if len(moving) < 10:
        return None
    baseline = statistics.median(moving)

    by_seg: dict[int, dict[int, list[float]]] = {}
    for bid, seg, sp in samples:
        by_seg.setdefault(seg, {}).setdefault(bid, []).append(sp)

    codes = dd.bus_codes()
    best: dict[str, Any] | None = None
    for seg, per_bus in sorted(by_seg.items()):
        slow = []
        for bid, sps in per_bus.items():
            if len(sps) < s.slow_min_samples:
                continue
            mean = sum(sps) / len(sps)
            if mean < s.slow_speed_ratio * baseline:
                slow.append({"bus": codes.get(bid, str(bid)), "avg_speed_kmh": round(mean * 3.6, 1), "samples": len(sps)})
        if len(slow) >= s.slow_min_buses:
            cand = {
                "segment_index": seg,
                "from_stop": dd.stops[seg].name,
                "to_stop": dd.stops[seg + 1].name,
                "buses": slow,
                "baseline_kmh": round(baseline * 3.6, 1),
                "threshold_ratio": s.slow_speed_ratio,
                "lookback_minutes": s.slow_lookback_minutes,
            }
            if best is None or len(slow) > len(best["buses"]):
                best = cand
    return best


# ---------------------------------------------------------------- qeyri-adi dayanma


def detect_unusual_stops(dd: DirData, now: datetime, s: Settings) -> list[dict[str, Any]]:
    out = []
    window_start = now - timedelta(minutes=s.unusual_stop_minutes)
    length = dd.length
    recent_speeds: dict[int, float] = {}
    for b in dd.buses:
        pts = [p for p in dd.gps.get(b.id, []) if p.t >= now - timedelta(seconds=s.eta_speed_window_seconds)]
        sp = displacement_speed(pts, length)
        recent_speeds[b.id] = (sum(v for _, v in sp) / len(sp)) if sp else 0.0

    for b in dd.buses:
        pts = [p for p in dd.gps.get(b.id, []) if p.t >= window_start - timedelta(seconds=15)]
        if len(pts) < 3 or pts[0].t > window_start + timedelta(seconds=15) or pts[-1].t < now - timedelta(seconds=30):
            continue
        speeds = [v for _, v in displacement_speed(pts, length)]
        if not speeds or max(speeds) >= s.unusual_stop_max_speed_mps:
            continue
        drift = max(haversine_m(pts[0].lat, pts[0].lon, p.lat, p.lon) for p in pts)
        if drift > s.unusual_stop_max_drift_m:
            continue
        last = pts[-1]
        nearest = min(haversine_m(last.lat, last.lon, st.lat, st.lon) for st in dd.stops)
        if nearest <= s.unusual_stop_min_stop_distance_m:
            continue  # dayanacaqda gözləmə normaldır
        others = [bid for bid, v in recent_speeds.items() if bid != b.id and v > s.others_moving_mps]
        if not others:
            continue
        # Faktiki dayanma müddətini geriyə doğru ölç (yoxlama pəncərəsi ilə məhdudlaşma)
        full = dd.gps.get(b.id, [])
        start_t = full[-1].t
        for prev, cur in zip(reversed(full[:-1]), reversed(full[1:])):
            dt = (cur.t - prev.t).total_seconds()
            if dt <= 0 or dt > MAX_SAMPLE_GAP_S:
                break
            if haversine_m(prev.lat, prev.lon, last.lat, last.lon) > s.unusual_stop_max_drift_m:
                break
            start_t = prev.t
        out.append(
            {
                "bus": b.code,
                "bus_id": b.id,
                "stopped_for_seconds": round((now - start_t).total_seconds()),
                "distance_to_nearest_stop_m": round(nearest),
                "other_buses_moving": [dd.bus_codes()[o] for o in others],
            }
        )
    return out


# ---------------------------------------------------------------- bir istiqamət üçün tam analiz


def analyze_direction(
    dd: DirData, now: datetime, s: Settings, active_keys: set[str]
) -> DirAnalysis:
    route, direction = dd.route, dd.direction
    active_fn = dd.active_at(s)
    line = line_crowd_at(dd.reports, active_fn(now), now, s)
    high_for = high_persistence_seconds(dd.reports, active_fn, now, s)

    events = pass_events(dd, now, s)
    intervals, bunching = analyze_intervals(dd, events, s)

    bus_crowd = {b.id: bus_crowd_at(dd.reports.get(b.id), now, s) for b in dd.buses}
    high_buses = [b.code for b in dd.buses if bus_crowd[b.id].level == "HIGH" and b.id in active_fn(now)]

    # Tutum çatışmazlığı ehtimalı: intervallar normal + ardıcıl avtobuslarda yüksək sıxlıq
    median = intervals["median_s"]
    target = direction.target_interval_seconds
    intervals_ok = (
        median is not None
        and bunching is None
        and s.interval_ok_low * target <= median <= s.interval_ok_high * target
    )
    if bunching is not None:
        diagnosis = "interval"
    elif intervals_ok and len(high_buses) >= 2:
        diagnosis = "capacity"
    else:
        diagnosis = "unclear"

    a = DirAnalysis(dd, now, line, high_for, intervals, bunching, diagnosis, bus_crowd)
    where = f"{route.name} ({direction.name})"

    # --- 1) 10 dəqiqəlik yüksək sıxlıq qaydası
    threshold = s.high_crowd_minutes * 60
    key = f"{KIND_HIGH_CROWD}:{direction.id}"
    sustained = high_for >= threshold
    still_high = line.is_high and key in active_keys  # artıq aktiv xəbərdarlıq YÜKSƏK qaldıqca davam edir
    if sustained or still_high:
        if diagnosis == "capacity":
            cause = (
                "Tutum çatışmazlığı ehtimalı: ölçülmüş intervallar hədəfə yaxındır, "
                "lakin ardıcıl avtobuslarda yüksək sıxlıq bildirilir."
            )
            rec = (
                "Əlavə avtobus ehtiyatı ayrılmalıdır. İntervallar normaldır, buna görə problemin əsas səbəbi "
                "interval pozuntusundan çox tutum ola bilər. Qərarı dispetçer verir."
            )
        elif diagnosis == "interval":
            cause = (
                "Mümkün interval pozuntusu: avtobuslar qruplaşıb və bir hissədə sıxlıq yüksəkdir; "
                "səbəb dəqiq müəyyən edilməyib."
            )
            rec = (
                "Əvvəlcə intervalın bərpası qiymətləndirilsin (qruplaşma aşkarlanıb). Sıxlıq intervaldan sonra da "
                "yüksək qalarsa əlavə avtobus ehtiyatı ayrılmalıdır."
            )
        else:
            cause = "Yüksək sıxlığın səbəbi kifayət qədər aydın deyil (interval məlumatı məhduddur və ya qarışıqdır)."
            rec = (
                "Əlavə avtobus ehtiyatı ayrılmasını və intervalları dispetçer yoxlasın; "
                "ehtiyat ayrılması qərarı operatorundur."
            )
        users = sum(bc.user_count for bc in bus_crowd.values())
        demos = sum(bc.demo_count for bc in bus_crowd.values())
        a.findings.append(
            Finding(
                kind=KIND_HIGH_CROWD,
                dedup_key=key,
                route_id=route.id,
                direction_id=direction.id,
                title=HIGH_CROWD_TITLE,
                event=(
                    f"{where} xəttində yüksək sıxlıq aktual məlumatlarla "
                    f"{fmt_dur(high_for)} fasiləsiz davam edir (hədd: {s.high_crowd_minutes} dəq)."
                ),
                possible_cause=cause,
                evidence={
                    "line_level": line.level,
                    "line_score": line.score,
                    "high_for_seconds": high_for,
                    "threshold_seconds": threshold,
                    "coverage": {"buses_with_data": line.buses_with_data, "active_buses": line.active_buses},
                    "latest_report_age_seconds": None
                    if line.latest_report_age_seconds is None
                    else round(line.latest_report_age_seconds),
                    "report_window_minutes": s.crowd_window_minutes,
                    "reports_in_window": {"user": users, "demo_seed": demos},
                    "high_buses": high_buses,
                    "observed_interval_median_s": median,
                    "target_interval_s": target,
                    "bunching_detected": bunching is not None,
                    "diagnosis": diagnosis,
                },
                recommendation=rec,
            )
        )

    # --- 2) qruplaşma
    if bunching is not None:
        a.findings.append(
            Finding(
                kind=KIND_BUNCHING,
                dedup_key=f"{KIND_BUNCHING}:{direction.id}",
                route_id=route.id,
                direction_id=direction.id,
                title="Avtobusların qruplaşması ehtimalı",
                event=(
                    f"{where}: {bunching['pair'][0]} və {bunching['pair'][1]} arasında interval "
                    f"{fmt_dur(bunching['gap_small_s'])}, arxasında isə {fmt_dur(bunching['gap_large_s'])} boşluq "
                    f"(hədəf interval: {fmt_dur(target)})."
                ),
                possible_cause=(
                    "Avtobusların bir-birinə yaxınlaşması (qruplaşma) mümkündür; arxadakı avtobus öndəkinə çatıb "
                    "və geridə böyük boşluq qalıb. Dəqiq səbəb GPS ilə müəyyən edilə bilməz."
                ),
                evidence={**bunching, "target_interval_s": target, "observed_intervals": intervals},
                recommendation=(
                    "Dispetçer təhlükəsiz nəzarət nöqtəsində intervalın bərpasını qiymətləndirsin. "
                    "Bu yalnız tövsiyədir: sürücüyə avtomatik əmr göndərilmir."
                ),
            )
        )

    # --- 3) mümkün yol ləngiməsi
    slow = detect_slowdown(dd, now, s)
    if slow is not None:
        names = ", ".join(b["bus"] for b in slow["buses"])
        a.findings.append(
            Finding(
                kind=KIND_SLOWDOWN,
                dedup_key=f"{KIND_SLOWDOWN}:{direction.id}:{slow['segment_index']}",
                route_id=route.id,
                direction_id=direction.id,
                title="Mümkün yol ləngiməsi",
                event=(
                    f"{where}: «{slow['from_stop']}» və «{slow['to_stop']}» arasındakı sxematik hissədə "
                    f"bir neçə avtobus ({names}) birlikdə yavaşlayıb."
                ),
                possible_cause=(
                    "Bu hissədə mümkün yol ləngiməsi (sıxlıq, yol işi və ya başqa səbəb ola bilər). "
                    "Səbəb GPS məlumatından qəti müəyyən edilə bilməz."
                ),
                evidence=slow,
                recommendation=(
                    "Operator bu hissədəki vəziyyəti əlavə mənbələrdən yoxlasın və intervalı izləsin. "
                    "Ləngimə davam edərsə sonrakı addım dispetçerin qərarıdır."
                ),
            )
        )

    # --- 4) qeyri-adi dayanma
    for u in detect_unusual_stops(dd, now, s):
        a.findings.append(
            Finding(
                kind=KIND_UNUSUAL_STOP,
                dedup_key=f"{KIND_UNUSUAL_STOP}:{u['bus_id']}",
                route_id=route.id,
                direction_id=direction.id,
                title="Qeyri-adi dayanma",
                event=(
                    f"{where}: {u['bus']} dayanacaqdan təxminən {u['distance_to_nearest_stop_m']} m kənarda "
                    f"{fmt_dur(u['stopped_for_seconds'])} hərəkətsizdir, digər avtobuslar isə hərəkət edir."
                ),
                possible_cause=(
                    "Qeyri-adi dayanma müşahidə olunur. Səbəb (texniki, yol və ya başqa) GPS-dən müəyyən edilə bilməz; "
                    "heç bir nəticə sürücünün günahı kimi qiymətləndirilməməlidir."
                ),
                evidence=u,
                recommendation="Operator səbəbi dəqiqləşdirsin (məsələn, avtobusla əlaqə yaradaraq).",
            )
        )
    return a


# ---------------------------------------------------------------- xəbərdarlıqların uzlaşdırılması


@dataclass
class EvalResult:
    created: list[int] = field(default_factory=list)
    resolved: list[int] = field(default_factory=list)
    updated: list[int] = field(default_factory=list)
    analyses: list[DirAnalysis] = field(default_factory=list)


def active_alert_keys(session: Session) -> set[str]:
    rows = session.execute(select(Alert.dedup_key).where(Alert.status == "ACTIVE")).scalars().all()
    return set(rows)


def analyze_all(session: Session, now: datetime, s: Settings) -> list[DirAnalysis]:
    keys = active_alert_keys(session)
    return [analyze_direction(dd, now, s, keys) for dd in load_all(session, now, s)]


def evaluate(session: Session, now: datetime, s: Settings) -> EvalResult:
    """Analizi işlət, xəbərdarlıqları yarat/yenilə/həll et.

    - Eyni dedup_key üçün eyni anda yalnız BİR aktiv xəbərdarlıq (DB unikal indeksi də qoruyur).
    - Şərt aradan qalxanda (sıxlıq düşüb, məlumat köhnəlib, ...) xəbərdarlıq HƏLL OLUNUR.
    - Həll olunandan sonra eyni hadisə yenidən yaranarsa YENİ xəbərdarlıq yaradılır
      (10 dəqiqəlik qayda yenidən sıfırdan ödənməlidir).
    """
    result = EvalResult()
    result.analyses = analyze_all(session, now, s)
    current: dict[str, Finding] = {}
    for a in result.analyses:
        for f in a.findings:
            current[f.dedup_key] = f

    existing = {
        al.dedup_key: al
        for al in session.execute(select(Alert).where(Alert.status == "ACTIVE")).scalars().all()
    }
    managed_prefixes = tuple(f"{k}:" for k in MANAGED_KINDS)

    for key, al in existing.items():
        if not key.startswith(managed_prefixes):
            continue
        if key not in current:
            al.status = "RESOLVED"
            al.resolved_at = now
            al.updated_at = now
            result.resolved.append(al.id)
        else:
            f = current[key]
            al.event = f.event
            al.possible_cause = f.possible_cause
            al.evidence = f.evidence
            al.recommendation = f.recommendation
            al.updated_at = now
            result.updated.append(al.id)

    for key, f in current.items():
        if key in existing:
            continue
        alert = Alert(
            kind=f.kind,
            route_id=f.route_id,
            direction_id=f.direction_id,
            dedup_key=key,
            status="ACTIVE",
            title=f.title,
            event=f.event,
            possible_cause=f.possible_cause,
            evidence=f.evidence,
            recommendation=f.recommendation,
            is_demo=True,
            created_at=now,
            updated_at=now,
        )
        try:
            with session.begin_nested():
                session.add(alert)
                session.flush()
            result.created.append(alert.id)
        except IntegrityError:
            # paralel icra eyni xəbərdarlığı artıq yaradıb; təkrar yaratma
            pass
    session.flush()
    return result
