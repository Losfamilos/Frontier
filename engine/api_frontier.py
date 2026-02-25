from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from engine.theme_brief import build_theme_briefs


def _dt(d: datetime | None) -> str | None:
    if not d:
        return None
    # DB dates are naive UTC
    return d.strftime("%Y-%m-%d")


def get_frontier_theme_briefs(top_n: int = 6, events_per_theme: int = 5) -> Dict[str, Any]:
    briefs = build_theme_briefs(top_n=top_n, events_per_theme=events_per_theme)

    out: List[Dict[str, Any]] = []
    for b in briefs:
        out.append(
            {
                "theme": b.theme,
                "score": b.score,
                "why_now": b.why_now,
                "board_question": b.board_question,
                "channels": b.channels,
                "first_seen": _dt(b.first_seen),
                "count_90d": b.count_90d,
                "count_365d": b.count_365d,
                "accel_ratio": b.accel_ratio,
                "evidence": [
                    {
                        "date": _dt(ev.date),
                        "source_name": ev.source_name,
                        "source_tier": int(getattr(ev, "source_tier", 3) or 3),
                        "signal_type": ev.signal_type,
                        "title": ev.title,
                        "url": ev.url,
                    }
                    for ev in b.events
                ],
            }
        )

    return {"items": out, "top_n": top_n, "events_per_theme": events_per_theme}
