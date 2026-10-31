"""AYNA real marşrut strukturunun idxalı: kod uyğunluğu, monoton dayanacaq mövqeyi, real geometriya, ssenarilər."""
import json

import pytest
from sqlalchemy import select

from app import clock
from app.geo import Polyline, haversine_m
from app.models import Alert, Bus, Direction, DirectionStop, Route, Stop
from app.services import ayna_import, demo
from app.services.transit import stop_infos
from tests.conftest import T0


def make_doc(path, n_stops=8, bad_code=None):
    """Kiçik SİNTETİK AYNA formatlı fayl: 'U' formalı, özünü kəsən (ora-bura) xətt. Real data deyil."""
    base_lat, base_lon = 40.40, 49.80
    outward = [[base_lat, base_lon + i * 0.003] for i in range(0, 13)]       # şərqə
    back = [[base_lat, base_lon + (12 - i) * 0.003] for i in range(0, 13)]  # eyni yolla geri (üst-üstə)
    coords = outward + back
    stops = [f"{1000000 + i}" for i in range(n_stops)]
    if bad_code:
        stops[3] = bad_code
    doc = {
        "routes": [
            {
                "ext_id": 1, "number": "T1", "carrier": "x", "first": "A", "last": "B", "length_km": 6.0, "duration_min": 30,
                "directions": [{"ext_id": 11, "dir": 1, "name": "A - B", "coords": coords, "stops": stops}],
            }
        ]
    }
    path.write_text(json.dumps(doc), encoding="utf-8")
    return doc, coords


def add_stops(db, n=8, base_lat=40.40, base_lon=49.80, with_codes=True):
    for i in range(n):
        db.add(
            Stop(
                stop_id=f"00{1000000 + i}", name=f"Dayanacaq {i}", name_search=f"dayanacaq {i}",
                lat=base_lat + 0.0001, lon=base_lon + i * 0.0045,
            )
        )
    db.commit()


def test_codes_match_with_leading_zero_padding(db, tmp_path):
    add_stops(db)
    make_doc(tmp_path / "r.json")
    rep = ayna_import.import_routes(db, tmp_path / "r.json")
    db.commit()
    assert rep.routes == 1 and rep.directions == 1 and rep.stop_links == 8 and not rep.missing_codes


def test_missing_stop_code_is_reported_not_invented(db, tmp_path):
    add_stops(db)
    make_doc(tmp_path / "r.json", bad_code="9999999")
    rep = ayna_import.import_routes(db, tmp_path / "r.json")
    db.commit()
    assert rep.missing_codes == [("T1", 1, "9999999")] and rep.stop_links == 7
    d = db.execute(select(Direction)).scalar_one()
    assert len(d.stops) == 7  # uydurma dayanacaq əlavə edilmir


def test_route_uses_real_geometry_and_is_labelled_ayna(db, tmp_path):
    add_stops(db)
    _, coords = make_doc(tmp_path / "r.json")
    ayna_import.import_routes(db, tmp_path / "r.json")
    db.commit()
    r = db.execute(select(Route)).scalar_one()
    assert r.source == "ayna" and r.is_demo  # dinamik məlumat simulyasiyadır
    d = r.directions[0]
    assert d.geometry == coords
    assert all(b.is_simulated for b in d.buses) and len(d.buses) >= 2


def test_stop_positions_are_monotone_on_self_overlapping_line(db, tmp_path):
    """Xətt gedib eyni yolla qayıdır: ən yaxın nöqtə iki yerdədir, amma ardıcıllıq irəliyə getməlidir."""
    add_stops(db)
    make_doc(tmp_path / "r.json")
    ayna_import.import_routes(db, tmp_path / "r.json")
    db.commit()
    d = db.execute(select(Direction)).scalar_one()
    infos, poly = stop_infos(d)
    ds = [s.d for s in infos]
    assert ds == sorted(ds)
    assert poly.length > 5500  # gediş + qayıdış (~6.1 km)
    # bütün dayanacaqlar xəttin ilk (gediş) yarısına düşür, çünki ardıcıllıq irəliyə doğrudur
    assert all(x <= poly.length / 2 + 400 for x in ds[:6])


def test_hinted_projection_follows_the_bus_on_overlap(db, tmp_path):
    _, coords = make_doc(tmp_path / "r.json")
    poly = Polyline.from_points([tuple(c) for c in coords])
    hint = None
    for d in range(0, int(poly.length), 40):
        lat, lon, _ = poly.point_at(d)
        prog, off = poly.project_hint(lat, lon, hint)
        assert abs(prog - d) < 60, (d, prog)  # qayıdış hissəsində də düzgün tərəfi seçir
        hint = prog


def test_import_replaces_demo_routes_but_keeps_real_stops(db, stops_loaded, settings):
    clock.freeze(T0)
    demo.apply_scenario(db, "normal", clock.now(), settings)
    assert db.execute(select(Route).where(Route.source == "demo")).scalars().first() is not None
    n_stops = db.execute(select(Stop)).scalars().all()
    # AYNA faylı sintetik stops cədvəlindəki mövcud 9 rəqəmli id-lərə uyğunlaşdırılır
    s0 = [s for s in n_stops][:6]
    coords = [[s.lat, s.lon] for s in s0]
    import tempfile, pathlib
    p = pathlib.Path(tempfile.mkdtemp()) / "r.json"
    p.write_text(json.dumps({"routes": [{"number": "Q1", "duration_min": 20, "directions": [
        {"dir": 1, "name": "x", "coords": coords, "stops": [s.stop_id for s in s0]}]}]}), encoding="utf-8")
    before = len(n_stops)
    rep = ayna_import.import_routes(db, p)
    db.commit()
    assert rep.removed_demo_routes == 2
    assert db.execute(select(Route).where(Route.source == "demo")).scalars().first() is None
    assert len(db.execute(select(Stop)).scalars().all()) == before  # real dayanacaqlara toxunulmayıb


def test_invalid_files_are_rejected(db, tmp_path):
    add_stops(db)
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(ayna_import.AynaFormatError):
        ayna_import.import_routes(db, p)
    p.write_text(json.dumps({"routes": [{"number": "X", "directions": [{"dir": 1, "coords": [[0, 0], [1, 1]], "stops": []}]}]}))
    with pytest.raises(ayna_import.AynaFormatError):  # Azərbaycandan kənar koordinat
        ayna_import.import_routes(db, p)


def real_like_doc(db, tmp_path):
    """Sintetik dayanacaqlar üzərində 'real strukturlu' marşrut: 5 dəq intervalla çoxlu avtobus."""
    add_stops(db, n=14)
    base_lat, base_lon = 40.40, 49.80
    coords = [[base_lat + 0.0001, base_lon + i * 0.0015] for i in range(0, 14 * 3)]
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"routes": [{"number": "T2", "duration_min": 40, "first": "A", "last": "B", "directions": [
        {"dir": 1, "name": "A - B", "coords": coords, "stops": [f"{1000000 + i}" for i in range(14)]}]}]}), encoding="utf-8")
    return p


def test_scenarios_run_on_ayna_route_and_high_crowd_alert_is_created(db, tmp_path, settings):
    p = real_like_doc(db, tmp_path)
    ayna_import.import_routes(db, p, bus_headway_minutes=5)
    db.commit()
    clock.freeze(T0)
    res = demo.apply_scenario(db, "high_crowd", clock.now(), settings)
    kinds = [a.title for a in db.execute(select(Alert).where(Alert.status == "ACTIVE")).scalars()]
    assert kinds == ["Əlavə avtobus ehtiyatı ayrılmalıdır"], kinds
    demo.apply_scenario(db, "normal", clock.now(), settings)
    assert db.execute(select(Alert).where(Alert.status == "ACTIVE")).scalars().first() is None


def test_api_reports_source_and_line_note(db, tmp_path, settings):
    from fastapi.testclient import TestClient
    from app.main import create_app

    p = real_like_doc(db, tmp_path)
    ayna_import.import_routes(db, p, bus_headway_minutes=5)
    db.commit()
    clock.freeze(T0)
    demo.apply_scenario(db, "normal", clock.now(), settings)
    c = TestClient(create_app())
    routes = c.get("/api/routes").json()["routes"]
    assert routes[0]["source"] == "ayna"
    det = c.get(f"/api/directions/{routes[0]['directions'][0]['id']}").json()
    assert "AYNA" in det["polyline_note"] and len(det["polyline"]) == 14 * 3


def test_simulate_subset_leaves_other_routes_structure_only(db, tmp_path, settings):
    from fastapi.testclient import TestClient
    from app.main import create_app

    add_stops(db, n=14)
    base_lat, base_lon = 40.40, 49.80
    coords = [[base_lat + 0.0001, base_lon + i * 0.0015] for i in range(0, 14 * 3)]
    mk = lambda n: {"number": n, "duration_min": 40, "directions": [
        {"dir": 1, "name": f"{n} A-B", "coords": coords, "stops": [f"{1000000 + i}" for i in range(14)]}]}
    bad = {"number": "BAD", "directions": [{"dir": 1, "coords": [[0, 0], [1, 1]], "stops": []}]}
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"routes": [mk("S1"), mk("S2"), bad]}), encoding="utf-8")
    rep = ayna_import.import_routes(db, p, bus_headway_minutes=5, simulate={"S1"})
    db.commit()
    assert rep.routes == 2 and rep.simulated_routes == 1 and any("BAD" in x for x in rep.skipped_directions)
    r1, r2 = (db.execute(select(Route).where(Route.code == c)).scalar_one() for c in ("S1", "S2"))
    assert r1.is_demo and not r2.is_demo
    assert len(r1.directions[0].buses) > 0 and len(r2.directions[0].buses) == 0
    clock.freeze(T0)
    demo.apply_scenario(db, "normal", clock.now(), settings)  # avtobussuz marşrut ssenarini pozmur
    c = TestClient(create_app())
    routes = {r["code"]: r for r in c.get("/api/routes").json()["routes"]}
    assert routes["S1"]["simulated"] is True and routes["S2"]["simulated"] is False
    d2 = routes["S2"]["directions"][0]["id"]
    det = c.get(f"/api/directions/{d2}").json()
    assert len(det["stops"]) == 14 and "AYNA" in det["polyline_note"]
    arr = c.get(f"/api/arrivals?direction_id={d2}&stop_id={det['stops'][5]['stop_id']}").json()
    assert arr["buses"] == []  # simulyasiya olunmayan marşrutda uydurma avtobus yoxdur
    ov = c.get("/api/operator/overview").json()
    assert all(d["route"]["code"] != "S2" for d in ov["directions"])  # operator yalnız simulyasiya olunanları analiz edir


def test_clean_coords_fixes_swapped_and_drops_bad():
    from app.services.ayna_import import clean_coords

    out, sw, dr = clean_coords([[40.4, 49.8], [49.9, 40.5], [0, 0], [40.41, 49.81], "x"])
    assert out == [[40.4, 49.8], [40.5, 49.9], [40.41, 49.81]]
    assert (sw, dr) == (1, 2)


def test_missing_stop_added_from_ayna_stops_dict(db, tmp_path):
    add_stops(db)
    doc, _ = make_doc(tmp_path / "r.json", bad_code="9999999")
    doc["stops"] = {"9999999": {"n": "AYNA dayanacağı", "a": 40.4001, "o": 49.8135}}
    (tmp_path / "r.json").write_text(json.dumps(doc), encoding="utf-8")
    rep = ayna_import.import_routes(db, tmp_path / "r.json")
    db.commit()
    assert rep.added_stops == 1 and not rep.missing_codes and rep.stop_links == 8
    st = db.execute(select(Stop).where(Stop.stop_id == "009999999")).scalar_one()
    assert st.stop_type == "AYNA" and st.name == "AYNA dayanacağı"


def test_invalid_ayna_stop_meta_is_ignored(db, tmp_path):
    add_stops(db)
    doc, _ = make_doc(tmp_path / "r.json", bad_code="9999999")
    doc["stops"] = {"9999999": {"n": "X", "a": 0, "o": 0}}
    (tmp_path / "r.json").write_text(json.dumps(doc), encoding="utf-8")
    rep = ayna_import.import_routes(db, tmp_path / "r.json")
    assert rep.added_stops == 0 and len(rep.missing_codes) == 1


def test_import_works_without_csv_stops_when_file_has_stops_dict(db, tmp_path):
    doc, _ = make_doc(tmp_path / "r.json")
    doc["stops"] = {str(1000000 + i): {"n": f"AYNA {i}", "a": 40.4001, "o": 49.80 + i * 0.0045} for i in range(8)}
    (tmp_path / "r.json").write_text(json.dumps(doc), encoding="utf-8")
    rep = ayna_import.import_routes(db, tmp_path / "r.json")
    assert rep.added_stops == 8 and rep.routes == 1 and not rep.missing_codes


def test_database_url_normalized():
    from app.config import Settings

    s = Settings(database_url="postgres://u:p@h:5432/d", session_hash_secret="x")
    assert s.database_url == "postgresql+psycopg://u:p@h:5432/d"
    assert Settings(database_url="postgresql://u:p@h/d", session_hash_secret="x").database_url == "postgresql+psycopg://u:p@h/d"
    assert Settings(database_url="postgresql+psycopg://u:p@h/d", session_hash_secret="x").database_url == "postgresql+psycopg://u:p@h/d"
