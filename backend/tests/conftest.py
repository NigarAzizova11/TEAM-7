import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://bakuflow:bakuflow_dev_pw@127.0.0.1:5432/bakuflow_test"
)
# TƏHLÜKƏSİZLİK: testlər bazanı silir; yalnız adı *_test ilə bitən bazada işləyir.
if not TEST_DB_URL.split("?")[0].endswith("_test"):
    raise RuntimeError("TEST_DATABASE_URL bazasının adı '_test' ilə bitməlidir (testlər cədvəlləri təmizləyir)")
os.environ["DATABASE_URL"] = TEST_DB_URL  # shell-dəki dev bazanı əzməsin
os.environ["SESSION_HASH_SECRET"] = "test-secret-not-for-production"
os.environ["SIM_AUTOSTART"] = "false"
os.environ["DEMO_ENDPOINTS_ENABLED"] = "true"

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app import clock  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import SessionLocal, get_engine  # noqa: E402
from app.services import analysis, demo, simulator  # noqa: E402
from app.services.csv_import import import_stops  # noqa: E402
from app.models import CrowdReport, DemoState, Bus  # noqa: E402
from sqlalchemy import select, delete  # noqa: E402
from tests.synth import write_csv  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _migrated_db():
    """Sınaq bazasını sıfırdan Alembic miqrasiyası ilə qur (miqrasiyanın özü də yoxlanır)."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def _clean(_migrated_db):
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE alerts, crowd_reports, gps_positions, buses, direction_stops, directions, "
                "routes, stops, demo_state RESTART IDENTITY CASCADE"
            )
        )
    clock.unfreeze()
    yield
    clock.unfreeze()


@pytest.fixture
def settings(monkeypatch):
    s = get_settings()
    # hər test default-larla başlasın (testlər içində monkeypatch ilə dəyişir)
    for k in ("high_crowd_minutes", "crowd_window_minutes", "report_cooldown_seconds"):
        monkeypatch.setattr(s, k, getattr(s, k))
    return s


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def csv_path(tmp_path):
    return write_csv(tmp_path / "dayanacaqlar.csv")


@pytest.fixture
def stops_loaded(db, csv_path):
    return import_stops(db, csv_path)


T0 = datetime(2026, 10, 31, 8, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def seeded(db, stops_loaded, settings):
    """Demo struktur + 'normal' ssenari, T0 anında (dondurulmuş saat). Bot bildirişləri söndürülüb:
    hər test bildirişləri özü idarə edir."""
    clock.freeze(T0)
    demo.apply_scenario(db, "normal", clock.now(), settings)
    st = db.get(DemoState, 1)
    st.bot_levels = {}
    st.last_bot_at = {}
    db.execute(delete(CrowdReport))
    db.commit()
    return db


class Harness:
    """Dondurulmuş saatı irəli aparır: simulyator GPS-i hər 15 san, bildirişlər və analiz hər dəqiqə."""

    def __init__(self, db, settings):
        self.db, self.s = db, settings
        self.buses = {b.code: b.id for b in db.execute(select(Bus)).scalars()}
        self.history: list[analysis.EvalResult] = []

    def now(self):
        return clock.now()

    def add_report(self, code: str, level: int, source: str = "user", at: datetime | None = None):
        self.db.add(
            CrowdReport(
                bus_id=self.buses[code],
                level=level,
                session_hash=f"h-{code}-{clock.now().timestamp()}",
                created_at=at or clock.now(),
                source=source,
            )
        )
        self.db.flush()

    def run(self, minutes: float, reports=None, evaluate: bool = True):
        """reports: callable(minute_index) -> {bus_code: level} (yalnız dəqiqə sərhədlərində)."""
        steps = int(minutes * 60 / 15)
        for i in range(steps):
            clock.advance(timedelta(seconds=15))
            simulator.tick(self.db, clock.now(), self.s)
            if (i + 1) % 4 == 0:
                m = (i + 1) // 4
                if reports:
                    for code, lvl in (reports(m) or {}).items():
                        self.add_report(code, lvl)
                if evaluate:
                    self.history.append(analysis.evaluate(self.db, clock.now(), self.s))
        self.db.commit()

    def active_alerts(self, kind: str | None = None):
        from app.models import Alert

        q = select(Alert).where(Alert.status == "ACTIVE")
        if kind:
            q = q.where(Alert.kind == kind)
        return self.db.execute(q).scalars().all()

    def all_alerts(self, kind: str | None = None):
        from app.models import Alert

        q = select(Alert).order_by(Alert.id)
        if kind:
            q = q.where(Alert.kind == kind)
        return self.db.execute(q).scalars().all()


@pytest.fixture
def harness(seeded, settings):
    return Harness(seeded, settings)
