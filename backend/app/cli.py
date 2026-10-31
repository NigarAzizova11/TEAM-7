"""Əmr sətri: python -m app.cli <əmr>

  import-stops [--file data/dayanacaqlar.csv]   CSV-ni PostgreSQL-ə yüklə (təkrar işlətmək təhlükəsizdir)
  import-routes [--file data/ayna_routes.json]  AYNA real marşrut strukturunu (dayanacaq sırası + xətt) yüklə
  seed-demo [--scenario normal] [--rebuild]     Demo marşrut/avtobus strukturunu qur və ssenarini tətbiq et
  reset-demo                                    Dinamik demo məlumatı təmizlə, 'normal' ssenarini qur
  status                                        Qısa vəziyyət
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import func, select

from . import clock
from .config import get_settings
from .db import session_scope
from .models import Alert, Bus, CrowdReport, GpsPosition, Route, Stop
from .services import ayna_import, csv_import, demo


def cmd_import(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.exists():
        print(f"XƏTA: fayl tapılmadı: {path}", file=sys.stderr)
        return 2
    try:
        with session_scope() as session:
            report = csv_import.import_stops(session, path)
    except csv_import.CsvFormatError as e:
        print(f"XƏTA: {e}", file=sys.stderr)
        return 2
    print(report.summary())
    return 0


def cmd_import_routes(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.exists():
        print(f"XƏTA: fayl tapılmadı: {path}", file=sys.stderr)
        return 2
    try:
        with session_scope() as session:
            sim = None if args.simulate.strip() == "all" else {x.strip() for x in args.simulate.split(",") if x.strip()}
            report = ayna_import.import_routes(session, path, bus_headway_minutes=args.headway, simulate=sim)
    except ayna_import.AynaFormatError as e:
        print(f"XƏTA: {e}", file=sys.stderr)
        return 2
    print(report.summary())
    print("Növbəti: python -m app.cli seed-demo --scenario normal   (avtobus hərəkəti SİMULYASİYA olunur)")
    return 0


def cmd_seed(args: argparse.Namespace) -> int:
    s = get_settings()
    try:
        with session_scope() as session:
            res = demo.apply_scenario(session, args.scenario, clock.now(), s, rebuild_structure=args.rebuild)
    except demo.DemoError as e:
        print(f"XƏTA: {e}", file=sys.stderr)
        return 2
    print(f"Demo ssenari tətbiq olundu: {res['scenario']} (yaranan xəbərdarlıq: {res['alerts_created']})")
    return 0


def cmd_status(_: argparse.Namespace) -> int:
    with session_scope() as session:
        def count(model) -> int:
            return session.execute(select(func.count()).select_from(model)).scalar() or 0

        st = demo.current_scenario(session)
        print(f"dayanacaqlar (REAL): {count(Stop)}")
        real = session.execute(select(func.count()).select_from(Route).where(Route.source == "ayna")).scalar() or 0
        print(f"marşrutlar: {count(Route)} (o cümlədən real AYNA strukturu: {real}), simulyasiya avtobusları: {count(Bus)}")
        print(f"GPS qeydləri: {count(GpsPosition)}, bildirişlər: {count(CrowdReport)}, xəbərdarlıqlar: {count(Alert)}")
        print(f"aktiv ssenari: {st.scenario if st else '-'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("import-stops")
    a.add_argument("--file", default="data/dayanacaqlar.csv")
    a.set_defaults(fn=cmd_import)
    r = sub.add_parser("import-routes")
    r.add_argument("--file", default="data/ayna_routes.json")
    r.add_argument("--headway", type=float, default=8.0, help="simulyasiya olunan avtobuslar arası interval (dəq), varsayım")
    r.add_argument(
        "--simulate", default="62,5,14,88,2,3,7A,6,49,46,21,11",
        help="avtobus simulyasiyası qurulacaq marşrut nömrələri (vergüllə) və ya 'all'. Qalan marşrutlar yalnız real xətt/dayanacaqla saxlanır",
    )
    r.set_defaults(fn=cmd_import_routes)
    b = sub.add_parser("seed-demo")
    b.add_argument("--scenario", default="normal", choices=sorted(demo.SCENARIOS))
    b.add_argument("--rebuild", action="store_true", help="demo marşrut strukturunu sıfırdan seç/qur")
    b.set_defaults(fn=cmd_seed)
    c = sub.add_parser("reset-demo")
    c.set_defaults(fn=lambda ns: cmd_seed(argparse.Namespace(scenario="normal", rebuild=False)))
    d = sub.add_parser("status")
    d.set_defaults(fn=cmd_status)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
