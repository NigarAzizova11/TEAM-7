"""Sərnişin və operator ekranları üçün oxu (read-only) məntiqi."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import Alert, Direction, DirectionStop, Route
from . import traffic as traffic_svc
from .analysis import DirAnalysis, analyze_all
from .crowd import BusCrowd
from .transit import DirData, displacement_speed, load_all, stop_infos

AT_STOP_TOLERANCE_M = 20.0
ALTERNATIVE_MAX_EXTRA_WAIT_S = 900
ALTERNATIVE_MIN_SCORE_GAP = 0.5

ETA_NOTE = (
    "ETA marşrut xətti boyunca qalan məsafə və SİMULYASİYA edilmiş sürət əsasında hesablanır; "
    "real avtobusun gəliş vaxtı vədi deyil."
)
LINE_NOTE_AYNA = "AYNA marşrut xətti (real geometriya, sadələşdirilmiş); avtobuslar simulyasiyadır"
LINE_NOTE_DEMO = "sxematik demo xətti (real yol geometriyası deyil)"


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def crowd_dict(bc: BusCrowd) -> dict[str, Any]:
    return {
        "level": bc.level,  # None => "Məlumat yoxdur" (heç vaxt "Aşağı" deyil)
        "score": bc.score,
        "reports_count": bc.count,
        "demo_reports_count": bc.demo_count,
        "latest_report_age_seconds": None if bc.latest_age_seconds is None else round(bc.latest_age_seconds),
    }


def _recent_speed(dd: DirData, bus_id: int, now: datetime, s: Settings) -> float | None:
    pts = [p for p in dd.gps.get(bus_id, []) if (now - p.t).total_seconds() <= s.eta_speed_window_seconds]
    sp = displacement_speed(pts, dd.length)
    if not sp:
        return None
    return sum(v for _, v in sp) / len(sp)


def bus_view(dd: DirData, bus_id: int, now: datetime, s: Settings, crowd: BusCrowd, d_stop: float | None) -> dict[str, Any]:
    bus = next(b for b in dd.buses if b.id == bus_id)
    last = dd.last_gps(bus_id)
    out: dict[str, Any] = {
        "id": bus.id,
        "code": bus.code,
        "is_simulated": bus.is_simulated,
        "lat": None,
        "lon": None,
        "speed_kmh": None,
        "gps_age_seconds": None,
        "status": "offline",
        "eta_seconds": None,
        "eta_basis": None,
        "distance_to_stop_m": None,
        "crowd": crowd_dict(crowd),
    }
    if last is None:
        return out
    age = (now - last.t).total_seconds()
    out.update({"lat": last.lat, "lon": last.lon, "gps_age_seconds": round(age)})
    if age > s.gps_stale_seconds:
        return out  # offline

    speed = _recent_speed(dd, bus_id, now, s)
    basis = "observed_speed"
    if speed is None:
        speed = last.speed if last.speed is not None else None
    out["speed_kmh"] = None if speed is None else round(speed * 3.6, 1)
    out["status"] = "moving" if (speed is not None and speed >= s.eta_stopped_speed_mps) else "stopped"

    if d_stop is None:
        return out
    diff = d_stop - last.progress
    out["distance_to_stop_m"] = round(abs(diff))
    if abs(diff) <= AT_STOP_TOLERANCE_M:
        out.update({"status": "at_stop", "eta_seconds": 0, "eta_basis": basis})
    elif diff < 0:
        out["status"] = "passed"  # dayanacağı artıq keçib: yaxınlaşan kimi GÖSTƏRİLMİR
    else:
        if speed is None or speed < s.eta_stopped_speed_mps:
            out["status"] = "stopped"  # ETA məlum deyil
        else:
            out["status"] = "approaching"
            out["eta_seconds"] = round(diff / speed)
            out["eta_basis"] = basis
    return out


def find_direction_data(session: Session, direction_id: int, now: datetime, s: Settings) -> DirData | None:
    for dd in load_all(session, now, s, lookback_minutes=max(5, s.crowd_window_minutes + 1)):
        if dd.direction.id == direction_id:
            return dd
    # Avtobus simulyasiyası olmayan (yalnız real xətt/dayanacaq) marşrut: avtobussuz struktur qaytar
    from sqlalchemy.orm import selectinload

    d = session.execute(
        select(Direction)
        .where(Direction.id == direction_id)
        .options(selectinload(Direction.stops).selectinload(DirectionStop.stop), selectinload(Direction.route))
    ).scalar_one_or_none()
    if d is None or not d.stops:
        return None
    stops, poly = stop_infos(d)
    return DirData(direction=d, route=d.route, stops=stops, poly=poly, buses=[])
    return None


def arrivals(session: Session, direction_id: int, stop_id: str, now: datetime, s: Settings) -> dict[str, Any] | None:
    from .crowd import bus_crowd_at

    dd = find_direction_data(session, direction_id, now, s)
    if dd is None:
        return None
    stop = next((st for st in dd.stops if st.stop_id == stop_id), None)
    if stop is None:
        return {"error": "stop_not_in_direction"}

    buses = []
    for b in dd.buses:
        crowd = bus_crowd_at(dd.reports.get(b.id), now, s)
        buses.append(bus_view(dd, b.id, now, s, crowd, stop.d))

    order = {"at_stop": 0, "approaching": 1, "stopped": 2, "moving": 3, "passed": 4, "offline": 5}
    buses.sort(key=lambda x: (order.get(x["status"], 9), x["eta_seconds"] if x["eta_seconds"] is not None else 10**9, x["code"]))

    alternative = None
    upcoming = [b for b in buses if b["status"] in ("at_stop", "approaching") and b["eta_seconds"] is not None]
    upcoming.sort(key=lambda b: b["eta_seconds"])
    if len(upcoming) >= 2:
        first = upcoming[0]
        for nxt in upcoming[1:]:
            extra = nxt["eta_seconds"] - first["eta_seconds"]
            if extra > ALTERNATIVE_MAX_EXTRA_WAIT_S:
                break
            a, c = first["crowd"], nxt["crowd"]
            if a["score"] is not None and c["score"] is not None and c["score"] <= a["score"] - ALTERNATIVE_MIN_SCORE_GAP:
                alternative = {
                    "first_bus": first["code"],
                    "bus_id": nxt["id"],
                    "bus_code": nxt["code"],
                    "eta_seconds": nxt["eta_seconds"],
                    "extra_wait_seconds": extra,
                    "first_level": a["level"],
                    "level": c["level"],
                    "data_age_seconds": c["latest_report_age_seconds"],
                    "reports_count": c["reports_count"],
                }
                break

    return {
        "server_time": iso(now),
        "direction": {
            "id": dd.direction.id,
            "name": dd.direction.name,
            "route": {"id": dd.route.id, "code": dd.route.code, "name": dd.route.name, "is_demo": dd.route.is_demo, "source": dd.route.source},
            "target_interval_seconds": dd.direction.target_interval_seconds,
        },
        "stop": {"stop_id": stop.stop_id, "name": stop.name, "lat": stop.lat, "lon": stop.lon, "seq": stop.seq},
        "buses": buses,
        "alternative": alternative,
        "notes": {"gps": "SİMULYASİYA", "line": LINE_NOTE_AYNA if dd.route.source == "ayna" else LINE_NOTE_DEMO, "eta": ETA_NOTE},
    }


def direction_buses(session: Session, direction_id: int, now: datetime, s: Settings) -> dict[str, Any] | None:
    from .crowd import bus_crowd_at

    dd = find_direction_data(session, direction_id, now, s)
    if dd is None:
        return None
    return {
        "server_time": iso(now),
        "buses": [bus_view(dd, b.id, now, s, bus_crowd_at(dd.reports.get(b.id), now, s), None) for b in dd.buses],
    }


def direction_detail(session: Session, direction_id: int, now: datetime, s: Settings) -> dict[str, Any] | None:
    dd = find_direction_data(session, direction_id, now, s)
    if dd is None:
        return None
    return {
        "id": dd.direction.id,
        "name": dd.direction.name,
        "route": {"id": dd.route.id, "code": dd.route.code, "name": dd.route.name, "is_demo": dd.route.is_demo, "source": dd.route.source},
        "target_interval_seconds": dd.direction.target_interval_seconds,
        "length_m": round(dd.length),
        "polyline": [[lat, lon] for lat, lon in dd.poly.points],
        "polyline_note": LINE_NOTE_AYNA if dd.route.source == "ayna" else LINE_NOTE_DEMO,
        "stops": [
            {"seq": st.seq, "stop_id": st.stop_id, "name": st.name, "lat": st.lat, "lon": st.lon, "distance_m": round(st.d)}
            for st in dd.stops
        ],
    }


def routes_list(session: Session) -> list[dict[str, Any]]:
    routes = session.execute(select(Route).order_by(Route.is_demo.desc(), Route.id)).scalars().all()
    out = []
    for r in routes:
        out.append(
            {
                "id": r.id,
                "code": r.code,
                "name": r.name,
                "is_demo": r.is_demo,
                "source": r.source,
                "simulated": r.is_demo,  # True = bu marşrutda avtobus/GPS/bildirişlər SİMULYASİYA olunur
                "directions": [
                    {"id": d.id, "name": d.name, "ordinal": d.ordinal, "buses": len(d.buses), "stops": len(d.stops)}
                    for d in r.directions
                ],
            }
        )
    return out


# ---------------------------------------------------------------- operator


def alert_dict(a: Alert) -> dict[str, Any]:
    return {
        "id": a.id,
        "kind": a.kind,
        "status": a.status,
        "title": a.title,
        "event": a.event,
        "possible_cause": a.possible_cause,
        "evidence": a.evidence,
        "recommendation": a.recommendation,
        "created_at": iso(a.created_at),
        "updated_at": iso(a.updated_at),
        "resolved_at": iso(a.resolved_at),
        "is_demo": a.is_demo,
        "route": {"id": a.route.id, "code": a.route.code, "name": a.route.name},
        "direction": {"id": a.direction.id, "name": a.direction.name},
    }


def list_alerts(session: Session, status: str, limit: int = 100) -> list[dict[str, Any]]:
    q = select(Alert).order_by(Alert.created_at.desc(), Alert.id.desc()).limit(limit)
    if status in ("ACTIVE", "RESOLVED"):
        q = q.where(Alert.status == status)
    return [alert_dict(a) for a in session.execute(q).scalars().all()]


def _analysis_view(a: DirAnalysis, s: Settings, now: datetime, active_alert_ids: list[int]) -> dict[str, Any]:
    dd = a.dd
    d_none = None
    return {
        "route": {"id": dd.route.id, "code": dd.route.code, "name": dd.route.name, "is_demo": dd.route.is_demo, "source": dd.route.source},
        "direction": {"id": dd.direction.id, "name": dd.direction.name, "ordinal": dd.direction.ordinal},
        "target_interval_seconds": dd.direction.target_interval_seconds,
        "intervals": a.intervals,
        "bunching_detected": a.bunching is not None,
        "diagnosis": a.diagnosis,
        "crowd": {
            "level": a.line.level,
            "score": a.line.score,
            "reason_no_result": a.line.reason,
            "coverage": {
                "buses_with_data": a.line.buses_with_data,
                "active_buses": a.line.active_buses,
                "ratio": round(a.line.coverage_ratio, 2),
            },
            "latest_report_age_seconds": None
            if a.line.latest_report_age_seconds is None
            else round(a.line.latest_report_age_seconds),
            "high_for_seconds": a.high_for_seconds,
            "high_threshold_seconds": s.high_crowd_minutes * 60,
        },
        "active_buses": len([b for b in dd.buses if dd.has_fresh_gps(b.id, now, s.gps_stale_seconds)]),
        "buses": [bus_view(dd, b.id, now, s, a.bus_crowd[b.id], d_none) for b in dd.buses],
        "active_alert_ids": active_alert_ids,
    }


def operator_overview(session: Session, now: datetime, s: Settings) -> dict[str, Any]:
    analyses = analyze_all(session, now, s)
    alerts = session.execute(select(Alert).where(Alert.status == "ACTIVE")).scalars().all()
    by_dir: dict[int, list[int]] = {}
    for al in alerts:
        by_dir.setdefault(al.direction_id, []).append(al.id)
    tr = traffic_svc.operator_summary(session, now, s)
    return {
        "server_time": iso(now),
        "traffic": {str(k): v for k, v in tr.items()},
        "rules": {
            "high_crowd_minutes": s.high_crowd_minutes,
            "crowd_window_minutes": s.crowd_window_minutes,
            "crowd_thresholds": {"low_max": s.crowd_low_max, "high_min": s.crowd_high_min},
            "report_cooldown_seconds": s.report_cooldown_seconds,
            "note": "Bunlar demo qaydalarıdır, təsdiqlənmiş nəqliyyat standartı deyil.",
            "traffic_window_minutes": s.traffic_window_minutes,
            "traffic_alert_min_reports": s.traffic_alert_min_reports,
        },
        "directions": [_analysis_view(a, s, now, by_dir.get(a.dd.direction.id, [])) for a in analyses],
        "active_alerts_count": len(alerts),
    }
