"""Tıxac: bildiriş qəbulu, klasterləşmə/səviyyə, operator xəbərdarlığı, alternativ yol girişi, demo."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import clock
from app.main import create_app
from app.models import Alert, Direction, Route, TrafficReport
from app.services import traffic
from app.services.transit import stop_infos

SIDS = [c * 32 for c in "abcdefgh"]


@pytest.fixture
def client(seeded):
    return TestClient(create_app())


def a_dir(db):
    return db.execute(select(Direction).join(Route).where(Route.code == "DEMO-A", Direction.ordinal == 0)).scalar_one()


def point_at(db, d, frac):
    _, poly = stop_infos(d)
    la, lo, _ = poly.point_at(poly.length * frac)
    return la, lo


def post(client, d, frac, level, sid, db):
    la, lo = point_at(db, d, frac)
    return client.post("/api/traffic-reports", json={"direction_id": d.id, "lat": la, "lon": lo, "level": level, "session_id": sid})


def test_single_heavy_report_reaches_operator_as_unconfirmed(client, seeded):
    d = a_dir(seeded)
    assert post(client, d, 0.5, "HIGH", SIDS[0], seeded).status_code == 201
    j = client.get(f"/api/directions/{d.id}/traffic").json()
    assert j["jams"][0]["level"] == "UNCONFIRMED" and j["jams"][0]["reports"] == 1
    assert "detour" not in j["jams"][0]
    al = seeded.execute(select(Alert).where(Alert.kind == traffic.KIND_TRAFFIC, Alert.status == "ACTIVE")).scalar_one()
    assert "təsdiqlənməyib" in al.title and al.evidence["confirmed_by_multiple_passengers"] is False
    ov = client.get("/api/operator/overview").json()["traffic"][str(d.id)]
    assert ov["jams"][0]["heavy_unconfirmed"] is True and ov["route_code"] == "DEMO-A"


def test_three_heavy_reports_create_operator_alert_then_resolve(client, seeded):
    d = a_dir(seeded)
    for sid in SIDS[:3]:
        assert post(client, d, 0.5, "HIGH", sid, seeded).status_code == 201
    j = client.get(f"/api/directions/{d.id}/traffic").json()
    jam = j["jams"][0]
    assert jam["level"] == "HIGH" and jam["reports"] == 3 and len(jam["path"]) >= 2
    assert jam["detour"]["affected_stops"] and jam["detour"]["from"] != jam["detour"]["to"]
    alerts = seeded.execute(select(Alert).where(Alert.kind == traffic.KIND_TRAFFIC, Alert.status == "ACTIVE")).scalars().all()
    assert len(alerts) == 1 and alerts[0].direction_id == d.id and "ağır tıxac" in alerts[0].event.lower()
    ov = client.get("/api/operator/overview").json()
    assert ov["traffic"][str(d.id)]["level"] == "HIGH"
    # vaxt keçir: bildirişlər köhnəlir -> xəbərdarlıq HƏLL olunur
    clock.advance(timedelta(minutes=16))
    traffic.reconcile_alerts(seeded, clock.now(), traffic_settings())
    seeded.commit()
    al = seeded.execute(select(Alert).where(Alert.kind == traffic.KIND_TRAFFIC)).scalar_one()
    assert al.status == "RESOLVED"


def traffic_settings():
    from app.config import get_settings

    return get_settings()


def test_no_duplicate_active_alert_on_more_reports(client, seeded):
    d = a_dir(seeded)
    for sid in SIDS[:5]:
        post(client, d, 0.5, "HIGH", sid, seeded)
    n = seeded.execute(select(Alert).where(Alert.kind == traffic.KIND_TRAFFIC, Alert.status == "ACTIVE")).scalars().all()
    assert len(n) == 1


def test_light_reports_do_not_alert(client, seeded):
    d = a_dir(seeded)
    for sid in SIDS[:4]:
        post(client, d, 0.5, "LOW", sid, seeded)
    j = client.get(f"/api/directions/{d.id}/traffic").json()
    assert j["jams"][0]["level"] == "LOW"
    assert seeded.execute(select(Alert).where(Alert.kind == traffic.KIND_TRAFFIC)).first() is None


def test_far_apart_reports_form_separate_jams(client, seeded):
    d = a_dir(seeded)
    post(client, d, 0.2, "HIGH", SIDS[0], seeded)
    post(client, d, 0.8, "HIGH", SIDS[1], seeded)
    assert len(client.get(f"/api/directions/{d.id}/traffic").json()["jams"]) == 2


def test_same_session_counts_once_and_is_rate_limited(client, seeded):
    d = a_dir(seeded)
    assert post(client, d, 0.5, "HIGH", SIDS[0], seeded).status_code == 201
    r = post(client, d, 0.5, "HIGH", SIDS[0], seeded)
    assert r.status_code == 429 and r.json()["retry_after_seconds"] > 0


def test_off_route_point_rejected_and_validation(client, seeded):
    d = a_dir(seeded)
    la, lo = point_at(seeded, d, 0.5)
    r = client.post("/api/traffic-reports", json={"direction_id": d.id, "lat": la + 0.05, "lon": lo, "level": "HIGH", "session_id": SIDS[0]})
    assert r.status_code == 422 and r.json()["code"] == "off_route"
    bad = client.post("/api/traffic-reports", json={"direction_id": d.id, "lat": la, "lon": lo, "level": "HIGH", "session_id": SIDS[0], "created_at": "2020-01-01"})
    assert bad.status_code == 422  # client vaxt göndərə bilməz
    assert client.post("/api/traffic-reports", json={"direction_id": 999999, "lat": la, "lon": lo, "level": "HIGH", "session_id": SIDS[0]}).status_code == 404


def test_demo_jam_is_labelled_and_clearable(client, seeded):
    d = a_dir(seeded)
    assert client.post(f"/api/demo/traffic?direction_id={d.id}&level=HIGH").status_code == 200
    j = client.get(f"/api/directions/{d.id}/traffic").json()
    assert j["jams"][0]["level"] == "HIGH" and j["jams"][0]["demo_reports"] == j["jams"][0]["reports"]
    al = seeded.execute(select(Alert).where(Alert.kind == traffic.KIND_TRAFFIC, Alert.status == "ACTIVE")).scalar_one()
    assert al.is_demo is True
    assert client.delete(f"/api/demo/traffic?direction_id={d.id}").json()["removed_demo_reports"] >= 3
    seeded.expire_all()
    assert seeded.execute(select(Alert).where(Alert.kind == traffic.KIND_TRAFFIC, Alert.status == "ACTIVE")).first() is None
    assert client.get(f"/api/directions/{d.id}/traffic").json()["jams"] == []


def test_scenario_reset_clears_traffic(client, seeded):
    d = a_dir(seeded)
    client.post(f"/api/demo/traffic?direction_id={d.id}&level=HIGH")
    client.post("/api/demo/reset")
    seeded.expire_all()
    assert seeded.execute(select(TrafficReport)).first() is None


def test_slice_points_and_classify(seeded):
    d = a_dir(seeded)
    _, poly = stop_infos(d)
    pts = traffic.slice_points(poly, 100, 900)
    assert len(pts) >= 2
    s = traffic_settings()
    assert traffic.classify(1, 3.0, s) == "UNCONFIRMED"
    assert traffic.classify(2, 1.0, s) == "LOW" and traffic.classify(2, 2.0, s) == "MEDIUM" and traffic.classify(2, 2.6, s) == "HIGH"


def test_two_heavy_reports_make_confirmed_alert(client, seeded):
    d = a_dir(seeded)
    for sid in SIDS[:2]:
        post(client, d, 0.5, "HIGH", sid, seeded)
    j = client.get(f"/api/directions/{d.id}/traffic").json()
    assert j["jams"][0]["level"] == "HIGH" and j["jams"][0]["reports"] == 2
    al = seeded.execute(select(Alert).where(Alert.kind == traffic.KIND_TRAFFIC, Alert.status == "ACTIVE")).scalar_one()
    assert "təsdiqlənməyib" not in al.title and al.evidence["confirmed_by_multiple_passengers"] is True


def test_same_session_multiple_rows_counted_once(client, seeded):
    d = a_dir(seeded)
    la, lo = point_at(seeded, d, 0.5)
    now = clock.now()
    for i in range(4):
        seeded.add(TrafficReport(direction_id=d.id, d_m=1000.0, lat=la, lon=lo, level=3, session_hash="same", created_at=now - timedelta(seconds=i), source="user"))
    seeded.commit()
    jam = client.get(f"/api/directions/{d.id}/traffic").json()["jams"][0]
    assert jam["reports"] == 1 and jam["level"] == "UNCONFIRMED"


def test_operator_confirm_and_dismiss(client, seeded):
    d = a_dir(seeded)
    post(client, d, 0.5, "HIGH", SIDS[0], seeded)
    al = seeded.execute(select(Alert).where(Alert.kind == traffic.KIND_TRAFFIC, Alert.status == "ACTIVE")).scalar_one()
    r = client.post(f"/api/operator/alerts/{al.id}/action", json={"action": "confirm"})
    assert r.status_code == 200 and r.json()["operator"]["action"] == "CONFIRMED"
    seeded.expire_all()
    al = seeded.get(Alert, al.id)
    assert "operator təsdiq etdi" in al.title and "təsdiqlənməyib" not in al.title
    post(client, d, 0.5, "HIGH", SIDS[1], seeded)  # yeni bildiriş qərarı silməməlidir
    seeded.expire_all()
    al = seeded.get(Alert, al.id)
    assert al.evidence["operator"]["action"] == "CONFIRMED" and "operator təsdiq etdi" in al.title
    r = client.post(f"/api/operator/alerts/{al.id}/action", json={"action": "dismiss"})
    assert r.status_code == 200 and r.json()["status"] == "RESOLVED"
    seeded.expire_all()
    assert seeded.execute(select(TrafficReport)).first() is None
    assert client.post(f"/api/operator/alerts/{al.id}/action", json={"action": "confirm"}).status_code == 409
    assert client.post("/api/operator/alerts/99999/action", json={"action": "confirm"}).status_code == 404
    assert client.post(f"/api/operator/alerts/{al.id}/action", json={"action": "x"}).status_code == 422


def test_dismiss_not_allowed_for_other_kinds(client, seeded):
    from app.models import Alert as A
    d = a_dir(seeded)
    now = clock.now()
    other = A(kind="BUNCHING", route_id=d.route_id, direction_id=d.id, dedup_key="BUNCHING:x", status="ACTIVE", title="t", event="e",
              possible_cause="c", evidence={}, recommendation="r", is_demo=True, created_at=now, updated_at=now)
    seeded.add(other); seeded.commit()
    assert client.post(f"/api/operator/alerts/{other.id}/action", json={"action": "dismiss"}).status_code == 422
    assert client.post(f"/api/operator/alerts/{other.id}/action", json={"action": "confirm"}).status_code == 200
