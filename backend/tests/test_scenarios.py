"""Demo ssenariləri REAL analiz kodundan keçir: nəticələr əl ilə yazılmır."""
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app import clock
from app.models import Alert, CrowdReport, DemoState, Stop
from app.services import analysis, demo, ticker
from tests.conftest import T0


def apply(db, settings, name):
    clock.freeze(T0)
    return demo.apply_scenario(db, name, clock.now(), settings)


def keys(db, status="ACTIVE"):
    return {a.dedup_key.split(":")[0] for a in db.execute(select(Alert).where(Alert.status == status)).scalars()}


def run_ticks(minutes):
    for _ in range(int(minutes * 60 / 15)):
        clock.advance(timedelta(seconds=15))
        ticker.run_tick(clock.now())


def test_normal_has_no_alerts_and_stays_quiet(db, stops_loaded, settings):
    apply(db, settings, "normal")
    assert keys(db) == set()
    run_ticks(12)
    db.expire_all()
    assert db.execute(select(func.count()).select_from(Alert)).scalar() == 0


def test_bunching_scenario(db, stops_loaded, settings):
    apply(db, settings, "bunching")
    a = db.execute(select(Alert).where(Alert.kind == analysis.KIND_BUNCHING)).scalar_one()
    assert a.status == "ACTIVE" and a.evidence["pair"] == ["DEMO-A-1", "DEMO-A-2"]
    assert a.evidence["gap_small_s"] < 0.4 * a.evidence["target_interval_s"]
    assert a.evidence["gap_large_s"] > 1.6 * a.evidence["target_interval_s"]
    assert "təhlükəsiz nəzarət nöqtəsində" in a.recommendation and "avtomatik əmr göndərilmir" in a.recommendation
    assert keys(db) == {"BUNCHING"}  # yalnız qruplaşma: yüksək sıxlıq və s. yoxdur
    run_ticks(6)
    db.expire_all()
    assert db.execute(select(func.count()).select_from(Alert).where(Alert.kind == analysis.KIND_BUNCHING)).scalar() == 1


def test_bunching_does_not_mix_opposite_directions(db, stops_loaded, settings):
    apply(db, settings, "bunching")
    al = db.execute(select(Alert)).scalars().all()
    assert {a.direction.ordinal for a in al} == {0} and {a.route.code for a in al} == {"DEMO-A"}
    an = analysis.analyze_all(db, clock.now(), settings)
    rev = next(x for x in an if x.dd.route.code == "DEMO-A" and x.dd.direction.ordinal == 1)
    assert rev.bunching is None  # əks istiqamət normal; düz istiqamətin yaxınlığı ilə qarışmır


def test_slowdown_scenario(db, stops_loaded, settings):
    apply(db, settings, "slowdown")
    a = db.execute(select(Alert).where(Alert.kind == analysis.KIND_SLOWDOWN)).scalar_one()
    assert len(a.evidence["buses"]) >= 2
    assert all(b["avg_speed_kmh"] < a.evidence["baseline_kmh"] * 0.5 for b in a.evidence["buses"])
    assert "mümkün" in a.title.lower() or "mümkün" in a.possible_cause.lower()
    assert "qəti" not in a.event.lower()
    assert keys(db) == {"POSSIBLE_SLOWDOWN"}


def test_unusual_stop_scenario(db, stops_loaded, settings):
    apply(db, settings, "unusual_stop")
    a = db.execute(select(Alert).where(Alert.kind == analysis.KIND_UNUSUAL_STOP)).scalar_one()
    assert a.evidence["bus"] == "DEMO-A-2"
    assert a.evidence["distance_to_nearest_stop_m"] > settings.unusual_stop_min_stop_distance_m
    assert a.evidence["stopped_for_seconds"] >= 290  # ~5 dəq (faktiki müddət, yoxlama pəncərəsi yox)
    assert "günah" in a.possible_cause and "sürücü" in a.possible_cause  # günahlandırmır, bunu açıq deyir


def test_high_crowd_scenario_goes_through_real_rule(db, stops_loaded, settings):
    apply(db, settings, "high_crowd")
    a = db.execute(select(Alert).where(Alert.kind == analysis.KIND_HIGH_CROWD)).scalar_one()
    assert a.title == "Əlavə avtobus ehtiyatı ayrılmalıdır"
    assert a.evidence["high_for_seconds"] >= settings.high_crowd_minutes * 60  # 10 dəq: qısaldılmayıb
    assert a.evidence["diagnosis"] == "capacity"  # intervallar normal + ardıcıl avtobuslar yüksək
    assert "Əlavə avtobus ehtiyatı ayrılmalıdır" in a.recommendation
    assert a.evidence["reports_in_window"]["demo_seed"] > 0 and a.evidence["reports_in_window"]["user"] == 0
    # seed bildirişlərinin əhatə etdiyi müddət ≥ 10 dəq və hamısı geridə (gələcək vaxtlı deyil)
    times = [r for r in db.execute(select(CrowdReport.created_at, CrowdReport.source)).all()]
    assert all(src == "demo_seed" for _, src in times)
    assert clock.now() - min(t for t, _ in times) >= timedelta(minutes=10)
    assert max(t for t, _ in times) <= clock.now()


def test_high_crowd_scenario_stays_single_alert_with_keepalive(db, stops_loaded, settings):
    apply(db, settings, "high_crowd")
    run_ticks(12)  # 12 dəq (açıq demo bildirişləri təzələnir)
    db.expire_all()
    rows = db.execute(select(Alert).where(Alert.kind == analysis.KIND_HIGH_CROWD)).scalars().all()
    assert len(rows) == 1 and rows[0].status == "ACTIVE"


def test_high_crowd_resolves_when_demo_reports_stop(db, stops_loaded, settings):
    apply(db, settings, "high_crowd")
    st = db.get(DemoState, 1)
    st.bot_levels = {}  # demo bildirişləri dayandırılır → məlumat köhnəlir
    db.commit()
    run_ticks(6)
    db.expire_all()
    rows = db.execute(select(Alert).where(Alert.kind == analysis.KIND_HIGH_CROWD)).scalars().all()
    assert len(rows) == 1 and rows[0].status == "RESOLVED"


def test_reset_clears_dynamic_data_but_never_touches_real_stops(db, stops_loaded, settings):
    def fingerprint():
        return db.execute(select(func.count(), func.sum(Stop.lat + Stop.lon), func.string_agg(Stop.stop_id, ",")).select_from(Stop)).one()

    before = fingerprint()
    apply(db, settings, "high_crowd")
    assert db.execute(select(func.count()).select_from(Alert)).scalar() == 1
    clock.freeze(T0 + timedelta(minutes=1))
    demo.apply_scenario(db, "normal", clock.now(), settings)  # "Demo sıfırlama"
    assert db.execute(select(func.count()).select_from(Alert)).scalar() == 0
    assert fingerprint() == before and before[0] == 3600


def test_scenarios_are_deterministic_and_repeatable(db, stops_loaded, settings):
    apply(db, settings, "slowdown")
    first = db.execute(select(Alert.evidence)).scalar_one()
    apply(db, settings, "slowdown")
    second = db.execute(select(Alert.evidence)).scalar_one()
    assert first == second


def test_unknown_scenario_rejected(db, stops_loaded, settings):
    with pytest.raises(demo.DemoError):
        demo.apply_scenario(db, "no_such", clock.now(), settings)


def test_demo_requires_imported_stops(db, settings):
    clock.freeze(T0)
    with pytest.raises(demo.DemoError, match="import-stops"):
        demo.apply_scenario(db, "normal", clock.now(), settings)
