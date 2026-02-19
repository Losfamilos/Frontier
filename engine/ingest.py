from datetime import timezone
from typing import Any, Dict, List

from sqlmodel import select

from database import get_session
from engine.dedup import dedup_items
from models import Event, EventSourceRef


def normalize_item(item: Dict[str, Any], source_name: str, source_tier: int, signal_type: str) -> Dict[str, Any]:
    dt = item["date"]
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    title = (item.get("title") or "").strip()
    url = (item.get("url") or "").strip()
    raw_text = (item.get("raw_text") or "").strip()

    # v1 summary = first 240 chars (deterministic); can upgrade later.
    summary = raw_text or title
    summary = " ".join(summary.split())[:240]

    return {
        "event_uid": item["event_uid"],
        "date": dt,
        "source_name": source_name,
        "source_tier": int(source_tier),
        "signal_type": signal_type,
        "title": title,
        "summary": summary,
        "url": url,
        "raw_text": raw_text,
        "entities": None,
        "theme_hint": item.get("theme_hint"),
    }


def upsert_events(items: List[Dict[str, Any]]) -> int:
    inserted = 0
    with get_session() as session:
        for it in items:
            existing = session.exec(select(Event).where(Event.event_uid == it["event_uid"])).first()
            if existing:
                # keep immutable-ish; update summary/raw_text if empty
                if not existing.summary and it["summary"]:
                    existing.summary = it["summary"]
                if not existing.raw_text and it.get("raw_text"):
                    existing.raw_text = it["raw_text"]
                session.add(existing)
                continue

            ev = Event(
                event_uid=it["event_uid"],
                date=it["date"],
                source_name=it["source_name"],
                source_tier=it["source_tier"],
                signal_type=it["signal_type"],
                title=it["title"],
                summary=it["summary"],
                url=it["url"],
                raw_text=it.get("raw_text"),
                entities=it.get("entities"),
                theme_hint=it.get("theme_hint"),
            )
            session.add(ev)
            session.commit()
            session.refresh(ev)

            session.add(
                EventSourceRef(
                    event_id=ev.id,
                    source_name=it["source_name"],
                    source_tier=it["source_tier"],
                    url=it["url"],
                )
            )
            session.commit()
            inserted += 1

    return inserted


def ingest_from_connectors(connector_specs, days: int = 365) -> int:
    all_items = []
    for spec in connector_specs:
        fetched = spec.fetch(days=days)
        for it in fetched:
            it["source_name"] = spec.source_name
            it["source_tier"] = spec.source_tier
            it["signal_type"] = spec.signal_type
        all_items.extend(fetched)

    all_items = dedup_items(all_items)
    normalized = [normalize_item(it, it["source_name"], it["source_tier"], it["signal_type"]) for it in all_items]
    return upsert_events(normalized)
