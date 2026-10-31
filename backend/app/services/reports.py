"""Sıxlıq bildirişinin qəbulu.

- Vaxt YALNIZ backend-dən gəlir (client vaxt göndərə bilməz: schema `extra=forbid`).
- Eyni anonim sessiyadan eyni avtobusa 60 saniyədə bir bildiriş.
- Sessiya identifikatoru DB-də YALNIZ HMAC-SHA256 hash kimi saxlanılır.

MƏHDUDİYYƏT: bu tam saxtakarlıq müdafiəsi DEYİL. Anonim sessiya id-sini dəyişən şəxs cooldown-u
keçə bilər; istifadəçinin avtobusda olduğu yoxlanmır. README-də qeyd olunub.
"""
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import Bus, CrowdReport, GpsPosition
from .crowd import LEVEL_VALUE


class ReportError(Exception):
    def __init__(self, code: str, status: int, message: str, retry_after: int | None = None):
        super().__init__(message)
        self.code, self.status, self.message, self.retry_after = code, status, message, retry_after


def hash_session(session_id: str, secret: str) -> str:
    return hmac.new(secret.encode(), session_id.encode(), hashlib.sha256).hexdigest()


def submit_report(session: Session, bus_id: int, level: str, session_id: str, now: datetime, s: Settings) -> dict:
    if level not in LEVEL_VALUE:
        raise ReportError("invalid_level", 422, "Sıxlıq səviyyəsi etibarsızdır")
    bus = session.get(Bus, bus_id)
    if bus is None:
        raise ReportError("bus_not_found", 404, "Avtobus tapılmadı")
    if not bus.is_active:
        raise ReportError("bus_inactive", 409, "Bu avtobus hazırda aktiv deyil")
    last_gps = session.execute(
        select(func.max(GpsPosition.recorded_at)).where(GpsPosition.bus_id == bus_id, GpsPosition.recorded_at <= now)
    ).scalar()
    if last_gps is None or (now - last_gps).total_seconds() > s.gps_stale_seconds:
        raise ReportError("bus_offline", 409, "Avtobusun GPS məlumatı köhnədir; bildiriş qəbul edilmir")

    h = hash_session(session_id, s.session_hash_secret)
    # eyni (sessiya, avtobus) üçün paralel sorğuları sıraya sal
    session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"), {"k": f"{h}:{bus_id}"})
    last = session.execute(
        select(func.max(CrowdReport.created_at)).where(
            CrowdReport.session_hash == h, CrowdReport.bus_id == bus_id, CrowdReport.source == "user"
        )
    ).scalar()
    cooldown = timedelta(seconds=s.report_cooldown_seconds)
    if last is not None and now - last < cooldown:
        wait = int((cooldown - (now - last)).total_seconds()) + 1
        raise ReportError("rate_limited", 429, f"Eyni avtobusa {s.report_cooldown_seconds} saniyədə bir bildiriş göndərilə bilər", retry_after=wait)

    report = CrowdReport(bus_id=bus_id, level=LEVEL_VALUE[level], session_hash=h, created_at=now, source="user")
    session.add(report)
    session.commit()
    return {
        "accepted": True,
        "bus_id": bus_id,
        "level": level,
        "received_at": now.isoformat(),
        "next_allowed_at": (now + cooldown).isoformat(),
    }
