from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import clock
from ..config import Settings, get_settings
from ..db import get_session
from ..models import Stop
from ..services import demo as demo_svc
from ..services import traffic as traffic_svc

router = APIRouter(prefix="/api/demo", tags=["demo"])


def _enabled(s: Settings = Depends(get_settings)) -> None:
    if not s.demo_endpoints_enabled:
        raise HTTPException(404, "Demo idarəetməsi söndürülüb")


@router.get("/status", dependencies=[Depends(_enabled)])
def status(session: Session = Depends(get_session)):
    st = demo_svc.current_scenario(session)
    return {
        "is_demo": True,
        "stops_loaded": session.execute(select(func.count()).select_from(Stop)).scalar(),
        "structure_ready": demo_svc.structure_exists(session),
        "active_scenario": None if st is None else st.scenario,
        "applied_at": None if st is None else st.applied_at.isoformat(),
        "scenarios": [
            {"name": i.name, "label": i.label, "description": i.description} for i in demo_svc.SCENARIOS.values()
        ],
        "warning": "Demo idarəetməsi: dinamik məlumat (GPS, bildiriş, xəbərdarlıq) silinir. Real dayanacaqlara toxunulmur.",
    }


@router.post("/scenarios/{name}", dependencies=[Depends(_enabled)])
def apply(name: str, session: Session = Depends(get_session), s: Settings = Depends(get_settings)):
    try:
        return demo_svc.apply_scenario(session, name, clock.now(), s)
    except demo_svc.DemoError as e:
        session.rollback()
        raise HTTPException(409 if name in demo_svc.SCENARIOS else 404, str(e)) from e


@router.post("/traffic", dependencies=[Depends(_enabled)])
def demo_traffic(
    direction_id: int,
    level: str = "HIGH",
    at: float = 0.5,
    session: Session = Depends(get_session),
    s: Settings = Depends(get_settings),
):
    """DEMO: seçilmiş istiqamətdə etiketli (demo) tıxac bildirişləri yaradır."""
    try:
        return traffic_svc.demo_jam(session, direction_id, level, clock.now(), s, at)
    except traffic_svc.TrafficError as e:
        session.rollback()
        raise HTTPException(e.status, e.message) from e


@router.delete("/traffic", dependencies=[Depends(_enabled)])
def demo_traffic_clear(direction_id: int | None = None, session: Session = Depends(get_session), s: Settings = Depends(get_settings)):
    return {"removed_demo_reports": traffic_svc.clear_demo(session, direction_id, clock.now(), s)}


@router.post("/reset", dependencies=[Depends(_enabled)])
def reset(session: Session = Depends(get_session), s: Settings = Depends(get_settings)):
    """Demo sıfırlama: dinamik məlumatı təmizləyir, 'normal' ssenarini yenidən qurur."""
    try:
        return demo_svc.apply_scenario(session, "normal", clock.now(), s)
    except demo_svc.DemoError as e:
        session.rollback()
        raise HTTPException(409, str(e)) from e
