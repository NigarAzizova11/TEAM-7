"""Məcburi qayda: xətt üzrə yüksək sıxlıq AKTUAL məlumatlarla 10 dəqiqə davam edərsə
"Əlavə avtobus ehtiyatı ayrılmalıdır" xəbərdarlığı. Qayda 10 dəqiqəlik qalır (10 saniyəyə endirilmir):
saat dondurulub və simulyasiya edilmiş vaxt dəqiqə-dəqiqə irəli aparılır.
"""
import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Alert
from app.services.analysis import HIGH_CROWD_TITLE, KIND_HIGH_CROWD

ALL3 = {"DEMO-A-1": 3, "DEMO-A-2": 3, "DEMO-A-3": 3}


def test_default_threshold_is_really_ten_minutes(settings):
    assert settings.high_crowd_minutes == 10
    assert settings.persistence_step_seconds == 60
    assert settings.crowd_window_minutes == 5


def test_no_alert_before_10_minutes_then_alert_with_exact_text(harness):
    h = harness
    h.run(10, reports=lambda m: ALL3)  # dəqiqə 1..10: davamlılıq 9 dəq
    assert h.active_alerts(KIND_HIGH_CROWD) == []
    h.run(1, reports=lambda m: ALL3)  # dəqiqə 11: davamlılıq 10 dəq
    alerts = h.active_alerts(KIND_HIGH_CROWD)
    assert len(alerts) == 1
    a = alerts[0]
    assert a.title == "Əlavə avtobus ehtiyatı ayrılmalıdır" == HIGH_CROWD_TITLE
    assert a.evidence["high_for_seconds"] >= 600
    assert a.evidence["coverage"] == {"buses_with_data": 3, "active_buses": 3}
    assert a.possible_cause and a.recommendation and a.event  # səbəb, tövsiyə, hadisə


def test_threshold_is_configurable_not_hardcoded(harness, monkeypatch):
    monkeypatch.setattr(harness.s, "high_crowd_minutes", 5)
    harness.run(5, reports=lambda m: ALL3)
    assert harness.active_alerts(KIND_HIGH_CROWD) == []
    harness.run(1, reports=lambda m: ALL3)
    assert len(harness.active_alerts(KIND_HIGH_CROWD)) == 1


def test_single_old_report_never_creates_alert_ten_minutes_later(harness):
    h = harness
    h.run(1, reports=lambda m: ALL3)  # hər avtobusdan BİR yüksək bildiriş
    h.run(14, reports=None)  # sonra heç nə
    assert h.all_alerts(KIND_HIGH_CROWD) == []


def test_stale_data_resets_persistence(harness):
    h = harness
    h.run(6, reports=lambda m: ALL3)  # dəq 1..6 YÜKSƏK
    h.run(6, reports=None)  # dəq 7..12: məlumat köhnəlir (5 dəq pəncərə)
    # köhnəlmə nəticəsində davamlılıq kəsildi; yenidən başlayır
    h.run(5, reports=lambda m: ALL3)  # dəq 13..17
    assert h.all_alerts(KIND_HIGH_CROWD) == []  # 1..6 və 13..17 birləşib 10 dəq sayılmamalıdır
    h.run(6, reports=lambda m: ALL3)  # dəq 18..23: yeni fasiləsiz seriya 11 dəq oldu
    assert len(h.active_alerts(KIND_HIGH_CROWD)) == 1


def test_no_duplicate_alert_on_repeated_polling(harness):
    h = harness
    h.run(11, reports=lambda m: ALL3)
    assert len(h.all_alerts(KIND_HIGH_CROWD)) == 1
    from app.services import analysis

    for _ in range(5):  # eyni anda təkrar təkrar analiz (polling)
        res = analysis.evaluate(h.db, h.now(), h.s)
        assert res.created == []
    h.run(5, reports=lambda m: ALL3)  # davam edən hadisə
    assert len(h.all_alerts(KIND_HIGH_CROWD)) == 1
    assert len(h.active_alerts(KIND_HIGH_CROWD)) == 1


def test_db_refuses_second_active_alert_with_same_key(harness):
    h = harness
    h.run(11, reports=lambda m: ALL3)
    first = h.active_alerts(KIND_HIGH_CROWD)[0]
    dup = Alert(
        kind=first.kind, route_id=first.route_id, direction_id=first.direction_id, dedup_key=first.dedup_key,
        status="ACTIVE", title="x", event="x", possible_cause="x", evidence={}, recommendation="x",
        created_at=h.now(), updated_at=h.now(),
    )
    h.db.add(dup)
    with pytest.raises(IntegrityError):
        h.db.flush()
    h.db.rollback()


def test_resolves_when_data_goes_stale_and_new_event_needs_full_10_minutes_again(harness):
    h = harness
    h.run(11, reports=lambda m: ALL3)
    assert len(h.active_alerts(KIND_HIGH_CROWD)) == 1
    h.run(6, reports=None)  # məlumat köhnələr → HƏLL OLUNUR
    assert h.active_alerts(KIND_HIGH_CROWD) == []
    resolved = h.all_alerts(KIND_HIGH_CROWD)
    assert len(resolved) == 1 and resolved[0].status == "RESOLVED" and resolved[0].resolved_at is not None
    h.run(9, reports=lambda m: ALL3)  # yeni hadisə: 9 dəq hələ kifayət deyil
    assert h.active_alerts(KIND_HIGH_CROWD) == []
    h.run(2, reports=lambda m: ALL3)
    assert len(h.active_alerts(KIND_HIGH_CROWD)) == 1
    assert len(h.all_alerts(KIND_HIGH_CROWD)) == 2  # köhnə həll olunmuş + yeni


def test_resolves_when_crowd_drops(harness):
    h = harness
    h.run(11, reports=lambda m: ALL3)
    assert len(h.active_alerts(KIND_HIGH_CROWD)) == 1
    h.run(8, reports=lambda m: {c: 1 for c in ALL3})  # hamı "Aşağı" bildirir
    assert h.active_alerts(KIND_HIGH_CROWD) == []
    assert h.all_alerts(KIND_HIGH_CROWD)[0].status == "RESOLVED"


def test_insufficient_coverage_does_not_alert(harness):
    h = harness
    h.run(15, reports=lambda m: {"DEMO-A-1": 3})  # 3 avtobusdan yalnız 1-i (əhatə 33% < 50%)
    assert h.all_alerts(KIND_HIGH_CROWD) == []
    h.run(11, reports=lambda m: {"DEMO-A-1": 3, "DEMO-A-2": 3})  # 2/3 = 67%
    assert len(h.active_alerts(KIND_HIGH_CROWD)) == 1


def test_no_data_is_not_low_and_mixed_levels_not_high(harness):
    h = harness
    h.run(12, reports=lambda m: {"DEMO-A-1": 3, "DEMO-A-2": 1, "DEMO-A-3": 2})  # ortalama 2.0 = ORTA
    assert h.all_alerts(KIND_HIGH_CROWD) == []
