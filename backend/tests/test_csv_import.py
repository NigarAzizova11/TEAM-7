"""CSV importu: mövqeyə görə sütunlar, mətn stop_id, koordinat formatı, idempotentlik."""
import pytest
from sqlalchemy import func, select

from app.models import Stop
from app.services.csv_import import CsvFormatError, import_stops, parse_rows
from tests.synth import N_STOPS, synthetic_rows, write_csv


def count(db):
    return db.execute(select(func.count()).select_from(Stop)).scalar()


def test_imports_all_3600_rows(db, csv_path):
    rep = import_stops(db, csv_path)
    assert rep.rows_read == N_STOPS and rep.inserted == N_STOPS and rep.skipped == 0
    assert count(db) == N_STOPS


def test_duplicate_id_headers_read_by_position(db, csv_path):
    import_stops(db, csv_path)
    s = db.execute(select(Stop).where(Stop.stop_id == "00042")).scalar_one()
    assert s.source_row_id == 42  # birinci ID = sıra nömrəsi
    assert s.stop_id == "00042"  # ikinci ID = dayanacaq kodu


def test_stop_id_is_text_with_leading_zeros(db, csv_path):
    import_stops(db, csv_path)
    s = db.execute(select(Stop).where(Stop.source_row_id == 7)).scalar_one()
    assert isinstance(s.stop_id, str) and s.stop_id == "00007"
    assert db.execute(select(Stop).where(Stop.stop_id == "7")).first() is None


def test_coordinates_are_degrees_not_divided_and_lat_lon_not_swapped(db, csv_path):
    import_stops(db, csv_path)
    s = db.execute(select(Stop).where(Stop.stop_id == "00001")).scalar_one()
    assert s.lat == pytest.approx(40.330, abs=1e-9)  # LATITUDE = enlik
    assert s.lon == pytest.approx(49.800, abs=1e-9)  # LONGITUDE = uzunluq
    assert 40 < s.lat < 41 and 49 < s.lon < 50  # 1 milyona bölünmüş olsaydı ~0.00004 olardı


def test_empty_tip_allowed(db, csv_path):
    import_stops(db, csv_path)
    row3 = db.execute(select(Stop).where(Stop.stop_id == "00003")).scalar_one()
    row1 = db.execute(select(Stop).where(Stop.stop_id == "00001")).scalar_one()
    assert row3.stop_type is None and row1.stop_type == "Avtobus"


def test_same_name_different_stops_not_merged(db, csv_path):
    import_stops(db, csv_path)
    same = db.execute(select(Stop).where(Stop.name == "Eyni Ad")).scalars().all()
    assert len(same) == N_STOPS // 50
    assert len({s.stop_id for s in same}) == len(same)


def test_reimport_does_not_duplicate_and_reports_unchanged(db, csv_path):
    import_stops(db, csv_path)
    rep2 = import_stops(db, csv_path)
    assert count(db) == N_STOPS
    assert rep2.inserted == 0 and rep2.updated == 0 and rep2.unchanged == N_STOPS


def test_reimport_updates_changed_stop_instead_of_duplicating(db, tmp_path):
    rows = synthetic_rows()
    p = write_csv(tmp_path / "a.csv", rows)
    import_stops(db, p)
    rows[0][3] = "49.900000"  # LONGITUDE dəyişdi
    rep = import_stops(db, write_csv(tmp_path / "b.csv", rows))
    assert rep.updated == 1 and rep.inserted == 0 and count(db) == N_STOPS
    assert db.execute(select(Stop.lon).where(Stop.stop_id == "00001")).scalar_one() == pytest.approx(49.9)


def test_bad_rows_reported_not_silently_fixed():
    rows = [
        ["1", "Ad", "", "49.8", "40.3", ""],  # stop_id boş
        ["2", "Ad", "00002", "49.8", "140.3", ""],  # lat aralıqdan kənar
        ["3", "Ad", "00003", "abc", "40.3", ""],  # oxunmayan koordinat
        ["4", "Ad", "00004", "49.8", "40.3", ""],  # yaxşı
        ["5", "Ad", "00004", "49.9", "40.4", ""],  # təkrar stop_id
    ]
    import tempfile, pathlib

    with tempfile.TemporaryDirectory() as d:
        p = write_csv(pathlib.Path(d) / "x.csv", rows)
        parsed, rep = parse_rows(p.read_bytes())
    assert [r["stop_id"] for r in parsed] == ["00004"]
    assert rep.skipped == 3 and rep.duplicate_stop_ids_in_file == 1
    assert any("stop_id boşdur" in r for r in rep.skip_reasons)


def test_wrong_header_rejected():
    with pytest.raises(CsvFormatError):
        parse_rows(b"ID,AD,LONGITUDE,LATITUDE\n1,a,49,40\n")


def test_bom_and_semicolon_and_decimal_comma(tmp_path):
    p = tmp_path / "s.csv"
    p.write_bytes("﻿ID;AD;ID;LONGITUDE;LATITUDE;Tip\n1;Ad;00009;49,8;40,3;\n".encode("utf-8"))
    rows, rep = parse_rows(p.read_bytes())
    assert rows[0]["lon"] == pytest.approx(49.8) and rows[0]["lat"] == pytest.approx(40.3)
    assert rows[0]["stop_id"] == "00009" and rep.delimiter == ";"


def test_azerbaijani_search_folding():
    from app.textutil import fold_az

    assert fold_az("Əhmədli") == fold_az("ehmedli")
    assert fold_az("İçərişəhər") == fold_az("icerisehər") == "icerisehər".translate(str.maketrans("ə", "e"))
