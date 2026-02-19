from datetime import datetime

from sqlmodel import select

from database import get_session
from models import Movement, MovementSnapshot, TextSnapshot, ThemeSnapshot


def quarter_id_for(dt: datetime) -> str:
    q = (dt.month - 1) // 3 + 1
    return f"{dt.year}Q{q}"


def create_snapshot(themes: list, executive_summary: str, discussion_topics: str) -> str:
    qid = quarter_id_for(datetime.utcnow())
    with get_session() as session:
        # Upsert text snapshot
        existing = session.exec(select(TextSnapshot).where(TextSnapshot.quarter_id == qid)).first()
        if existing:
            existing.executive_summary = executive_summary
            existing.discussion_topics = discussion_topics
        else:
            session.add(
                TextSnapshot(
                    quarter_id=qid,
                    executive_summary=executive_summary,
                    discussion_topics=discussion_topics,
                )
            )

        # Themes
        for t in themes:
            top_ids = ",".join(str(x) for x in t["top_movements"][:10])
            session.add(
                ThemeSnapshot(
                    quarter_id=qid,
                    theme=t["theme"],
                    theme_score=t["theme_score"],
                    confidence_label=t["confidence_label"],
                    acceleration_arrow=t["acceleration_arrow"],
                    top_movement_ids=top_ids,
                )
            )

        # Movements snapshot from current movement table
        movements = session.exec(select(Movement)).all()
        for m in movements:
            session.add(
                MovementSnapshot(
                    quarter_id=qid,
                    movement_id=m.id,
                    theme=m.theme,
                    impact_score=m.impact_score,
                    stabilized_impact=m.stabilized_impact,
                    confidence_label=m.confidence_label,
                    acceleration_arrow=m.acceleration_arrow,
                    persistence=m.persistence,
                )
            )

        session.commit()
    return qid
