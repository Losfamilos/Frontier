from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Iterator, Optional, Tuple

from sqlmodel import select

from database import get_session
from models import Event, MovementEventLink


@dataclass
class BaselineCounts:
    recent_90: int
    baseline_90: float

    def as_dict(self) -> Dict[str, Any]:
        return {"recent_90": self.recent_90, "baseline_90": self.baseline_90}

    def __iter__(self) -> Iterator[float]:
        # allow: recent, baseline = baseline_counts_90d_for_movement(...)
        yield float(self.recent_90)
        yield float(self.baseline_90)

    def __getitem__(self, k):
        # allow dict-like access
        if k in ("recent_90", 0):
            return self.recent_90
        if k in ("baseline_90", 1):
            return self.baseline_90
        raise KeyError(k)

    def __int__(self) -> int:
        return int(self.recent_90)


def _parse_args(*args, **kwargs) -> Tuple[Optional[Any], Optional[int], int]:
    days = int(kwargs.get("days", 365))
    session = None
    movement_id = None

    for a in args:
        if isinstance(a, int):
            movement_id = a
        else:
            if hasattr(a, "exec"):
                session = a

    return session, movement_id, days


def baseline_counts_90d_for_movement(*args, **kwargs) -> BaselineCounts:
    session, movement_id, days = _parse_args(*args, **kwargs)
    if movement_id is None:
        return BaselineCounts(recent_90=0, baseline_90=0.0)

    now = datetime.utcnow()
    cutoff_days = now - timedelta(days=days)
    cutoff_90 = now - timedelta(days=90)

    def _compute(sess) -> BaselineCounts:
        links = sess.exec(select(MovementEventLink).where(MovementEventLink.movement_id == movement_id)).all()
        ev_ids = [l.event_id for l in links]
        if not ev_ids:
            return BaselineCounts(recent_90=0, baseline_90=0.0)

        events = sess.exec(select(Event).where(Event.id.in_(ev_ids))).all()

        recent_90 = sum(1 for ev in events if ev.date and ev.date >= cutoff_90)

        baseline_events = [ev for ev in events if ev.date and (ev.date >= cutoff_days) and (ev.date < cutoff_90)]
        baseline_total = len(baseline_events)

        baseline_span_days = max(1, days - 90)
        baseline_90 = (baseline_total / baseline_span_days) * 90.0

        return BaselineCounts(recent_90=recent_90, baseline_90=round(baseline_90, 2))

    if session is not None:
        return _compute(session)

    with get_session() as sess:
        return _compute(sess)
