from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReportIn(BaseModel):
    """Vaxt sahəsi YOXDUR və `extra=forbid`: client keçmiş/gələcək vaxtlı bildiriş göndərə bilməz."""

    model_config = ConfigDict(extra="forbid")

    bus_id: int = Field(gt=0)
    level: Literal["LOW", "MEDIUM", "HIGH"]
    session_id: str = Field(min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class TrafficReportIn(BaseModel):
    """Vaxt sahəsi YOXDUR, `extra=forbid`. Nöqtə server tərəfdə istiqamət xəttinə proyeksiya olunur."""

    model_config = ConfigDict(extra="forbid")

    direction_id: int = Field(gt=0)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    level: Literal["LOW", "MEDIUM", "HIGH"]
    session_id: str = Field(min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class ReportOut(BaseModel):
    accepted: bool
    bus_id: int
    level: str
    received_at: str
    next_allowed_at: str
