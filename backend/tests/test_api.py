"""REST API: bildiriş qəbulu, ETA, alternativ, axtarış, demo idarəetməsi, vaxt zonası."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import clock
from app.main import create_app
from app.models import Bus, CrowdReport, Direction, Route
from app.services import simulator

SID = "a" * 32
SID2 = "b" * 32


@pytest.fixture
def client(seeded):
    return TestClient(create_app())


def bus_id(db, code):
    return db.execute(select(Bus.id).where(Bus.code == code)).scalar_one()


def dir_a_fwd(db):
    return db.execute(
        select(Direction).join(Route).where(Route.code == "DEMO-A", Direction.ordinal == 0)
    ).scalar_one()


def tick(db, settings, seconds):
    for _ in range(int(seconds / 15)):
        clock.advance(timedelta(seconds=15))
        simulator.tick(db, clock.now(), settings)
    db.commit()


# ------------------------------------------------------------------ bildirişlər


def test_report_accepted_and_time_comes_from_backend(client, seeded):
    b = bus_id(seeded, "DEMO-A-1")
    r = client.post("/api/reports", json={"bus_id": b, "level": "HIGH", "session_id": SID})
    assert r.status_code == 201, r.text
    row = seeded.execute(select(CrowdReport).where(CrowdReport.bus_id == b)).scalar_one()
    assert row.created_at == clock.now()  # backend vaxtı
    assert row.created_at.tzinfo is not None and row.created_at.utcoffset() == timedelta(0)
    assert row.level == 3 and row.source == "user"
    assert SID not in row.session_hash and len(row.session_hash) == 64  # xam sessiya id saxlanmır


@pytest.mark.parametrize("extra", [{"created_at": "2020-01-01T00:00:00Z"}, {"timestamp": 1}, {"ts": "x"}, {"recorded_at": "2020-01-01T00:00:00Z"}])
def test_client_cannot_send_past_timestamp(client, seeded, extra):
    b = bus_id(seeded, "DEMO-A-1")
    r = client.post("/api/reports", json={"bus_id": b, "level": "LOW", "session_id": SID, **extra})
    assert r.status_code == 422
    assert seeded.execute(select(CrowdReport)).first() is None


@pytest.mark.parametrize("body", [
    {"bus_id": 1, "level": "EXTREME", "session_id": SID},
    {"bus_id": 1, "level": "LOW", "session_id": "short"},
    {"bus_id": 1, "level": "LOW", "session_id": "bad chars!!bad chars!!bad chars!!"},
    {"bus_id": 0, "level": "LOW", "session_id": SID},
    {"level": "LOW", "session_id": SID},
])
def test_invalid_report_bodies_rejected(client, seeded, body):
    assert client.post("/api/reports", json=body).status_code == 422


def test_cooldown_60s_same_session_same_bus(client, seeded, settings):
    b = bus_id(seeded, "DEMO-A-1")
    body = {"bus_id": b, "level": "HIGH", "session_id": SID}
    assert client.post("/api/reports", json=body).status_code == 201
    r = client.post("/api/reports", json=body)
    assert r.status_code == 429
    assert 1 <= int(r.headers["Retry-After"]) <= 61 and r.json()["code"] == "rate_limited"
    # başqa avtobus və başqa sessiya olar
    assert client.post("/api/reports", json={**body, "bus_id": bus_id(seeded, "DEMO-A-2")}).status_code == 201
    assert client.post("/api/reports", json={**body, "session_id": SID2}).status_code == 201
    tick(seeded, settings, 45)
    assert client.post("/api/reports", json=body).status_code == 429  # 45 san: hələ tezdir
    tick(seeded, settings, 30)  # cəmi 75 san
    assert client.post("/api/reports", json=body).status_code == 201
    assert len(seeded.execute(select(CrowdReport)).scalars().all()) == 4


def test_report_rejected_for_offline_bus_and_unknown_bus(client, seeded):
    clock.advance(timedelta(minutes=2))  # GPS ticklənmədi → köhnə
    b = bus_id(seeded, "DEMO-A-1")
    r = client.post("/api/reports", json={"bus_id": b, "level": "LOW", "session_id": SID})
    assert r.status_code == 409 and r.json()["code"] == "bus_offline"
    assert client.post("/api/reports", json={"bus_id": 99999, "level": "LOW", "session_id": SID}).status_code == 404


# ------------------------------------------------------------------ gəliş / ETA


def get_arrivals(client, d, stop_id):
    r = client.get("/api/arrivals", params={"direction_id": d.id, "stop_id": stop_id})
    assert r.status_code == 200, r.text
    return r.json()


def middle_stop(client, d):
    det = client.get(f"/api/directions/{d.id}").json()
    return det, det["stops"][len(det["stops"]) // 2]


def test_arrivals_never_show_passed_bus_as_approaching(client, seeded):
    d = dir_a_fwd(seeded)
    det, stop = middle_stop(client, d)
    res = get_arrivals(client, d, stop["stop_id"])
    statuses = {b["status"] for b in res["buses"]}
    assert "approaching" in statuses and "passed" in statuses  # dayanacağın hər iki tərəfində avtobus var
    from app.geo import Polyline

    poly = Polyline.from_points([tuple(p) for p in det["polyline"]])
    for b in res["buses"]:
        prog, _ = poly.project(b["lat"], b["lon"])  # müstəqil yoxlama: GPS-i xəttə proyeksiya et
        if b["status"] == "approaching":
            assert prog < stop["distance_m"] and b["eta_seconds"] > 0
        if b["status"] == "passed":
            assert prog > stop["distance_m"] and b["eta_seconds"] is None
    etas = [b["eta_seconds"] for b in res["buses"] if b["status"] == "approaching"]
    assert etas == sorted(etas)


def test_eta_matches_distance_over_speed(client, seeded):
    d = dir_a_fwd(seeded)
    _, stop = middle_stop(client, d)
    res = get_arrivals(client, d, stop["stop_id"])
    for b in res["buses"]:
        if b["status"] == "approaching":
            v = b["speed_kmh"] / 3.6
            assert b["eta_seconds"] == pytest.approx(b["distance_to_stop_m"] / v, abs=2)


def test_no_data_is_reported_as_null_not_low(client, seeded):
    d = dir_a_fwd(seeded)
    _, stop = middle_stop(client, d)
    for b in get_arrivals(client, d, stop["stop_id"])["buses"]:
        assert b["crowd"]["level"] is None and b["crowd"]["reports_count"] == 0


def test_report_shows_up_in_arrivals_and_overview(client, seeded):
    d = dir_a_fwd(seeded)
    _, stop = middle_stop(client, d)
    b = bus_id(seeded, "DEMO-A-2")
    client.post("/api/reports", json={"bus_id": b, "level": "HIGH", "session_id": SID})
    res = get_arrivals(client, d, stop["stop_id"])
    bus = next(x for x in res["buses"] if x["id"] == b)
    assert bus["crowd"]["level"] == "HIGH" and bus["crowd"]["reports_count"] == 1
    ov = client.get("/api/operator/overview").json()
    line = next(x for x in ov["directions"] if x["direction"]["id"] == d.id)
    assert line["crowd"]["coverage"] == {"buses_with_data": 1, "active_buses": 3, "ratio": 0.33}
    assert line["crowd"]["level"] is None and line["crowd"]["reason_no_result"] == "low_coverage"


def test_alternative_only_when_next_bus_is_clearly_emptier(client, seeded):
    d = dir_a_fwd(seeded)
    det = client.get(f"/api/directions/{d.id}").json()
    stop = det["stops"][-2]  # sona yaxın dayanacaq: ≥2 avtobus hələ yaxınlaşır
    res = get_arrivals(client, d, stop["stop_id"])
    appro = [b for b in res["buses"] if b["status"] == "approaching"]
    assert len(appro) >= 2
    first, second = appro[0]["id"], appro[1]["id"]

    def add(bid, level):
        seeded.add(CrowdReport(bus_id=bid, level=level, session_hash="x" * 16, created_at=clock.now(), source="user"))
        seeded.commit()

    assert get_arrivals(client, d, stop["stop_id"])["alternative"] is None  # məlumat yox
    add(first, 3)
    assert get_arrivals(client, d, stop["stop_id"])["alternative"] is None  # ikincidə məlumat yox: uydurma
    add(second, 3)
    assert get_arrivals(client, d, stop["stop_id"])["alternative"] is None  # eyni sıxlıq
    seeded.execute(CrowdReport.__table__.delete().where(CrowdReport.bus_id == second))
    add(second, 1)
    alt = get_arrivals(client, d, stop["stop_id"])["alternative"]
    assert alt and alt["bus_id"] == second and alt["level"] == "LOW" and alt["first_level"] == "HIGH"
    assert alt["reports_count"] == 1 and alt["data_age_seconds"] is not None  # aktuallıq göstərilir


def test_arrivals_validation_and_404(client, seeded):
    d = dir_a_fwd(seeded)
    assert client.get("/api/arrivals", params={"direction_id": d.id, "stop_id": "nope"}).status_code == 404
    assert client.get("/api/arrivals", params={"direction_id": 99999, "stop_id": "00001"}).status_code == 404
    assert client.get("/api/arrivals").status_code == 422


# ------------------------------------------------------------------ axtarış və strukturlar


def test_stop_search_azerbaijani_folding_and_served_by(client, seeded):
    d = dir_a_fwd(seeded)
    det, stop = middle_stop(client, d)
    r = client.get("/api/stops", params={"q": stop["name"].upper()})  # böyük hərflə də tapılmalıdır
    assert r.status_code == 200
    hit = next(s for s in r.json()["stops"] if s["stop_id"] == stop["stop_id"])
    assert hit["is_real"] is True and any(x["direction_id"] == d.id for x in hit["served_by"])
    far = client.get("/api/stops", params={"q": "sintetik dayanacaq 1"}).json()["stops"]
    assert far and any(not s["served_by"] for s in far)  # demo xəttdə olmayan REAL dayanacaq da tapılır
    assert client.get("/api/stops", params={"q": "a"}).status_code == 422
    assert client.get("/api/stops", params={"q": "%%"}).json()["stops"] == []  # LIKE metasimvolu qaçırılır


def test_routes_are_marked_demo_and_directions_are_separate(client, seeded):
    routes = client.get("/api/routes").json()["routes"]
    assert [r["name"] for r in routes] == ["Demo A", "Demo B"]
    assert all(r["is_demo"] for r in routes)
    assert len(routes[0]["directions"]) == 2 and len(routes[1]["directions"]) == 1
    det = client.get(f"/api/directions/{routes[0]['directions'][0]['id']}").json()
    assert "sxematik" in det["polyline_note"].lower() and len(det["polyline"]) == len(det["stops"])
    rev = client.get(f"/api/directions/{routes[0]['directions'][1]['id']}").json()
    assert [s["stop_id"] for s in rev["stops"]] == [s["stop_id"] for s in reversed(det["stops"])]


def test_timestamps_in_api_are_timezone_aware_utc(client, seeded):
    ov = client.get("/api/operator/overview").json()
    t = datetime.fromisoformat(ov["server_time"])
    assert t.tzinfo is not None and t.utcoffset() == timedelta(0)


def test_gps_and_alert_columns_are_timezone_aware(seeded):
    from app.models import GpsPosition

    g = seeded.execute(select(GpsPosition).limit(1)).scalar_one()
    assert g.recorded_at.tzinfo is not None and g.recorded_at.utcoffset() == timedelta(0)


# ------------------------------------------------------------------ demo idarəetməsi / operator


def test_demo_endpoints_apply_scenario_and_reset(client, seeded):
    st = client.get("/api/demo/status").json()
    assert st["stops_loaded"] == 3600 and {s["name"] for s in st["scenarios"]} >= {"normal", "bunching", "slowdown", "high_crowd"}
    r = client.post("/api/demo/scenarios/high_crowd")
    assert r.status_code == 200 and r.json()["alerts_created"] == 1
    alerts = client.get("/api/operator/alerts", params={"status": "ACTIVE"}).json()["alerts"]
    assert len(alerts) == 1 and alerts[0]["title"] == "Əlavə avtobus ehtiyatı ayrılmalıdır" and alerts[0]["is_demo"]
    assert client.post("/api/demo/reset").status_code == 200
    assert client.get("/api/operator/alerts", params={"status": "ACTIVE"}).json()["alerts"] == []
    assert client.post("/api/demo/scenarios/nope").status_code == 404


def test_demo_endpoints_can_be_disabled(client, seeded, settings, monkeypatch):
    monkeypatch.setattr(settings, "demo_endpoints_enabled", False)
    assert client.get("/api/demo/status").status_code == 404
    assert client.post("/api/demo/reset").status_code == 404


def test_operator_overview_shape(client, seeded):
    ov = client.get("/api/operator/overview").json()
    assert ov["rules"]["high_crowd_minutes"] == 10 and "demo qaydalarıdır" in ov["rules"]["note"]
    assert len(ov["directions"]) == 3
    for x in ov["directions"]:
        assert {"intervals", "crowd", "target_interval_seconds", "buses", "diagnosis"} <= x.keys()
        assert x["crowd"]["high_threshold_seconds"] == 600
        assert x["intervals"]["target_s"] == x["target_interval_seconds"]
        assert all(b["is_simulated"] for b in x["buses"])


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
