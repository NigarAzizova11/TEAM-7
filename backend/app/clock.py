"""Vahid vaxt mexanizmi.

Bütün biznes məntiqi (bildirişlərin vaxtı, simulyator, 10 dəqiqəlik qayda, demo seed)
vaxtı YALNIZ buradan alır. Demo üçün qaydalar (məs. 10 dəqiqə) qısaldılmır; əvəzində
demo seed keçmiş vaxtlı məlumat yaradır və onu real analiz kodundan keçirir.

Testlər `freeze()` ilə vaxtı idarə edir. İstehsalda həmişə real UTC saatdır.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Iterator

_frozen: datetime | None = None


def now() -> datetime:
    """Timezone-aware UTC vaxt."""
    if _frozen is not None:
        return _frozen
    return datetime.now(timezone.utc)


def ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("naive datetime qəbul edilmir; yalnız timezone-aware UTC")
    return dt.astimezone(timezone.utc)


def freeze(dt: datetime) -> None:
    global _frozen
    _frozen = ensure_utc(dt)


def advance(delta: timedelta) -> datetime:
    global _frozen
    if _frozen is None:
        raise RuntimeError("saat dondurulmayıb")
    _frozen = _frozen + delta
    return _frozen


def unfreeze() -> None:
    global _frozen
    _frozen = None


@contextmanager
def frozen(dt: datetime) -> Iterator[None]:
    freeze(dt)
    try:
        yield
    finally:
        unfreeze()
