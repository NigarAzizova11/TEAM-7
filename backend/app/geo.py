"""Coğrafi köməkçilər. Koordinatlar onluq dərəcədir: (lat=enlik, lon=uzunluq).

Marşrut xətti iki mənbədən ola bilər: (1) real AYNA xətt geometriyası (sadələşdirilmiş) və ya
(2) real olmayan demo marşrutlar üçün dayanacaqlar arasında düz seqmentlərdən ibarət sxematik xətt.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

EARTH_R = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R * math.asin(min(1.0, math.sqrt(a)))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def angle_diff_deg(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return d if d <= 180.0 else 360.0 - d


@dataclass(frozen=True)
class Polyline:
    """(lat, lon) nöqtələrindən ibarət sxematik xətt və yığılmış məsafələr."""

    points: tuple[tuple[float, float], ...]
    cum: tuple[float, ...]  # points[i] nöqtəsinə qədər metrlə məsafə

    @classmethod
    def from_points(cls, pts: list[tuple[float, float]]) -> "Polyline":
        if len(pts) < 2:
            raise ValueError("xətt üçün ən azı 2 nöqtə lazımdır")
        cum = [0.0]
        for (la1, lo1), (la2, lo2) in zip(pts, pts[1:]):
            cum.append(cum[-1] + haversine_m(la1, lo1, la2, lo2))
        return cls(tuple(pts), tuple(cum))

    @property
    def length(self) -> float:
        return self.cum[-1]

    def _segment_index(self, d: float) -> int:
        lo, hi = 0, len(self.cum) - 2
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.cum[mid] <= d:
                lo = mid
            else:
                hi = mid - 1
        return lo

    def point_at(self, d: float) -> tuple[float, float, float]:
        """d metr məsafədəki (lat, lon, heading). d xəttin uzunluğuna görə dövrə vurur."""
        d = d % self.length
        i = self._segment_index(d)
        seg_len = self.cum[i + 1] - self.cum[i]
        t = 0.0 if seg_len == 0 else (d - self.cum[i]) / seg_len
        (la1, lo1), (la2, lo2) = self.points[i], self.points[i + 1]
        return (
            la1 + (la2 - la1) * t,
            lo1 + (lo2 - lo1) * t,
            bearing_deg(la1, lo1, la2, lo2),
        )

    def project(self, lat: float, lon: float) -> tuple[float, float]:
        """GPS nöqtəsini xəttə proyeksiya et: (xətt boyunca məsafə m, xəttdən kənarlaşma m).

        Lokal müstəvi yaxınlaşması istifadə olunur (şəhər miqyasında kifayət qədər dəqiqdir).
        """
        lat0 = math.radians(lat)
        kx = math.cos(lat0) * 111_320.0
        ky = 110_540.0
        best_off = math.inf
        best_prog = 0.0
        px, py = lon * kx, lat * ky
        for i in range(len(self.points) - 1):
            (la1, lo1), (la2, lo2) = self.points[i], self.points[i + 1]
            ax, ay = lo1 * kx, la1 * ky
            bx, by = lo2 * kx, la2 * ky
            dx, dy = bx - ax, by - ay
            seg2 = dx * dx + dy * dy
            t = 0.0 if seg2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg2))
            cx, cy = ax + t * dx, ay + t * dy
            off = math.hypot(px - cx, py - cy)
            if off < best_off:
                best_off = off
                best_prog = self.cum[i] + t * (self.cum[i + 1] - self.cum[i])
        return best_prog, best_off

    # ------------------------------------------------------------------ real (özünü kəsən) xətlər üçün

    def _candidates(self, lat: float, lon: float):
        """Hər seqment üzrə (xətt boyunca məsafə m, kənarlaşma m)."""
        kx = math.cos(math.radians(lat)) * 111_320.0
        ky = 110_540.0
        px, py = lon * kx, lat * ky
        for i in range(len(self.points) - 1):
            (la1, lo1), (la2, lo2) = self.points[i], self.points[i + 1]
            ax, ay = lo1 * kx, la1 * ky
            dx, dy = lo2 * kx - ax, la2 * ky - ay
            seg2 = dx * dx + dy * dy
            t = 0.0 if seg2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg2))
            off = math.hypot(px - (ax + t * dx), py - (ay + t * dy))
            yield i, self.cum[i] + t * (self.cum[i + 1] - self.cum[i]), off

    def _window_segments(self, lo_d: float, hi_d: float) -> range:
        lo = self._segment_index(max(0.0, min(lo_d, self.length)))
        hi = self._segment_index(max(0.0, min(hi_d, self.length)))
        return range(lo, min(hi, len(self.points) - 2) + 1)

    def project_hint(
        self, lat: float, lon: float, hint: float | None, back_m: float = 150.0, fwd_m: float = 1500.0, max_jump_off_m: float = 120.0
    ) -> tuple[float, float]:
        """Əvvəlki proqresə (hint) görə proyeksiya. Xətt özünü kəsəndə/üst-üstə düşəndə avtobusun
        əvvəlki mövqeyinə yaxın hissəni seçir (xəttin sonunda başa qayıdış nəzərə alınır).
        Pəncərədə yaxşı nəticə yoxdursa qlobal proyeksiyaya düşür."""
        if hint is None:
            return self.project(lat, lon)
        L = self.length
        lo, hi = hint - back_m, hint + fwd_m
        ranges = [self._window_segments(lo, hi)]
        if hi > L:  # başa qayıdış
            ranges.append(self._window_segments(0.0, hi - L))
        if lo < 0:
            ranges.append(self._window_segments(L + lo, L))
        kx = math.cos(math.radians(lat)) * 111_320.0
        ky = 110_540.0
        px, py = lon * kx, lat * ky
        cands: list[tuple[float, float, float]] = []  # (kənarlaşma, proqres, işarəli məsafə hint-ə görə)
        for rng in ranges:
            for i in rng:
                (la1, lo1), (la2, lo2) = self.points[i], self.points[i + 1]
                ax, ay = lo1 * kx, la1 * ky
                dx, dy = lo2 * kx - ax, la2 * ky - ay
                seg2 = dx * dx + dy * dy
                t = 0.0 if seg2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg2))
                off = math.hypot(px - (ax + t * dx), py - (ay + t * dy))
                prog = self.cum[i] + t * (self.cum[i + 1] - self.cum[i])
                delta = ((prog - hint + L / 2) % L) - L / 2
                cands.append((off, prog, delta))
        if not cands:
            return self.project(lat, lon)
        best_off = min(c[0] for c in cands)
        if best_off > max_jump_off_m:
            return self.project(lat, lon)
        # üst-üstə düşən (ora-bura) hissələrdə irəli istiqaməti üstün tut
        near = [c for c in cands if c[0] <= best_off + 2.5]
        fwd = [c for c in near if c[2] >= -3.0]
        pick = min(fwd, key=lambda c: c[2]) if fwd else min(near, key=lambda c: abs(c[2]))
        return pick[1], pick[0]

    def project_stops(self, pts: list[tuple[float, float]], tol_m: float = 5.0, off_slack_m: float = 60.0) -> list[float]:
        """Ardıcıl dayanacaqları xətt boyunca MONOTON (azalmayan) məsafələrə proyeksiya et.

        Real xətt özünü kəsə/üst-üstə düşə bilər: ən yaxın nöqtə səhv hissəyə düşə bilər. Ona görə hər
        dayanacaq üçün namizədlər (xəttə yaxın hər seqment) çıxarılır və dinamik proqramlaşdırma ilə
        cəmi kənarlaşmanı minimuma endirən azalmayan ardıcıllıq seçilir."""
        per_stop: list[list[tuple[float, float]]] = []
        for lat, lon in pts:
            cs = [(prog, off) for _, prog, off in self._candidates(lat, lon)]
            m = min(o for _, o in cs)
            keep = sorted({(round(p, 1), round(o, 1)) for p, o in cs if o <= m + off_slack_m})
            per_stop.append(keep)
        INF = float("inf")
        cost: list[list[float]] = []
        back: list[list[int]] = []
        for i, cand in enumerate(per_stop):
            ci, bi = [], []
            for prog, off in cand:
                if i == 0:
                    ci.append(off)
                    bi.append(-1)
                    continue
                best, arg = INF, -1
                for j, (pp, _) in enumerate(per_stop[i - 1]):
                    if pp <= prog + tol_m and cost[i - 1][j] < best:
                        best, arg = cost[i - 1][j], j
                ci.append(best + off if arg >= 0 else INF)
                bi.append(arg)
            cost.append(ci)
            back.append(bi)
        # son dayanacaqdan geri izlə
        last = min(range(len(cost[-1])), key=lambda k: cost[-1][k])
        if cost[-1][last] == INF:  # monoton ardıcıllıq tapılmadı: ən yaxın nöqtələr + azalmayan düzəliş
            res, cur = [], 0.0
            for cand in per_stop:
                prog = min(cand, key=lambda c: c[1])[0]
                cur = max(cur, prog)
                res.append(cur)
            return res
        res = [0.0] * len(per_stop)
        k = last
        for i in range(len(per_stop) - 1, -1, -1):
            res[i] = per_stop[i][k][0]
            k = back[i][k]
        return res

