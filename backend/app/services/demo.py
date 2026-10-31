"""Demo məlumat: real dayanacaqlardan 2 demo marşrut, simulyasiya ssenariləri, demo bildirişləri.

DİQQƏT (hər yerdə açıq göstərilir):
- Dayanacaqlar REAL-dır (dayanacaqlar.csv), marşrutlar isə "Demo A/B" adlı UYDURMA/sxematik xətlərdir
  (real 88 və ya başqa xətt deyil). Xətt dayanacaqlar arasında düz seqmentlərdir, real yol deyil.
- Avtobuslar və GPS SİMULYASİYADIR. `demo_seed` mənbəli bildirişlər DEMO-dur.
- Sıfırlama yalnız demo/dinamik cədvəlləri təmizləyir; `stops` cədvəlinə toxunmur.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session, selectinload

from ..config import Settings
from ..geo import Polyline, angle_diff_deg, bearing_deg, haversine_m
from ..models import (
    Alert,
    Bus,
    CrowdReport,
    DemoState,
    Direction,
    DirectionStop,
    GpsPosition,
    Route,
    Stop,
    TrafficReport,
)
from . import analysis, simulator
from .crowd import LEVEL_VALUE
from .transit import stop_infos

SIM_LOCK_KEY = 727_001
BOT_PERIOD_S = 75
TARGET_SPEED_MPS = 6.25  # ~22.5 km/s: hədəf intervalı hesablamaq üçün nominal sürət

BAKU_BBOX = (40.30, 40.50, 49.70, 50.05)  # lat_min, lat_max, lon_min, lon_max (kobud)


class DemoError(RuntimeError):
    pass


@dataclass(frozen=True)
class DirSpec:
    name: str
    buses: int
    code_prefix: str  # avtobus kodları: f"{route.code}-{prefix}{i}"


@dataclass(frozen=True)
class RouteSpec:
    code: str
    name: str
    anchor: tuple[float, float]  # (lat, lon) başlanğıc üçün təxmini nöqtə (Bakı daxilində)
    heading: float  # ilkin istiqamət (dərəcə)
    n_stops: int
    directions: tuple[DirSpec, ...]


ROUTE_SPECS = (
    RouteSpec(
        code="DEMO-A",
        name="Demo A",
        anchor=(40.3795, 49.8470),
        heading=60.0,
        n_stops=12,
        directions=(
            DirSpec("Düz istiqamət (sxematik)", 3, ""),
            DirSpec("Əks istiqamət (sxematik)", 2, "R"),
        ),
    ),
    RouteSpec(
        code="DEMO-B",
        name="Demo B",
        anchor=(40.4050, 49.8200),
        heading=110.0,
        n_stops=11,
        directions=(DirSpec("Düz istiqamət (sxematik)", 3, ""),),
    ),
)


@dataclass(frozen=True)
class ScenarioInfo:
    name: str
    label: str
    description: str


SCENARIOS: dict[str, ScenarioInfo] = {
    "normal": ScenarioInfo(
        "normal",
        "Normal hərəkət",
        "Avtobuslar bərabər interval ilə hərəkət edir; bir neçə demo bildirişi var, biri üçün isə 'Məlumat yoxdur'.",
    ),
    "bunching": ScenarioInfo(
        "bunching",
        "Qruplaşmış avtobuslar",
        "Demo A düz istiqamətdə iki avtobus bir-birinə yaxınlaşıb, arxasında böyük boşluq var.",
    ),
    "slowdown": ScenarioInfo(
        "slowdown",
        "Yol ləngiməsi",
        "Demo A düz istiqamətin bir sxematik hissəsində avtobuslar birlikdə yavaşlayır.",
    ),
    "high_crowd": ScenarioInfo(
        "high_crowd",
        "10 dəqiqə davam edən yüksək sıxlıq",
        "Əvvəlki ~11 dəqiqə üzrə ardıcıl 'Yüksək' demo bildirişləri yaradılır və real analiz kodundan keçir.",
    ),
    "unusual_stop": ScenarioInfo(
        "unusual_stop",
        "Qeyri-adi dayanma",
        "Demo A düz istiqamətdə bir avtobus dayanacaqdan kənarda ~5 dəqiqədir dayanıb, digərləri hərəkət edir.",
    ),
}


# ---------------------------------------------------------------- demo marşrutların seçimi (real dayanacaqlardan)


def _circ_mean(a: float, b: float) -> float:
    ax, ay = math.cos(math.radians(a)), math.sin(math.radians(a))
    bx, by = math.cos(math.radians(b)), math.sin(math.radians(b))
    return (math.degrees(math.atan2(ay + by, ax + bx)) + 360.0) % 360.0


def build_chain(
    stops: list[tuple[int, str, str, float, float]],  # (pk, stop_id, name, lat, lon)
    anchor: tuple[float, float],
    heading: float,
    n: int,
    exclude: set[int],
) -> list[tuple[int, str, str, float, float]]:
    """Deterministik: anchor-a ən yaxın dayanacaqdan başlayıb ardıcıl yaxın dayanacaqlardan xətt qurur."""
    lat_min, lat_max, lon_min, lon_max = BAKU_BBOX
    pool = [
        s
        for s in stops
        if lat_min <= s[3] <= lat_max and lon_min <= s[4] <= lon_max and s[0] not in exclude
    ]
    if len(pool) < n * 3:
        raise DemoError(
            f"Bakı ərazisində demo marşrut üçün kifayət qədər dayanacaq yoxdur ({len(pool)} tapıldı). "
            "Əvvəlcə dayanacaqlar.csv faylını import edin."
        )
    start = min(pool, key=lambda s: haversine_m(anchor[0], anchor[1], s[3], s[4]))
    chain = [start]
    used = {start[0]}
    cur, hd = start, heading
    levels = [(50.0, 250.0, 900.0), (80.0, 200.0, 1300.0), (120.0, 150.0, 2000.0)]
    while len(chain) < n:
        picked = None
        for max_ang, dmin, dmax in levels:
            best, best_score, best_b = None, math.inf, 0.0
            for c in pool:
                if c[0] in used:
                    continue
                d = haversine_m(cur[3], cur[4], c[3], c[4])
                if d < dmin or d > dmax:
                    continue
                b = bearing_deg(cur[3], cur[4], c[3], c[4])
                ad = angle_diff_deg(b, hd)
                if ad > max_ang:
                    continue
                if any(haversine_m(c[3], c[4], x[3], x[4]) < 150.0 for x in chain):
                    continue
                score = abs(d - 450.0) + 6.0 * ad
                if score < best_score:
                    best, best_score, best_b = c, score, b
            if best is not None:
                picked = (best, best_b)
                break
        if picked is None:
            break
        chain.append(picked[0])
        used.add(picked[0][0])
        hd = _circ_mean(hd, picked[1])
        cur = picked[0]
    if len(chain) < 6:
        raise DemoError(f"Demo marşrut üçün ardıcıl dayanacaq zənciri qurula bilmədi (yalnız {len(chain)} dayanacaq).")
    return chain


def structure_exists(session: Session) -> bool:
    return session.execute(select(Route.id).where(Route.is_demo.is_(True)).limit(1)).first() is not None


def ensure_structure(session: Session, rebuild: bool = False) -> None:
    if rebuild:
        session.execute(delete(Route).where(Route.source == "demo"))  # yalnız real olmayan demo marşrutlar
        session.flush()
    if structure_exists(session):
        return
    rows = session.execute(select(Stop.id, Stop.stop_id, Stop.name, Stop.lat, Stop.lon).order_by(Stop.id)).all()
    if not rows:
        raise DemoError("'stops' cədvəli boşdur. Əvvəlcə: python -m app.cli import-stops")
    stops = [(r.id, r.stop_id, r.name, r.lat, r.lon) for r in rows]
    used: set[int] = set()
    for spec in ROUTE_SPECS:
        chain = build_chain(stops, spec.anchor, spec.heading, spec.n_stops, used)
        used |= {c[0] for c in chain}
        route = Route(code=spec.code, name=spec.name, is_demo=True, source="demo")
        session.add(route)
        session.flush()
        poly = Polyline.from_points([(c[3], c[4]) for c in chain])
        for ordinal, dspec in enumerate(spec.directions):
            seq_chain = chain if ordinal == 0 else list(reversed(chain))
            length = poly.length
            target = max(120, int(round(length / (dspec.buses * TARGET_SPEED_MPS) / 10.0)) * 10)
            nominal = length / (dspec.buses * target)
            direction = Direction(
                route_id=route.id,
                ordinal=ordinal,
                name=dspec.name,
                target_interval_seconds=target,
                nominal_speed_mps=nominal,
                sim_params={},
            )
            session.add(direction)
            session.flush()
            for seq, c in enumerate(seq_chain):
                session.add(DirectionStop(direction_id=direction.id, seq=seq, stop_pk=c[0]))
            for i in range(1, dspec.buses + 1):
                session.add(
                    Bus(code=f"{spec.code}-{dspec.code_prefix}{i}", direction_id=direction.id, is_active=True, is_simulated=True)
                )
    session.flush()


# ---------------------------------------------------------------- ssenari maketləri


def _layout(
    scenario: str,
    primary: bool,
    direction: Direction,
    stop_d: list[float],
    length: float,
    base_frac: float,
    history_s: float,
) -> tuple[dict, list[float], list[str]]:
    """(sim_params, hər avtobus üçün başlanğıc proqres p0, hər avtobus üçün mode)."""
    n = len(direction.buses)
    v = direction.nominal_speed_mps
    target = direction.target_interval_seconds
    params: dict = {}
    modes = ["moving"] * n
    now_pos: list[float]

    if primary and scenario == "bunching" and n >= 3:
        p0_now = base_frac * length
        now_pos = [p0_now, p0_now - v * 0.15 * target]
        now_pos.append(now_pos[1] - v * 1.8 * target)
        now_pos += [now_pos[-1] - v * target * (i + 1) for i in range(n - 3)]
        starts = [(p - v * history_s) % length for p in now_pos]
    elif primary and scenario == "slowdown":
        j = max(1, round(0.4 * (len(stop_d) - 1)))
        params = {"slow_segments": [{"start_m": stop_d[j], "end_m": stop_d[j + 1], "factor": 0.3}]}
        t_reach0 = max(60.0, min(240.0, history_s - 150.0 - (n - 1) * target))
        starts = [(stop_d[j] - v * (t_reach0 + i * target)) % length for i in range(n)]
    elif primary and scenario == "unusual_stop" and n >= 2:
        j = max(1, round(0.55 * (len(stop_d) - 2)))
        halt_m = (stop_d[j] + stop_d[j + 1]) / 2.0
        params = {"halt": {"bus_code": direction.buses[1].code, "progress_m": halt_m}}
        halted_since = 300.0
        virtual_p1 = halt_m + v * halted_since
        spacing = length / n
        now_pos = [virtual_p1 + spacing * (1 - i) for i in range(n)]
        starts = [(p - v * history_s) % length for p in now_pos]
        starts[1] = (halt_m - v * (history_s - halted_since)) % length
    else:
        spacing = length / n
        now_pos = [base_frac * length - i * spacing for i in range(n)]
        starts = [(p - v * history_s) % length for p in now_pos]
    return params, starts, modes


BASE_FRAC = {"DEMO-A": (0.60, 0.35), "DEMO-B": (0.50,)}
DEFAULT_FRAC = (0.60, 0.35)


def _bot_levels(scenario: str, primary: bool, direction: Direction) -> dict[str, int]:
    """Yalnız əsas (ilk marşrutun 1-ci istiqaməti) üçün demo bildirişləri (açıq işarələnir: source='demo_seed')."""
    if not primary or len(direction.buses) < 3:
        return {}
    codes = [b.code for b in direction.buses]
    if scenario == "normal":
        return {codes[0]: 2, codes[1]: 1}  # codes[2] üçün bilərəkdən məlumat yoxdur
    if scenario == "bunching":
        return {codes[0]: 3, codes[1]: 1, codes[2]: 2}
    if scenario == "slowdown":
        return {c: 2 for c in codes}
    if scenario == "high_crowd":
        return {c: 3 for c in codes}
    if scenario == "unusual_stop":
        return {codes[0]: 2, codes[2]: 2}
    return {}


def _bot_hash(code: str) -> str:
    return f"demo-bot:{code}"


def bot_tick(session: Session, now: datetime) -> int:
    """Aktiv ssenaridə demo bildirişlərini təzələ (açıq işarəli, source='demo_seed')."""
    st = session.get(DemoState, 1)
    if st is None or not st.bot_levels:
        return 0
    buses = {b.code: b.id for b in session.execute(select(Bus)).scalars()}
    last = dict(st.last_bot_at or {})
    added = 0
    for code, level in st.bot_levels.items():
        if code not in buses:
            continue
        prev = datetime.fromisoformat(last[code]) if code in last else None
        if prev is None or (now - prev).total_seconds() >= BOT_PERIOD_S:
            session.add(
                CrowdReport(bus_id=buses[code], level=int(level), session_hash=_bot_hash(code), created_at=now, source="demo_seed")
            )
            last[code] = now.isoformat()
            added += 1
    if added:
        st.last_bot_at = last
    return added


# ---------------------------------------------------------------- ssenarinin tətbiqi (sıfırlama + seed)


def apply_scenario(
    session: Session, name: str, now: datetime, settings: Settings, rebuild_structure: bool = False
) -> dict:
    if name not in SCENARIOS:
        raise DemoError(f"Naməlum ssenari: {name}")
    session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": SIM_LOCK_KEY})
    ensure_structure(session, rebuild=rebuild_structure)

    # YALNIZ dinamik/demo məlumat silinir. `stops` cədvəlinə TOXUNULMUR.
    session.execute(delete(Alert))
    session.execute(delete(CrowdReport))
    session.execute(delete(TrafficReport))
    session.execute(delete(GpsPosition))
    session.flush()

    history_s = float(settings.sim_history_minutes * 60)
    directions = (
        session.execute(
            select(Direction)
            .join(Route)
            .where(Route.is_demo.is_(True))
            .options(
                selectinload(Direction.stops).selectinload(DirectionStop.stop),
                selectinload(Direction.buses),
                selectinload(Direction.route),
            )
            .order_by(Route.id, Direction.ordinal)
        )
        .scalars()
        .all()
    )
    bot_levels: dict[str, int] = {}
    primary_id = directions[0].id if directions else None  # ilk marşrutun 1-ci istiqaməti (id sırası ilə)
    for d in directions:
        d.buses.sort(key=lambda b: b.id)
        stops, poly = stop_infos(d)
        primary = d.id == primary_id
        fracs = BASE_FRAC.get(d.route.code, DEFAULT_FRAC)
        base = fracs[min(d.ordinal, len(fracs) - 1)]
        params, starts, modes = _layout(name, primary, d, [s.d for s in stops], poly.length, base, history_s)
        d.sim_params = params
        for bus, p0, mode in zip(d.buses, starts, modes):
            bus.progress_m = p0
            bus.mode = mode
            bus.last_tick_at = None
            bus.is_active = True
        bot_levels.update(_bot_levels(name, primary, d))
    session.flush()

    simulator.backfill(session, now - timedelta(seconds=history_s), now, settings.sim_history_step_seconds, settings)

    # Demo bildirişləri: əvvəlki ~12 dəqiqə üzrə ardıcıl (açıq 'demo_seed' mənbəli)
    code_to_id = {b.code: b.id for d in directions for b in d.buses}
    last_bot: dict[str, str] = {}
    for idx, (code, level) in enumerate(sorted(bot_levels.items())):
        offset = (idx % 3) * 20
        k = 0
        while True:
            t = now - timedelta(seconds=offset + k * BOT_PERIOD_S)
            if (now - t).total_seconds() > 12.5 * 60:
                break
            session.add(
                CrowdReport(bus_id=code_to_id[code], level=int(level), session_hash=_bot_hash(code), created_at=t, source="demo_seed")
            )
            if k == 0:
                last_bot[code] = t.isoformat()
            k += 1

    state = session.get(DemoState, 1)
    if state is None:
        state = DemoState(id=1, scenario=name, applied_at=now, bot_levels=bot_levels, last_bot_at=last_bot)
        session.add(state)
    else:
        state.scenario, state.applied_at, state.bot_levels, state.last_bot_at = name, now, bot_levels, last_bot
    session.flush()

    result = analysis.evaluate(session, now, settings)
    session.commit()
    return {
        "scenario": name,
        "alerts_created": len(result.created),
        "applied_at": now.isoformat(),
    }


def current_scenario(session: Session) -> DemoState | None:
    return session.get(DemoState, 1)


__all__ = [
    "SCENARIOS",
    "DemoError",
    "apply_scenario",
    "bot_tick",
    "ensure_structure",
    "LEVEL_VALUE",
]
