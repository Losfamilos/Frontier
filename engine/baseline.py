from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Iterator

from sqlmodel import Session, select

from models import Event, MovementEventLink


@dataclass
class BaselineCounts:
    recent_90: int
    baseline_90: float

    def as_dict(self) -> Dict[str, Any]:
        return {"recent_90": int(self.recent_90), "baseline_90": float(self.baseline_90)}

    def __iter__(self) -> Iterator[float]:
        # allow: recent, baseline = baseline_counts_90d_for_movement(...)
        yield float(self.recent_90)
        yield float(self.baseline_90)


def baseline_counts_90d_for_movement(session: Session, movement_id: int) -> BaselineCounts:
    """
    Compute:
      - recent_90: events in last 90 days
      - baseline_90: events in the 90-day window BEFORE that (days 90–180 ago)
    This gives a stable baseline that excludes the most recent burst.
    """
    now = datetime.utcnow()
    cutoff_90 = now - timedelta(days=90)
    cutoff_180 = now - timedelta(days=180)

    links = session.exec(
        select(MovementEventLink).where(MovementEventLink.movement_id == movement_id)
    ).all()
    ev_ids = [l.event_id for l in links if l.event_id is not None]
    if not ev_ids:
        return BaselineCounts(recent_90=0, baseline_90=0.0)

    evs = session.exec(select(Event).where(Event.id.in_(ev_ids))).all()

    recent_90 = 0
    baseline_90 = 0
    for e in evs:
        if not getattr(e, "date", None):
            continue
        d = e.date
        if d >= cutoff_90:
            recent_90 += 1
        elif cutoff_180 <= d < cutoff_90:
            baseline_90 += 1

    return BaselineCounts(recent_90=recent_90, baseline_90=float(baseline_90))
