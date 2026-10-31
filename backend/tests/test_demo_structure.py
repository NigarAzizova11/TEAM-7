"""Demo marşrutların real dayanacaqlardan seçilməsi."""
import pytest
from sqlalchemy import select

from app import clock
from app.models import Direction, DirectionStop, Route, Stop
from app.services import demo
from app.services.transit import stop_infos
from tests.conftest import T0


def chains(db):
    out = {}
    for d in db.execute(select(Direction).join(Route).order_by(Route.id, Direction.ordinal)).scalars():
        out[(d.route.code, d.ordinal)] = [ds.stop.stop_id for ds in sorted(d.stops, key=lambda x: x.seq)]
    return out


def test_demo_routes_use_real_stops_only_and_are_labelled_demo(db, stops_loaded, settings):
    clock.freeze(T0)
    demo.apply_scenario(db, "normal", clock.now(), settings)
    all_ids = set(db.execute(select(Stop.stop_id)).scalars())
    for key, ids in chains(db).items():
        assert set(ids) <= all_ids and len(ids) >= 6
    assert [r.name for r in db.execute(select(Route).order_by(Route.id)).scalars()] == ["Demo A", "Demo B"]
    assert all(r.is_demo for r in db.execute(select(Route)).scalars())


def test_chain_selection_is_deterministic_and_routes_do_not_share_stops(db, stops_loaded, settings):
    clock.freeze(T0)
    demo.apply_scenario(db, "normal", clock.now(), settings)
    first = chains(db)
    demo.apply_scenario(db, "normal", clock.now(), settings, rebuild_structure=True)
    assert chains(db) == first
    assert not set(first[("DEMO-A", 0)]) & set(first[("DEMO-B", 0)])
    assert first[("DEMO-A", 1)] == list(reversed(first[("DEMO-A", 0)]))


def test_chain_is_close_stops_in_baku_with_sane_spacing(db, stops_loaded, settings):
    from app.geo import haversine_m

    clock.freeze(T0)
    demo.apply_scenario(db, "normal", clock.now(), settings)
    for d in db.execute(select(Direction)).scalars():
        stops, poly = stop_infos(d)
        for a, b in zip(stops, stops[1:]):
            assert 150 <= haversine_m(a.lat, a.lon, b.lat, b.lon) <= 2000
        assert all(40.30 <= s.lat <= 40.50 and 49.70 <= s.lon <= 50.05 for s in stops)
        assert 2_000 < poly.length < 12_000


def test_each_direction_has_two_or_three_simulated_buses_and_target_interval(db, stops_loaded, settings):
    clock.freeze(T0)
    demo.apply_scenario(db, "normal", clock.now(), settings)
    for d in db.execute(select(Direction)).scalars():
        assert 2 <= len(d.buses) <= 3 and all(b.is_simulated for b in d.buses)
        assert d.target_interval_seconds >= 120
