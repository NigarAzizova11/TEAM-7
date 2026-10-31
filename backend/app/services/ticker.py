"""Hər `sim_tick_seconds` saniyədən bir: simulyator → demo bildirişləri → analiz/xəbərdarlıqlar."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, text

from .. import clock
from ..config import get_settings
from ..db import session_scope
from ..models import CrowdReport, GpsPosition, TrafficReport
from . import analysis, demo, simulator, traffic

log = logging.getLogger("bakuflow.ticker")
RETENTION = timedelta(minutes=90)


def run_tick(now: datetime | None = None) -> dict:
    s = get_settings()
    now = now or clock.now()
    with session_scope() as session:
        got = session.execute(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": demo.SIM_LOCK_KEY}).scalar()
        if not got:
            return {"skipped": "locked"}
        if not demo.structure_exists(session):
            return {"skipped": "no_demo_structure"}
        gps = simulator.tick(session, now, s)
        bots = demo.bot_tick(session, now)
        session.flush()
        res = analysis.evaluate(session, now, s)
        traffic.reconcile_alerts(session, now, s)
        session.execute(delete(GpsPosition).where(GpsPosition.recorded_at < now - RETENTION))
        session.execute(delete(CrowdReport).where(CrowdReport.created_at < now - RETENTION))
        session.execute(delete(TrafficReport).where(TrafficReport.created_at < now - RETENTION))
        return {"gps": gps, "bot_reports": bots, "alerts_created": len(res.created), "alerts_resolved": len(res.resolved)}


async def tick_loop() -> None:
    s = get_settings()
    while True:
        await asyncio.sleep(s.sim_tick_seconds)
        try:
            await asyncio.to_thread(run_tick)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - dövr dayanmasın
            log.exception("tick xətası")
