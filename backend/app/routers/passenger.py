from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from .. import clock
from ..config import Settings, get_settings
from ..db import get_session
from ..models import Direction, DirectionStop, Route, Stop
from ..schemas import ReportIn, ReportOut, TrafficReportIn
from ..services import reports, traffic, views
from ..textutil import fold_az

router = APIRouter(prefix="/api", tags=["passenger"])


@router.get("/routes")
def list_routes(session: Session = Depends(get_session)):
    """Demo marşrutlar (real xətt deyil)."""
    return {"routes": views.routes_list(session)}


@router.get("/directions/{direction_id}")
def direction_detail(direction_id: int, session: Session = Depends(get_session), s: Settings = Depends(get_settings)):
    d = views.direction_detail(session, direction_id, clock.now(), s)
    if d is None:
        raise HTTPException(404, "İstiqamət tapılmadı")
    return d


@router.get("/directions/{direction_id}/traffic")
def direction_traffic(direction_id: int, session: Session = Depends(get_session), s: Settings = Depends(get_settings)):
    d = traffic.direction_traffic(session, direction_id, clock.now(), s)
    if d is None:
        raise HTTPException(404, "İstiqamət tapılmadı")
    return d


@router.post("/traffic-reports", status_code=201)
def post_traffic_report(body: TrafficReportIn, session: Session = Depends(get_session), s: Settings = Depends(get_settings)):
    try:
        return traffic.submit_report(session, body.direction_id, body.lat, body.lon, body.level, body.session_id, clock.now(), s)
    except traffic.TrafficError as e:
        session.rollback()
        headers = {"Retry-After": str(e.retry_after)} if e.retry_after else None
        return JSONResponse(status_code=e.status, content={"detail": e.message, "code": e.code, "retry_after_seconds": e.retry_after}, headers=headers)


@router.get("/directions/{direction_id}/buses")
def direction_buses(direction_id: int, session: Session = Depends(get_session), s: Settings = Depends(get_settings)):
    d = views.direction_buses(session, direction_id, clock.now(), s)
    if d is None:
        raise HTTPException(404, "İstiqamət tapılmadı")
    return d


@router.get("/stops")
def search_stops(
    q: str = Query(min_length=2, max_length=80),
    limit: int = Query(20, ge=1, le=50),
    session: Session = Depends(get_session),
):
    """REAL dayanacaqlar üzrə ada görə axtarış. `served_by` yalnız DEMO istiqamətləri göstərir."""
    needle = fold_az(q)
    rows = session.execute(
        select(Stop)
        .where(Stop.name_search.contains(needle, autoescape=True))
        .order_by(case((Stop.name_search.startswith(needle, autoescape=True), 0), else_=1), Stop.name_search, Stop.stop_id)
        .limit(limit)
    ).scalars().all()
    pks = [r.id for r in rows]
    served: dict[int, list[dict]] = {}
    if pks:
        links = session.execute(
            select(DirectionStop.stop_pk, DirectionStop.seq, Direction.id, Direction.name, Route.name)
            .join(Direction, Direction.id == DirectionStop.direction_id)
            .join(Route, Route.id == Direction.route_id)
            .where(DirectionStop.stop_pk.in_(pks))
        ).all()
        for pk, seq, did, dname, rname in links:
            served.setdefault(pk, []).append({"direction_id": did, "direction_name": dname, "route_name": rname, "seq": seq})
    return {
        "stops": [
            {
                "stop_id": r.stop_id,
                "name": r.name,
                "lat": r.lat,
                "lon": r.lon,
                "stop_type": r.stop_type,
                "is_real": True,
                "served_by": served.get(r.id, []),
            }
            for r in rows
        ]
    }


@router.get("/arrivals")
def arrivals(
    direction_id: int = Query(gt=0),
    stop_id: str = Query(min_length=1, max_length=64),
    session: Session = Depends(get_session),
    s: Settings = Depends(get_settings),
):
    res = views.arrivals(session, direction_id, stop_id, clock.now(), s)
    if res is None:
        raise HTTPException(404, "İstiqamət tapılmadı")
    if res.get("error") == "stop_not_in_direction":
        raise HTTPException(404, "Bu dayanacaq seçilmiş istiqamətdə yoxdur")
    return res


@router.post("/reports", response_model=ReportOut, status_code=201)
def post_report(body: ReportIn, session: Session = Depends(get_session), s: Settings = Depends(get_settings)):
    try:
        return reports.submit_report(session, body.bus_id, body.level, body.session_id, clock.now(), s)
    except reports.ReportError as e:
        session.rollback()
        headers = {"Retry-After": str(e.retry_after)} if e.retry_after else None
        return JSONResponse(
            status_code=e.status,
            content={"detail": e.message, "code": e.code, "retry_after_seconds": e.retry_after},
            headers=headers,
        )
