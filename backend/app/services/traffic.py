"""Tıxac: sərnişin bildirişləri əsasında xətt üzrə tıxac səviyyəsi və operator xəbərdarlığı.

DÜRÜSTLÜK QEYDİ: bu real trafik sensoru/Waze/Google datası DEYİL (onlar açar/lisenziya tələb edir). Tıxac yalnız
sərnişinlərin xətt üzərində verdiyi bildirişlərdən hesablanır (Waze-in "icma bildirişi" prinsipi). Bildiriş azdırsa,
nəticə "təsdiqlənməyib" kimi göstərilir. Alternativ yol real marşrutlaşdırma mühərrikindən (OSRM) alınır, amma OSRM
də canlı tıxacı bilmir: yalnız tıxac nöqtəsindən yan keçən yolları təklif edir.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..config import Settings
from ..models import Alert, Direction, DirectionStop, Route, TrafficReport
from .reports import hash_session
from .transit import stop_infos

KIND_TRAFFIC = "TRAFFIC_JAM"
LEVEL_VALUE = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
LEVEL_LABEL = {"LOW": "Yüngül tıxac", "MEDIUM": "Orta tıxac", "HIGH": "Ağır tıxac", "UNCONFIRMED": "Təsdiqlənməyib"}
# Detour: tıxacdan əvvəl/sonra neçə metr məsafədə yan keçid başlayıb bitsin
DETOUR_MARGIN_M = 600.0


class TrafficError(Exception):
    def __init__(self, code: str, status: int, message: str, retry_after: int | None = None):
        super().__init__(message)
        self.code, self.status, self.message, self.retry_after = code, status, message, retry_after


@dataclass
class Jam:
    d_from: float
    d_to: float
    d_center: float
    lat: float
    lon: float
    level: str  # LOW | MEDIUM | HIGH | UNCONFIRMED
    reports: int  # fərqli sərnişin sayı
    avg_score: float
    latest_age_s: float
    demo_reports: int


def classify(n: int, avg: float, s: Settings) -> str:
    if n < s.traffic_min_reports:
        return "UNCONFIRMED"
    if avg >= s.traffic_heavy_min:
        return "HIGH"
    if avg >= s.traffic_medium_min:
        return "MEDIUM"
    return "LOW"


def slice_points(poly, d1: float, d2: float) -> list[list[float]]:
    """Xəttin d1..d2 hissəsi [[lat, lon], ...] (xəritədə rənglənmək üçün)."""
    d1, d2 = max(0.0, min(d1, d2)), min(poly.length, max(d1, d2))
    if d2 - d1 < 1.0:
        d2 = min(poly.length, d1 + 1.0)
        d1 = max(0.0, d2 - 1.0)
    out = [list(poly.point_at(min(d1, poly.length - 1e-6))[:2])]
    for c, pt in zip(poly.cum, poly.points):
        if d1 < c < d2:
            out.append([pt[0], pt[1]])
    out.append(list(poly.point_at(min(d2, poly.length - 1e-6))[:2]))
    return out


def build_jams(rows: list[tuple[float, float, float, int, str, datetime, str]], now: datetime, s: Settings) -> list[Jam]:
    """rows: (d_m, lat, lon, level, session_hash, created_at, source). Eyni sessiyanın yalnız ƏN SON bildirişi sayılır."""
    latest: dict[str, tuple] = {}
    for r in rows:
        cur = latest.get(r[4])
        if cur is None or r[5] > cur[5]:
            latest[r[4]] = r
    items = sorted(latest.values(), key=lambda r: r[0])
    groups: list[list[tuple]] = []
    for r in items:
        if groups and r[0] - groups[-1][-1][0] <= s.traffic_cluster_gap_m:
            groups[-1].append(r)
        else:
            groups.append([r])
    jams = []
    for g in groups:
        n = len(g)
        avg = sum(x[3] for x in g) / n
        dc = sum(x[0] for x in g) / n
        jams.append(
            Jam(
                d_from=min(x[0] for x in g),
                d_to=max(x[0] for x in g),
                d_center=dc,
                lat=sum(x[1] for x in g) / n,
                lon=sum(x[2] for x in g) / n,
                level=classify(n, avg, s),
                reports=n,
                avg_score=round(avg, 2),
                latest_age_s=min((now - x[5]).total_seconds() for x in g),
                demo_reports=sum(1 for x in g if x[6] == "demo_seed"),
            )
        )
    return jams


def fresh_rows(session: Session, direction_ids: list[int] | None, now: datetime, s: Settings):
    q = select(
        TrafficReport.direction_id, TrafficReport.d_m, TrafficReport.lat, TrafficReport.lon, TrafficReport.level,
        TrafficReport.session_hash, TrafficReport.created_at, TrafficReport.source,
    ).where(
        TrafficReport.created_at > now - timedelta(minutes=s.traffic_window_minutes), TrafficReport.created_at <= now
    )
    if direction_ids is not None:
        q = q.where(TrafficReport.direction_id.in_(direction_ids))
    by_dir: dict[int, list] = {}
    for r in session.execute(q).all():
        by_dir.setdefault(r[0], []).append(r[1:])
    return by_dir


def _load_direction(session: Session, direction_id: int) -> Direction | None:
    return session.execute(
        select(Direction)
        .where(Direction.id == direction_id)
        .options(selectinload(Direction.stops).selectinload(DirectionStop.stop), selectinload(Direction.route))
    ).scalar_one_or_none()


def submit_report(
    session: Session, direction_id: int, lat: float, lon: float, level: str, session_id: str, now: datetime, s: Settings
) -> dict[str, Any]:
    if level not in LEVEL_VALUE:
        raise TrafficError("invalid_level", 422, "Tıxac səviyyəsi etibarsızdır")
    d = _load_direction(session, direction_id)
    if d is None:
        raise TrafficError("direction_not_found", 404, "İstiqamət tapılmadı")
    _, poly = stop_infos(d)
    d_m, off = poly.project(lat, lon)
    if off > s.traffic_snap_max_m:
        raise TrafficError(
            "off_route", 422, f"Seçilən nöqtə marşrut xəttindən {round(off)} m uzaqdadır (maksimum {round(s.traffic_snap_max_m)} m). Xəttin üstündə seçin."
        )
    h = hash_session(session_id, s.session_hash_secret)
    last = session.execute(
        select(func.max(TrafficReport.created_at)).where(
            TrafficReport.session_hash == h, TrafficReport.direction_id == direction_id, TrafficReport.source == "user"
        )
    ).scalar()
    cd = timedelta(seconds=s.traffic_cooldown_seconds)
    if last is not None and now - last < cd:
        wait = int((cd - (now - last)).total_seconds()) + 1
        raise TrafficError("rate_limited", 429, f"Eyni istiqamətə {s.traffic_cooldown_seconds} saniyədə bir tıxac bildirişi göndərilə bilər", wait)
    la, lo, _ = poly.point_at(min(d_m, poly.length - 1e-6))
    session.add(
        TrafficReport(direction_id=direction_id, d_m=d_m, lat=la, lon=lo, level=LEVEL_VALUE[level], session_hash=h, created_at=now, source="user")
    )
    session.flush()
    reconcile_alerts(session, now, s)
    session.commit()
    return {"accepted": True, "direction_id": direction_id, "level": level, "snapped_distance_m": round(off), "received_at": now.isoformat()}


def _nearest_stop(stops, d: float):
    return min(stops, key=lambda st: abs(st.d - d))


def direction_traffic(session: Session, direction_id: int, now: datetime, s: Settings) -> dict[str, Any] | None:
    d = _load_direction(session, direction_id)
    if d is None:
        return None
    stops, poly = stop_infos(d)
    rows = fresh_rows(session, [direction_id], now, s).get(direction_id, [])
    jams = build_jams(rows, now, s)
    out = []
    for i, j in enumerate(jams):
        near = _nearest_stop(stops, j.d_center)
        pad = 150.0  # bir nöqtəlik bildiriş də xəritədə görünsün
        item = {
            "index": i,
            "level": j.level,
            "label": LEVEL_LABEL[j.level],
            "reports": j.reports,
            "demo_reports": j.demo_reports,
            "avg_score": j.avg_score,
            "latest_report_age_seconds": round(j.latest_age_s),
            "lat": j.lat,
            "lon": j.lon,
            "near_stop": near.name,
            "from_m": round(j.d_from),
            "to_m": round(j.d_to),
            "path": slice_points(poly, j.d_from - pad, j.d_to + pad),
        }
        if j.level in ("MEDIUM", "HIGH"):
            item["detour"] = detour_hint(stops, poly, j)
        out.append(item)
    worst = max((j for j in jams), key=lambda j: ("UNCONFIRMED", "LOW", "MEDIUM", "HIGH").index(j.level), default=None)
    return {
        "direction_id": direction_id,
        "server_time": now.isoformat(),
        "window_minutes": s.traffic_window_minutes,
        "level": worst.level if worst else None,
        "label": LEVEL_LABEL[worst.level] if worst else "Tıxac bildirişi yoxdur",
        "jams": out,
        "note": "Tıxac səviyyəsi YALNIZ sərnişin bildirişlərindən hesablanır (real trafik sensoru yoxdur). "
        f"Son {s.traffic_window_minutes} dəqiqənin bildirişləri sayılır; {s.traffic_min_reports} nəfərdən az bildiriş 'təsdiqlənməyib' sayılır.",
    }


def detour_hint(stops, poly, jam: Jam) -> dict[str, Any]:
    """Alternativ yol üçün giriş: tıxacdan əvvəlki/sonrakı nöqtələr, yan keçilməli sahə və təsirlənən dayanacaqlar.
    Marşrutlaşdırma özü (OSRM) brauzerdən/mobil tətbiqdən çağırılır."""
    d_a = max(0.0, jam.d_from - DETOUR_MARGIN_M)
    d_b = min(poly.length, jam.d_to + DETOUR_MARGIN_M)
    a = poly.point_at(min(d_a, poly.length - 1e-6))
    b = poly.point_at(min(d_b, poly.length - 1e-6))
    affected = [st for st in stops if d_a < st.d < d_b]
    return {
        "from": {"lat": a[0], "lon": a[1]},
        "to": {"lat": b[0], "lon": b[1]},
        "avoid": {"lat": jam.lat, "lon": jam.lon, "radius_m": 150.0 + (jam.d_to - jam.d_from) / 2},
        "original_length_m": round(d_b - d_a),
        "affected_stops": [{"seq": st.seq, "name": st.name} for st in affected],
        "note": "Alternativ yol sərnişin bildirişlərinə əsasən təklifdir; marşrut dəyişikliyi operator/dispetçer qərarıdır.",
    }


# ---------------------------------------------------------------- operator xəbərdarlığı


def reconcile_alerts(session: Session, now: datetime, s: Settings) -> dict[str, list[int]]:
    """Ağır tıxac (>= traffic_alert_min_reports fərqli sərnişin) varsa istiqamət üçün TRAFFIC_JAM xəbərdarlığı yarat/yenilə,
    şərt itəndə HƏLL ET."""
    res: dict[str, list[int]] = {"created": [], "updated": [], "resolved": []}
    by_dir = fresh_rows(session, None, now, s)
    heavy: dict[int, Jam] = {}
    for did, rows in by_dir.items():
        hj = [
            j for j in build_jams(rows, now, s)
            if j.avg_score >= s.traffic_heavy_min and j.reports >= s.traffic_alert_min_reports
        ]
        if hj:
            heavy[did] = max(hj, key=lambda j: j.reports)
    existing = {
        a.direction_id: a
        for a in session.execute(
            select(Alert).where(Alert.status == "ACTIVE", Alert.kind == KIND_TRAFFIC)
        ).scalars()
    }
    for did, al in existing.items():
        if did not in heavy:
            al.status, al.resolved_at, al.updated_at = "RESOLVED", now, now
            res["resolved"].append(al.id)
    if not heavy:
        session.flush()
        return res
    dirs = {
        d.id: d
        for d in session.execute(
            select(Direction)
            .where(Direction.id.in_(list(heavy)))
            .options(selectinload(Direction.stops).selectinload(DirectionStop.stop), selectinload(Direction.route))
        ).scalars()
    }
    for did, j in heavy.items():
        d = dirs.get(did)
        if d is None:
            continue
        stops, poly = stop_infos(d)
        near = _nearest_stop(stops, j.d_center)
        hint = detour_hint(stops, poly, j)
        confirmed = j.reports >= s.traffic_min_reports
        title = f"Marşrutda ağır tıxac: {d.route.code}" + ("" if confirmed else " (təsdiqlənməyib)")
        event = (
            f"{d.route.name} marşrutunun «{d.name}» istiqamətində «{near.name}» dayanacağı yaxınlığında ağır tıxac bildirilir "
            f"({j.reports} fərqli sərnişin, son {s.traffic_window_minutes} dəqiqə)."
            + ("" if confirmed else " Bu hələ yalnız 1 sərnişinin bildirişidir, başqa sərnişin təsdiq etməyib.")
        )
        cause = (
            "Sərnişin bildirişlərinə əsaslanan ehtimaldır (real trafik sensoru yoxdur): səbəb qəza, yol işi və ya yüksək axın ola bilər; "
            "qəti iddia edilmir."
        )
        evidence = {
            "reports_distinct_sessions": j.reports,
            "confirmed_by_multiple_passengers": confirmed,
            "avg_level_score_1_to_3": j.avg_score,
            "window_minutes": s.traffic_window_minutes,
            "location": {"lat": round(j.lat, 5), "lon": round(j.lon, 5), "near_stop": near.name, "route_meter": round(j.d_center)},
            "latest_report_age_seconds": round(j.latest_age_s),
            "demo_reports": j.demo_reports,
            "affected_stops": [x["name"] for x in hint["affected_stops"]],
        }
        rec = (
            "Marşrutda gecikmə gözlənilir. Sərnişin tətbiqində alternativ yol təklifi göstərilir. "
            "Yönləndirmə/əlavə avtobus barədə qərarı dispetçer verir; sürücüyə avtomatik əmr göndərilmir."
        )
        al = existing.get(did)
        if al is not None and (al.evidence or {}).get("operator"):
            evidence["operator"] = al.evidence["operator"]
            if evidence["operator"].get("action") == "CONFIRMED":
                title = f"Marşrutda ağır tıxac: {d.route.code} (operator təsdiq etdi)"
        if al is not None:
            al.title, al.event, al.possible_cause, al.evidence, al.recommendation, al.updated_at = title, event, cause, evidence, rec, now
            res["updated"].append(al.id)
            continue
        alert = Alert(
            kind=KIND_TRAFFIC, route_id=d.route_id, direction_id=did, dedup_key=f"{KIND_TRAFFIC}:{did}", status="ACTIVE",
            title=title, event=event, possible_cause=cause, evidence=evidence, recommendation=rec,
            is_demo=j.demo_reports > 0, created_at=now, updated_at=now,
        )
        try:
            with session.begin_nested():
                session.add(alert)
                session.flush()
            res["created"].append(alert.id)
        except IntegrityError:
            pass
    session.flush()
    return res


def operator_action(session: Session, alert_id: int, action: str, now: datetime, s: Settings) -> dict[str, Any]:
    """Operator xəbərdarlığı təsdiq edir ('confirm') və ya yalan bildiriş kimi rədd edir ('dismiss', yalnız tıxac).
    Qərar `evidence.operator` daxilində saxlanılır (yenilənmələrdə qorunur)."""
    al = session.get(Alert, alert_id)
    if al is None:
        raise TrafficError("alert_not_found", 404, "Xəbərdarlıq tapılmadı")
    if al.status != "ACTIVE":
        raise TrafficError("not_active", 409, "Xəbərdarlıq artıq aktiv deyil")
    if action == "confirm":
        ev = dict(al.evidence or {})
        ev["operator"] = {"action": "CONFIRMED", "at": now.isoformat()}
        al.evidence = ev
        al.title = al.title.replace(" (təsdiqlənməyib)", "") + " (operator təsdiq etdi)" if "operator təsdiq" not in al.title else al.title
        al.updated_at = now
    elif action == "dismiss":
        if al.kind != KIND_TRAFFIC:
            raise TrafficError("dismiss_unsupported", 422, "Yalnız tıxac bildirişi yalan kimi rədd edilə bilər")
        n = session.execute(
            delete(TrafficReport).where(TrafficReport.direction_id == al.direction_id, TrafficReport.source == "user")
        ).rowcount or 0
        ev = dict(al.evidence or {})
        ev["operator"] = {"action": "DISMISSED", "at": now.isoformat(), "removed_reports": n}
        al.evidence = ev
        al.status, al.resolved_at, al.updated_at = "RESOLVED", now, now
    else:
        raise TrafficError("invalid_action", 422, "Naməlum əməliyyat")
    session.flush()
    reconcile_alerts(session, now, s)
    session.commit()
    return {"id": al.id, "status": al.status, "operator": (al.evidence or {}).get("operator")}


def operator_summary(session: Session, now: datetime, s: Settings) -> dict[int, dict[str, Any]]:
    """Operator cədvəli üçün: istiqamət id -> {level, label, jams:[...]} (yalnız bildirişi olanlar)."""
    out: dict[int, dict[str, Any]] = {}
    by_dir = fresh_rows(session, None, now, s)
    dirs = {}
    if by_dir:
        dirs = {
            d.id: d
            for d in session.execute(
                select(Direction).where(Direction.id.in_(list(by_dir))).options(selectinload(Direction.route))
            ).scalars()
        }
    for did, rows in by_dir.items():
        jams = build_jams(rows, now, s)
        worst = max(jams, key=lambda j: ("UNCONFIRMED", "LOW", "MEDIUM", "HIGH").index(j.level))
        d = dirs.get(did)
        out[did] = {
            "level": worst.level,
            "label": LEVEL_LABEL[worst.level],
            "route": d.route.name if d else "",
            "route_code": d.route.code if d else "",
            "direction": d.name if d else "",
            "jams": [
                {"level": j.level, "label": LEVEL_LABEL[j.level], "reports": j.reports, "lat": j.lat, "lon": j.lon,
                 "age_seconds": round(j.latest_age_s), "demo_reports": j.demo_reports,
                 "heavy_unconfirmed": j.avg_score >= s.traffic_heavy_min and j.reports < s.traffic_min_reports}
                for j in jams
            ],
        }
    return out


# ---------------------------------------------------------------- demo


def demo_jam(session: Session, direction_id: int, level: str, now: datetime, s: Settings, at_fraction: float = 0.5) -> dict[str, Any]:
    """DEMO: seçilmiş istiqamətdə etiketli (demo_seed) tıxac bildirişləri yarat. Real bildiriş sayılmır."""
    if level not in LEVEL_VALUE:
        raise TrafficError("invalid_level", 422, "Tıxac səviyyəsi etibarsızdır")
    d = _load_direction(session, direction_id)
    if d is None:
        raise TrafficError("direction_not_found", 404, "İstiqamət tapılmadı")
    _, poly = stop_infos(d)
    center = poly.length * max(0.05, min(0.95, at_fraction))
    n = 4 if level == "HIGH" else 3
    for i in range(n):
        dd = center + (i - (n - 1) / 2) * 60.0
        la, lo, _ = poly.point_at(max(0.0, min(dd, poly.length - 1e-6)))
        h = hashlib.sha256(f"demo-traffic-{direction_id}-{i}".encode()).hexdigest()
        session.add(
            TrafficReport(direction_id=direction_id, d_m=dd, lat=la, lon=lo, level=LEVEL_VALUE[level], session_hash=h,
                          created_at=now - timedelta(seconds=30 * (n - i)), source="demo_seed")
        )
    session.flush()
    reconcile_alerts(session, now, s)
    session.commit()
    return {"created_demo_reports": n, "level": level, "direction_id": direction_id}


def clear_demo(session: Session, direction_id: int | None, now: datetime, s: Settings) -> int:
    q = delete(TrafficReport).where(TrafficReport.source == "demo_seed")
    if direction_id is not None:
        q = q.where(TrafficReport.direction_id == direction_id)
    n = session.execute(q).rowcount or 0
    session.flush()
    reconcile_alerts(session, now, s)
    session.commit()
    return n
