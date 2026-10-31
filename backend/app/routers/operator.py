from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from .. import clock
from ..config import Settings, get_settings
from ..db import get_session
from ..services import traffic, views

# QEYD: prototipdə operator endpointləri autentifikasiya olunmur (README-də açıq yazılıb).
router = APIRouter(prefix="/api/operator", tags=["operator"])


@router.get("/overview")
def overview(session: Session = Depends(get_session), s: Settings = Depends(get_settings)):
    return views.operator_overview(session, clock.now(), s)


class AlertActionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["confirm", "dismiss"]


@router.post("/alerts/{alert_id}/action")
def alert_action(alert_id: int, body: AlertActionIn, session: Session = Depends(get_session), s: Settings = Depends(get_settings)):
    """Operator qərarı: confirm = təsdiq/qəbul, dismiss = yalan tıxac bildirişi (yalnız TRAFFIC_JAM)."""
    try:
        return traffic.operator_action(session, alert_id, body.action, clock.now(), s)
    except traffic.TrafficError as e:
        session.rollback()
        raise HTTPException(e.status, e.message) from e


@router.get("/alerts")
def alerts(
    status: Literal["ACTIVE", "RESOLVED", "ALL"] = "ALL",
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_session),
):
    return {"alerts": views.list_alerts(session, status, limit)}
