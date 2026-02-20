# engine/ingest.py
from __future__ import annotations

from datetime import timezone
from typing import Any, Dict, List, Sequence, Set, Tuple

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


def _configure_sqlite_pragmas(session) -> None:
    """
    Helps with concurrency/locking in SQLite (Codespaces).
    Safe no-op-ish for other DBs: if it fails, we ignore.
    """
    try:
        session.exec("PRAGMA journal_mode=WAL;")
        session.exec("PRAGMA busy_timeout=5000;")  # ms
    except Exception:
        pass


def _chunked(seq: Sequence[Dict[str, Any]], size: int) -> List[List[Dict[str, Any]]]:
    return [list(seq[i : i + size]) for i in range(0, len(seq), size)]


def _existing_event_uids(session, uids: List[str]) -> Set[str]:
    if not uids:
        return set()
    rows = session.exec(select(Event.event_uid).where(Event.event_uid.in_(uids))).all()
    return set(rows)


def upsert_events(items: List[Dict[str, Any]], batch_size: int = 250) -> int:
    """
    Fast path:
    - prefetch existing event_uids per batch
    - insert new events in bulk, commit once
    - insert refs in bulk, commit once
    """
    if not items:
        return 0

    inserted_total = 0

    with get_session() as session:
        _configure_sqlite_pragmas(session)

        for batch in _chunked(items, batch_size):
            uids = [it["event_uid"] for it in batch]
            existing = _existing_event_uids(session, uids)

            new_events: List[Event] = []
            for it in batch:
                if it["event_uid"] in existing:
                    continue

                new_events.append(
                    Event(
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
                )

            if not new_events:
                continue

            session.add_all(new_events)
            session.commit()

            # Refresh IDs so we can create EventSourceRef rows.
            new_refs: List[EventSourceRef] = []
            for ev in new_events:
                session.refresh(ev)
                new_refs.append(
                    EventSourceRef(
                        event_id=ev.id,
                        source_name=ev.source_name,
                        source_tier=ev.source_tier,
                        url=ev.url,
                    )
                )

            session.add_all(new_refs)
            session.commit()

            inserted_total += len(new_events)

    return inserted_total


def ingest_from_connectors(connector_specs, days: int = 365, batch_size: int = 250) -> int:
    """
    Runs connectors one-by-one with:
    - progress logging
    - per-connector exception isolation
    - streaming normalize + batch insert
    """
    total_inserted = 0

   for idx, spec in enumerate(connector_specs, start=1):
    print(f"[DEBUG] connector name = '{spec.name}'", flush=True)
    name = getattr(spec, "name", "<unnamed>")

    # TEMP: SWIFT RSS can hang behind CDN. Skip for now.
    if name.strip() == "swift_rss":
        print("[ingest] skipping swift_rss (temporary)", flush=True)
        continue

    src = getattr(spec, "source_name", "<source>")
    tier = getattr(spec, "source_tier", 0)
    sig = getattr(spec, "signal_type", "<signal>")

        print(f"[ingest] ({idx}/{len(connector_specs)}) {name} — {src} (tier {tier}, {sig})", flush=True)

        try:
            fetched = spec.fetch(days=days) or []
        except Exception as e:
            print(f"[ingest] ⚠️  {name} failed: {type(e).__name__}: {e}", flush=True)
            continue

        print(f"[ingest] {name}: fetched {len(fetched)} items", flush=True)

        # Decorate + normalize immediately
        normalized: List[Dict[str, Any]] = []
        for it in fetched:
            it["source_name"] = src
            it["source_tier"] = tier
            it["signal_type"] = sig
            normalized.append(normalize_item(it, src, tier, sig))

        # Dedup within this connector batch
        normalized = dedup_items(normalized)

        inserted = upsert_events(normalized, batch_size=batch_size)
        total_inserted += inserted

        print(f"[ingest] {name}: inserted {inserted} new events", flush=True)

    print(f"[ingest] done. total inserted={total_inserted}", flush=True)
    return total_inserted
