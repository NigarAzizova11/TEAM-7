"""SQLAlchemy modelləri. Bütün vaxtlar timezone-aware UTC saxlanılır.

REAL məlumat: `stops` (dayanacaqlar.csv-dən).
DEMO/SİMULYASİYA: routes, directions, direction_stops, buses, gps_positions,
crowd_reports (source='demo_seed' olanlar), alerts (is_demo=true).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

TSTZ = DateTime(timezone=True)


class Base(DeclarativeBase):
    pass


class Stop(Base):
    """REAL dayanacaq (dayanacaqlar.csv). stop_id mətndir (əvvəlindəki sıfırlar qorunur)."""

    __tablename__ = "stops"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stop_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    source_row_id: Mapped[int | None] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    name_search: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    lat: Mapped[float] = mapped_column(Double, nullable=False)
    lon: Mapped[float] = mapped_column(Double, nullable=False)
    stop_type: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(TSTZ, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TSTZ, server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("lat BETWEEN -90 AND 90", name="ck_stops_lat"),
        CheckConstraint("lon BETWEEN -180 AND 180", name="ck_stops_lon"),
    )


class Route(Base):
    """Marşrut. `source`: 'ayna' = AYNA-dan real struktur (dayanacaq ardıcıllığı + xətt geometriyası),
    'demo' = real olmayan, real dayanacaqlardan qurulmuş demo marşrut. İkisində də avtobus hərəkəti,
    GPS və sıxlıq bildirişləri SİMULYASİYADIR (`is_demo` = dinamik məlumat simulyasiyadır)."""

    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    source: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'demo'"))
    ext_id: Mapped[int | None] = mapped_column(Integer)  # AYNA bus id (yalnız source='ayna')

    directions: Mapped[list["Direction"]] = relationship(
        back_populates="route", order_by="Direction.ordinal", cascade="all, delete-orphan"
    )


class Direction(Base):
    __tablename__ = "directions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id", ondelete="CASCADE"), nullable=False)
    ordinal: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    target_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    nominal_speed_mps: Mapped[float] = mapped_column(Double, nullable=False)
    # Simulyasiya parametrləri (yavaş seqmentlər, dayanacaq nöqtəsi və s.). Yalnız demo üçün.
    sim_params: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    # Real xətt geometriyası [[lat, lon], ...] (AYNA, sadələşdirilmiş). NULL = dayanacaqları birləşdirən sxematik xətt.
    geometry: Mapped[list[list[float]] | None] = mapped_column(JSONB)
    ext_id: Mapped[int | None] = mapped_column(Integer)  # AYNA route id

    route: Mapped[Route] = relationship(back_populates="directions")
    stops: Mapped[list["DirectionStop"]] = relationship(
        back_populates="direction", order_by="DirectionStop.seq", cascade="all, delete-orphan"
    )
    buses: Mapped[list["Bus"]] = relationship(
        back_populates="direction", order_by="Bus.id", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("route_id", "ordinal", name="uq_direction_route_ordinal"),
        CheckConstraint("target_interval_seconds > 0", name="ck_direction_interval"),
    )


class DirectionStop(Base):
    __tablename__ = "direction_stops"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    direction_id: Mapped[int] = mapped_column(ForeignKey("directions.id", ondelete="CASCADE"), nullable=False)
    seq: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    stop_pk: Mapped[int] = mapped_column(ForeignKey("stops.id", ondelete="RESTRICT"), nullable=False)

    direction: Mapped[Direction] = relationship(back_populates="stops")
    stop: Mapped[Stop] = relationship()

    __table_args__ = (UniqueConstraint("direction_id", "seq", name="uq_direction_stop_seq"),)


class Bus(Base):
    """SİMULYASİYA edilən avtobus."""

    __tablename__ = "buses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    direction_id: Mapped[int] = mapped_column(ForeignKey("directions.id", ondelete="CASCADE"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    # Simulyator vəziyyəti
    progress_m: Mapped[float] = mapped_column(Double, nullable=False, server_default=text("0"))
    mode: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'moving'"))
    last_tick_at: Mapped[datetime | None] = mapped_column(TSTZ)

    direction: Mapped[Direction] = relationship(back_populates="buses")


class GpsPosition(Base):
    __tablename__ = "gps_positions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    bus_id: Mapped[int] = mapped_column(ForeignKey("buses.id", ondelete="CASCADE"), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(TSTZ, nullable=False)
    lat: Mapped[float] = mapped_column(Double, nullable=False)
    lon: Mapped[float] = mapped_column(Double, nullable=False)
    speed_mps: Mapped[float | None] = mapped_column(Double)
    heading_deg: Mapped[float | None] = mapped_column(Double)
    source: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'simulator'"))

    __table_args__ = (Index("ix_gps_bus_time", "bus_id", "recorded_at"),)


class CrowdReport(Base):
    __tablename__ = "crowd_reports"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    bus_id: Mapped[int] = mapped_column(ForeignKey("buses.id", ondelete="CASCADE"), nullable=False)
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 1=aşağı 2=orta 3=yüksək
    session_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TSTZ, nullable=False)  # həmişə backend vaxtı
    source: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'user'"))

    __table_args__ = (
        CheckConstraint("level IN (1, 2, 3)", name="ck_report_level"),
        CheckConstraint("source IN ('user', 'demo_seed')", name="ck_report_source"),
        Index("ix_report_bus_time", "bus_id", "created_at"),
        Index("ix_report_session_bus_time", "session_hash", "bus_id", "created_at"),
    )


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id", ondelete="CASCADE"), nullable=False)
    direction_id: Mapped[int] = mapped_column(ForeignKey("directions.id", ondelete="CASCADE"), nullable=False)
    dedup_key: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)  # ACTIVE | RESOLVED
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    event: Mapped[str] = mapped_column(Text, nullable=False)
    possible_cause: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(TSTZ, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TSTZ, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(TSTZ)

    route: Mapped[Route] = relationship()
    direction: Mapped[Direction] = relationship()

    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'RESOLVED')", name="ck_alert_status"),
        # Eyni hadisə üçün eyni anda yalnız BİR aktiv xəbərdarlıq (verilənlər bazası səviyyəsində zəmanət)
        Index(
            "uq_alert_active_dedup",
            "dedup_key",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        Index("ix_alert_status_created", "status", "created_at"),
    )


class TrafficReport(Base):
    """Sərnişinin xəttdə bildirdiyi tıxac. `d_m` = nöqtənin istiqamət xətti boyunca məsafəsi (xəttə proyeksiya)."""

    __tablename__ = "traffic_reports"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    direction_id: Mapped[int] = mapped_column(ForeignKey("directions.id", ondelete="CASCADE"), nullable=False)
    d_m: Mapped[float] = mapped_column(Double, nullable=False)
    lat: Mapped[float] = mapped_column(Double, nullable=False)
    lon: Mapped[float] = mapped_column(Double, nullable=False)
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 1=yüngül 2=orta 3=ağır
    session_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TSTZ, nullable=False)  # həmişə backend vaxtı
    source: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'user'"))

    __table_args__ = (
        CheckConstraint("level IN (1, 2, 3)", name="ck_traffic_level"),
        CheckConstraint("source IN ('user', 'demo_seed')", name="ck_traffic_source"),
        Index("ix_traffic_dir_time", "direction_id", "created_at"),
    )


class DemoState(Base):
    """Tək sətirlik cədvəl: aktiv demo ssenarisi."""

    __tablename__ = "demo_state"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    scenario: Mapped[str] = mapped_column(String(32), nullable=False)
    applied_at: Mapped[datetime] = mapped_column(TSTZ, nullable=False)
    bot_levels: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    last_bot_at: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
