import pytest

from app.geo import Polyline, haversine_m
from app.services.transit import GpsPoint, unwrap
from datetime import datetime, timezone

PTS = [(40.38, 49.84), (40.385, 49.85), (40.39, 49.862), (40.396, 49.87)]


def test_haversine_known_distance():
    # 0.01 dərəcə enlik ~ 1112 m
    assert haversine_m(40.0, 49.0, 40.01, 49.0) == pytest.approx(1111.9, rel=0.01)


def test_point_at_and_project_roundtrip():
    poly = Polyline.from_points(PTS)
    for d in (0.0, 300.0, poly.length / 2, poly.length - 1):
        lat, lon, _ = poly.point_at(d)
        prog, off = poly.project(lat, lon)
        assert prog == pytest.approx(d, abs=1.0) and off < 1.0


def test_point_at_wraps_around():
    poly = Polyline.from_points(PTS)
    a = poly.point_at(100.0)
    b = poly.point_at(100.0 + poly.length)
    assert a[0] == pytest.approx(b[0]) and a[1] == pytest.approx(b[1])


def test_unwrap_handles_lap_wrap():
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    L = 1000.0
    pts = [GpsPoint(t, 0, 0, None, p, 0) for p in (900.0, 980.0, 20.0, 100.0)]
    assert [round(p) for _, p in unwrap(pts, L)] == [900, 980, 1020, 1100]
