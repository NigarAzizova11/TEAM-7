"""AYNA saytının (map.ayna.gov.az) öz API-sindən BÜTÜN marşrutların xəttini və dayanacaq ardıcıllığını yüklə.

Yalnız Python standart kitabxanası. Bir dəfə işlədilir, nəticə `data/ayna_routes.json` faylına yazılır;
backend işləyərkən AYNA API-sinə sorğu göndərilmir.

  python tools/fetch_ayna_routes.py                      # bütün marşrutlar
  python tools/fetch_ayna_routes.py --numbers 62,5,88    # yalnız seçilmişlər
  python tools/fetch_ayna_routes.py --out data/ayna_routes.json --delay 0.3

Endpointlər map.ayna.gov.az-ın JS-indən götürülüb: /api/bus/getBusList və /api/bus/getBusById?id=...
(sahələr: routes[].flowCoordinates[{lat,lng}], routes[].directionTypeId, stops[].stopCode/directionTypeId).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import ssl
import urllib.error
import urllib.request
from datetime import date

BASE = "https://map-api.ayna.gov.az"
EPS_DEG = 0.00007  # ~8 m: Douglas-Peucker sadələşdirmə həddi


def make_context(cafile: str | None) -> ssl.SSLContext:
    """TLS yoxlaması HƏMİŞƏ açıqdır. Windows-da sertifikat tapılmırsa: `pip install certifi` və ya --cafile verin."""
    if cafile:
        return ssl.create_default_context(cafile=cafile)
    try:
        import certifi  # type: ignore

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


CTX: ssl.SSLContext | None = None


def get_json(url: str, retries: int = 3):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "BakuFlow-hackathon-prototype/0.1"})
            with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
                return json.loads(r.read().decode("utf-8"))
        except ssl.SSLError as e:
            raise RuntimeError(f"TLS sertifikatı yoxlanmadı ({e}). Həll: `pip install certifi` və ya brauzer variantı: tools/fetch_ayna_routes_browser.js") from e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            if isinstance(getattr(e, "reason", None), ssl.SSLError):
                raise RuntimeError(
                    f"TLS sertifikatı yoxlanmadı ({e.reason}). Həll: `pip install certifi`, və ya --cafile, "
                    "və ya brauzer variantı: tools/fetch_ayna_routes_browser.js"
                ) from e
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


def simplify(pts: list[list[float]], eps: float = EPS_DEG) -> list[list[float]]:
    """Douglas-Peucker (iterativ)."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (ax, ay), (bx, by) = pts[a], pts[b]
        dx, dy = bx - ax, by - ay
        norm = (dx * dx + dy * dy) ** 0.5 or 1e-12
        md, mi = 0.0, -1
        for i in range(a + 1, b):
            d = abs(dy * (pts[i][0] - ax) - dx * (pts[i][1] - ay)) / norm
            if d > md:
                md, mi = d, i
        if md > eps and mi > 0:
            keep[mi] = True
            stack += [(a, mi), (mi, b)]
    return [p for p, k in zip(pts, keep) if k]


META: dict[str, dict] = {}


def transform(d: dict) -> dict | None:
    """getBusById cavabını sadə formata çevir. İstiqamət başına ilk 'routes' qeydi götürülür (variantlar atılır)."""
    by_dir: dict[int, dict] = {}
    for r in d.get("routes") or []:
        coords = [[round(c["lat"], 5), round(c["lng"], 5)] for c in (r.get("flowCoordinates") or [])]
        if len(coords) < 2:
            continue
        dt = int(r.get("directionTypeId") or 0)
        if dt not in by_dir:
            by_dir[dt] = {"ext_id": r.get("id"), "dir": dt, "name": r.get("destination") or "", "coords": simplify(coords), "stops": []}
    for s in d.get("stops") or []:
        st = s.get("stop") or {}
        if s.get("stopCode") and st and str(s["stopCode"]) not in META:
            try:
                META[str(s["stopCode"])] = {"n": s.get("stopName") or st.get("name"), "a": float(st["latitude"]), "o": float(st["longitude"])}
            except (KeyError, TypeError, ValueError):
                pass
        dt = int(s.get("directionTypeId") or 0)
        if dt in by_dir and s.get("stopCode"):
            by_dir[dt]["stops"].append(str(s["stopCode"]))  # massiv sırası = marşrut sırası
    dirs = [by_dir[k] for k in sorted(by_dir) if len(by_dir[k]["stops"]) >= 2]
    if not dirs:
        return None
    return {
        "ext_id": d.get("id"),
        "number": str(d.get("number")),
        "carrier": d.get("carrier"),
        "first": (d.get("firstPoint") or "").strip(),
        "last": (d.get("lastPoint") or "").strip(),
        "length_km": d.get("routLength"),
        "duration_min": d.get("durationMinuts"),
        "directions": dirs,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/ayna_routes.json")
    ap.add_argument("--numbers", default="", help="vergüllə ayrılmış marşrut nömrələri (boş = hamısı)")
    ap.add_argument("--delay", type=float, default=0.25, help="sorğular arası saniyə")
    ap.add_argument("--cafile", default=None, help="etibarlı CA sertifikat faylı (şəbəkə sertifikat müdaxiləsi varsa)")
    args = ap.parse_args()
    global CTX
    CTX = make_context(args.cafile)
    want = {x.strip() for x in args.numbers.split(",") if x.strip()}

    lst = get_json(f"{BASE}/api/bus/getBusList")
    items = [b for b in lst if not want or str(b.get("number")) in want]
    print(f"{len(items)} marşrut yüklənəcək...")
    routes, failed, skipped = [], [], []
    for i, b in enumerate(items, 1):
        try:
            d = get_json(f"{BASE}/api/bus/getBusById?id={b['id']}")
            t = transform(d)
            (routes.append(t) if t else skipped.append(b["number"]))
        except Exception as e:  # noqa: BLE001
            failed.append((b.get("number"), str(e)[:80]))
        if i % 10 == 0:
            print(f"  {i}/{len(items)}")
        time.sleep(args.delay)
    doc = {
        "source": "map-api.ayna.gov.az /api/bus/getBusById (map.ayna.gov.az saytının öz sorğusu)",
        "fetched_at": date.today().isoformat(),
        "note": "Xətt koordinatları Douglas-Peucker ilə ~8 m dəqiqliyə sadələşdirilib; dayanacaq kodları AYNA-nın 'stopCode' sahəsidir.",
        "stops": META,
        "routes": routes,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Yazıldı: {args.out} ({len(routes)} marşrut). Keçildi (xətt/dayanacaq yoxdur): {skipped}. Xəta: {failed}")
    return 0 if routes else 1


if __name__ == "__main__":
    sys.exit(main())
