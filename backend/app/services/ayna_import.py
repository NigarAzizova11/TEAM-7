"""AYNA marşrut strukturunun idxalı (real dayanacaq ardıcıllığı + real xətt geometriyası).

Mənbə: map.ayna.gov.az saytının öz API cavabı (`/api/bus/getBusById`) əsasında hazırlanmış
`data/ayna_routes.json`. Bu skript API-ni ÇAĞIRMIR: yalnız lokal faylı oxuyur, nəticəni PostgreSQL-də saxlayır.

REAL olanlar: marşrutun nömrəsi, istiqamətləri, dayanacaq ardıcıllığı, xətt geometriyası, ümumi gediş müddəti.
SİMULYASİYA olanlar: avtobuslar (say, mövqe, sürət), GPS və sıxlıq bildirişləri. Hədəf interval də varsayımdır
(AYNA bunu vermir): `bus_headway_minutes` ilə hesablanır.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..geo import Polyline
from ..models import Bus, Direction, DirectionStop, Route, Stop
from ..textutil import fold_az

DIR_LETTERS = "AB"
DEFAULT_DURATION_MIN = 45.0


class AynaFormatError(Exception):
    pass


def norm_code(code: str) -> str:
    """AYNA kodu '1001407' ↔ CSV stop_id '001001407': baş sıfırlar fərqlidir, rəqəmlər eynidir."""
    return str(code).strip().lstrip("0")


@dataclass
class ImportReport:
    routes: int = 0
    directions: int = 0
    stop_links: int = 0
    buses: int = 0
    missing_codes: list[tuple[str, int, str]] = field(default_factory=list)  # (marşrut, istiqamət, kod)
    skipped_directions: list[str] = field(default_factory=list)
    removed_demo_routes: int = 0
    added_stops: int = 0
    fixed_points: int = 0
    dropped_points: int = 0
    simulated_routes: int = 0
    replaced_routes: int = 0

    def summary(self) -> str:
        lines = [
            f"Marşrut: {self.routes} (avtobus simulyasiyası olan: {self.simulated_routes}), istiqamət: {self.directions}, "
            f"dayanacaq bağlantısı: {self.stop_links}, simulyasiya avtobusu: {self.buses}",
            f"Silinən demo (real olmayan) marşrut: {self.removed_demo_routes}, əvəzlənən real marşrut: {self.replaced_routes}",
            f"AYNA-dan əlavə edilən yeni dayanacaq: {self.added_stops}",
            f"Xətlərdə düzəldilən (lat/lon yeri dəyişik) nöqtə: {self.fixed_points}, atılan səhv nöqtə: {self.dropped_points}",
            f"Bazada və AYNA faylında tapılmayan dayanacaq kodu: {len(self.missing_codes)}",
        ]
        for r, d, c in self.missing_codes[:10]:
            lines.append(f"  - marşrut {r}, istiqamət {d}: kod {c}")
        for s in self.skipped_directions[:15]:
            lines.append(f"  ! keçildi: {s}")
        return "\n".join(lines)


def _ok_pt(p: Any) -> bool:
    return isinstance(p, list) and len(p) == 2 and all(isinstance(x, (int, float)) for x in p) and 39.0 < p[0] < 42.0 and 48.0 < p[1] < 51.0


def clean_coords(coords: list) -> tuple[list[list[float]], int, int]:
    """Etibarlı nöqtələri saxla; lat/lon yeri dəyişənləri düzəlt; qalanları at. (nəticə, düzəldilən, atılan)"""
    out, swapped, dropped = [], 0, 0
    for p in coords:
        if _ok_pt(p):
            out.append([float(p[0]), float(p[1])])
        elif isinstance(p, list) and len(p) == 2 and _ok_pt([p[1], p[0]]):
            out.append([float(p[1]), float(p[0])])
            swapped += 1
        else:
            dropped += 1
    return out, swapped, dropped


def _route_problem(r: Any) -> str | None:
    if not isinstance(r, dict) or not r.get("number") or not isinstance(r.get("directions"), list) or not r["directions"]:
        return f"natamam qeyd: {str(r)[:60]}"
    for d in r["directions"]:
        coords = d.get("coords")
        if not isinstance(coords, list) or len(coords) < 2:
            return "xətt geometriyası yoxdur/çox qısadır"
        cleaned, _, _ = clean_coords(coords)
        if len(cleaned) < 2:
            return "etibarlı xətt koordinatı < 2 (Azərbaycan hüdudundan kənar/səhv)"
        if not isinstance(d.get("stops"), list):
            return "'stops' siyahısı yoxdur"
    return None


def _validate(doc: Any) -> tuple[list[dict], list[str]]:
    """(etibarlı marşrutlar, keçilənlər). Fayl strukturu pozuqdursa AynaFormatError; tək marşrut pozuqdursa keçilir."""
    if not isinstance(doc, dict) or not isinstance(doc.get("routes"), list) or not doc["routes"]:
        raise AynaFormatError("Faylda 'routes' siyahısı yoxdur")
    ok, bad = [], []
    for r in doc["routes"]:
        prob = _route_problem(r)
        if prob is None:
            ok.append(r)
        else:
            bad.append(f"{r.get('number') if isinstance(r, dict) else '?'}: {prob}")
    if not ok:
        raise AynaFormatError("Etibarlı marşrut yoxdur: " + "; ".join(bad[:3]))
    return ok, bad


def import_routes(
    session: Session, path: Path, bus_headway_minutes: float = 10.0, simulate: set[str] | None = None
) -> ImportReport:
    """simulate=None: hamısı üçün avtobus simulyasiyası; çoxluq: yalnız bu nömrəli marşrutlara avtobus qurulur,
    qalanlar real xətt/dayanacaqla saxlanır (avtobussuz, is_demo=False)."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise AynaFormatError(f"JSON oxunmadı: {e}") from e
    routes, bad_routes = _validate(doc)

    stops_by_norm: dict[str, Stop] = {}
    dup: set[str] = set()
    for st in session.execute(select(Stop)).scalars():
        k = norm_code(st.stop_id)
        if k in stops_by_norm:
            dup.add(k)
        stops_by_norm[k] = st
    if not stops_by_norm and not (isinstance(doc.get("stops"), dict) and doc["stops"]):
        raise AynaFormatError("'stops' cədvəli boşdur və faylda 'stops' lüğəti yoxdur. Əvvəlcə: python -m app.cli import-stops")
    for k in dup:  # birmənalı olmayan kodlar istifadə edilmir
        stops_by_norm.pop(k, None)

    rep = ImportReport()
    # CSV-də olmayan dayanacaqlar: faylın 'stops' lüğətindən (AYNA-nın öz məlumatı: ad + koordinat) əlavə et
    meta = doc.get("stops") if isinstance(doc.get("stops"), dict) else {}
    used_codes = {norm_code(c) for r in routes for d in r["directions"] for c in d["stops"]}
    for code, m in meta.items():
        k = norm_code(code)
        if k in stops_by_norm or k not in used_codes or not isinstance(m, dict):
            continue
        try:
            lat, lon, name = float(m["a"]), float(m["o"]), str(m["n"]).strip()
        except (KeyError, TypeError, ValueError):
            continue
        if not (39.0 < lat < 42.0 and 48.0 < lon < 51.0) or not name:
            continue
        st = Stop(stop_id=str(code).strip().zfill(9), name=name[:300], name_search=fold_az(name)[:300], lat=lat, lon=lon, stop_type="AYNA")
        session.add(st)
        session.flush()
        stops_by_norm[k] = st
        rep.added_stops += 1
    rep.skipped_directions.extend(f"marşrut {b}" for b in bad_routes)
    # real olmayan demo marşrutları sil (real dayanacaqlara toxunulmur)
    res = session.execute(delete(Route).where(Route.source == "demo"))
    rep.removed_demo_routes = res.rowcount or 0
    for r in routes:
        res = session.execute(delete(Route).where(Route.code == str(r["number"])))
        rep.replaced_routes += res.rowcount or 0
    session.flush()

    for r in routes:
        number = str(r["number"])
        duration = float(r.get("duration_min") or DEFAULT_DURATION_MIN)
        first = (r.get("first") or "").strip()
        last = (r.get("last") or "").strip()
        route = Route(
            code=number,
            name=(f"{number}: {first} – {last}" if first and last else number)[:100],
            is_demo=simulate is None or number in simulate,  # True = bu marşrutda avtobus/GPS/bildiriş SİMULYASİYA olunur
            source="ayna",
            ext_id=r.get("ext_id"),
        )
        session.add(route)
        session.flush()
        built = 0
        for d in sorted(r["directions"], key=lambda x: x.get("dir", 0)):
            ordinal = built
            if ordinal >= len(DIR_LETTERS):
                rep.skipped_directions.append(f"{number}: 2-dən çox istiqamət dəstəklənmir")
                continue
            resolved: list[Stop] = []
            for code in d["stops"]:
                st = stops_by_norm.get(norm_code(code))
                if st is None:
                    rep.missing_codes.append((number, d.get("dir", 0), str(code)))
                    continue
                if resolved and resolved[-1].id == st.id:
                    continue  # ardıcıl təkrar
                resolved.append(st)
            if len(resolved) < 2:
                rep.skipped_directions.append(f"{number} istiqamət {d.get('dir')}: bazada tapılan dayanacaq < 2")
                continue
            coords, sw, dr = clean_coords(d["coords"])
            rep.fixed_points += sw
            rep.dropped_points += dr
            poly = Polyline.from_points([(a, b) for a, b in coords])
            n_buses = max(2, round(duration / bus_headway_minutes))
            target = max(120, int(round(duration * 60 / n_buses / 10.0)) * 10)
            direction = Direction(
                route_id=route.id,
                ordinal=ordinal,
                name=(d.get("name") or f"İstiqamət {ordinal + 1}")[:100],
                target_interval_seconds=target,
                nominal_speed_mps=poly.length / (duration * 60.0),
                sim_params={},
                geometry=coords,
                ext_id=d.get("ext_id"),
            )
            session.add(direction)
            session.flush()
            for seq, st in enumerate(resolved):
                session.add(DirectionStop(direction_id=direction.id, seq=seq, stop_pk=st.id))
            for i in range(1, (n_buses if route.is_demo else 0) + 1):
                session.add(
                    Bus(code=f"{number}-{DIR_LETTERS[ordinal]}{i}", direction_id=direction.id, is_active=True, is_simulated=True)
                )
            built += 1
            rep.directions += 1
            rep.stop_links += len(resolved)
            rep.buses += n_buses if route.is_demo else 0
        if built:
            rep.routes += 1
            rep.simulated_routes += 1 if route.is_demo else 0
        else:
            session.delete(route)
    session.flush()
    return rep
