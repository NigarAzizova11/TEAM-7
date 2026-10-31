"""dayanacaqlar.csv importeri.

Faylın başlığı: ID,AD,ID,LONGITUDE,LATITUDE,Tip  (təkrarlanan "ID" başlığı var!)
Sütunlar YALNIZ MÖVQEYƏ görə oxunur:
  0 -> row_id (sıra nömrəsi)     1 -> ad
  2 -> stop_id (MƏTN, sıfırlar qorunur)
  3 -> LONGITUDE (uzunluq)       4 -> LATITUDE (enlik)       5 -> Tip (boş ola bilər)

Koordinatlar artıq onluq dərəcədir: heç bir bölmə aparılmır. Etibarsız sətirlər
sakitcə düzəldilmir, səbəbi ilə birlikdə hesabatda göstərilir.
Eyni stop_id təkrar import olunanda yenilənir (çoxalmır). Adlar birləşdirilmir.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import literal_column
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from .. import clock
from ..models import Stop
from ..textutil import fold_az

BATCH = 1000


class CsvFormatError(ValueError):
    pass


@dataclass
class ImportReport:
    rows_read: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    duplicate_stop_ids_in_file: int = 0
    outside_expected_bbox: int = 0  # xəbərdarlıq: Azərbaycan bbox-dan kənar
    skip_reasons: list[str] = field(default_factory=list)
    encoding: str = "utf-8-sig"
    delimiter: str = ","

    def summary(self) -> str:
        lines = [
            f"Oxunan sətir: {self.rows_read}",
            f"  yeni əlavə: {self.inserted}",
            f"  yenilənən: {self.updated}",
            f"  dəyişməyən: {self.unchanged}",
            f"  keçilən (etibarsız): {self.skipped}",
            f"  faylda təkrarlanan stop_id: {self.duplicate_stop_ids_in_file}",
            f"  Azərbaycan bbox-dan kənar koordinat (xəbərdarlıq): {self.outside_expected_bbox}",
            f"Kodlaşdırma: {self.encoding}, ayırıcı: {self.delimiter!r}",
        ]
        if self.skip_reasons:
            lines.append("Keçilən sətirlərin ilk səbəbləri:")
            lines += [f"  - {r}" for r in self.skip_reasons[:10]]
        return "\n".join(lines)


def _decode(raw: bytes) -> tuple[str, str]:
    for enc in ("utf-8-sig", "cp1254"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    raise CsvFormatError("Fayl nə UTF-8, nə də cp1254 kimi oxuna bilmədi")


def _parse_float(raw: str) -> float:
    s = raw.strip()
    if not s:
        raise ValueError("boşdur")
    if "," in s and "." not in s:  # onluq vergül
        s = s.replace(",", ".")
    return float(s)


def _norm_header(h: str) -> str:
    return h.strip().lstrip("﻿").upper()


# Azərbaycan üçün kobud bbox: yalnız XƏBƏRDARLIQ üçün (məs. mikro-dərəcə səhvi aşkarlamaq)
_AZ_LAT = (38.0, 42.0)
_AZ_LON = (44.0, 51.0)


def parse_rows(raw: bytes) -> tuple[list[dict], ImportReport]:
    text_data, enc = _decode(raw)
    report = ImportReport(encoding=enc)
    first_line = text_data.splitlines()[0] if text_data.strip() else ""
    delim = ";" if first_line.count(";") > first_line.count(",") else ","
    report.delimiter = delim

    reader = csv.reader(io.StringIO(text_data), delimiter=delim)
    try:
        header = next(reader)
    except StopIteration as exc:
        raise CsvFormatError("Fayl boşdur") from exc

    h = [_norm_header(x) for x in header]
    expected = ["ID", "AD", "ID", "LONGITUDE", "LATITUDE"]
    if len(h) < 5 or h[:5] != expected:
        raise CsvFormatError(
            f"Gözlənilən başlıq: ID,AD,ID,LONGITUDE,LATITUDE,Tip; tapılan: {header!r}"
        )

    rows: dict[str, dict] = {}
    for line_no, cells in enumerate(reader, start=2):
        if not any(c.strip() for c in cells):
            continue  # tam boş sətir
        report.rows_read += 1
        if len(cells) < 5:
            report.skipped += 1
            report.skip_reasons.append(f"sətir {line_no}: kifayət qədər sütun yoxdur")
            continue

        stop_id = cells[2].strip()
        name = cells[1].strip()
        if not stop_id:
            report.skipped += 1
            report.skip_reasons.append(f"sətir {line_no}: stop_id boşdur")
            continue
        if not name:
            report.skipped += 1
            report.skip_reasons.append(f"sətir {line_no} (stop_id={stop_id}): ad boşdur")
            continue
        try:
            lon = _parse_float(cells[3])
            lat = _parse_float(cells[4])
        except ValueError as exc:
            report.skipped += 1
            report.skip_reasons.append(f"sətir {line_no} (stop_id={stop_id}): koordinat oxunmadı ({exc})")
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            report.skipped += 1
            report.skip_reasons.append(
                f"sətir {line_no} (stop_id={stop_id}): koordinat aralıqdan kənardır lat={lat} lon={lon}"
            )
            continue

        row_id: int | None
        try:
            row_id = int(cells[0].strip())
        except ValueError:
            row_id = None

        stop_type = cells[5].strip() if len(cells) > 5 and cells[5].strip() else None

        if stop_id in rows:
            report.duplicate_stop_ids_in_file += 1
            report.skip_reasons.append(f"sətir {line_no}: stop_id={stop_id} faylda təkrarlanır (ilk qeyd saxlanıldı)")
            continue
        if not (_AZ_LAT[0] <= lat <= _AZ_LAT[1] and _AZ_LON[0] <= lon <= _AZ_LON[1]):
            report.outside_expected_bbox += 1

        rows[stop_id] = {
            "stop_id": stop_id,
            "source_row_id": row_id,
            "name": name,
            "name_search": fold_az(name),
            "lat": lat,
            "lon": lon,
            "stop_type": stop_type,
        }
    return list(rows.values()), report


def import_stops(session: Session, path: Path) -> ImportReport:
    raw = Path(path).read_bytes()
    rows, report = parse_rows(raw)
    now = clock.now()

    for i in range(0, len(rows), BATCH):
        chunk = rows[i : i + BATCH]
        stmt = pg_insert(Stop).values([{**r, "created_at": now, "updated_at": now} for r in chunk])
        changed = (
            Stop.source_row_id.is_distinct_from(stmt.excluded.source_row_id)
            | (Stop.name != stmt.excluded.name)
            | (Stop.lat != stmt.excluded.lat)
            | (Stop.lon != stmt.excluded.lon)
            | Stop.stop_type.is_distinct_from(stmt.excluded.stop_type)
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[Stop.stop_id],
            set_={
                "source_row_id": stmt.excluded.source_row_id,
                "name": stmt.excluded.name,
                "name_search": stmt.excluded.name_search,
                "lat": stmt.excluded.lat,
                "lon": stmt.excluded.lon,
                "stop_type": stmt.excluded.stop_type,
                "updated_at": now,
            },
            where=changed,
        ).returning(literal_column("(xmax = 0)").label("inserted"))
        result = session.execute(stmt).all()
        inserted = sum(1 for r in result if r.inserted)
        report.inserted += inserted
        report.updated += len(result) - inserted
    report.unchanged = len(rows) - report.inserted - report.updated
    session.commit()
    return report
