from __future__ import annotations

import hashlib
import inspect
from datetime import datetime, timezone
from typing import Iterable, List

from sqlmodel import select

from database import get_session
from models import Event


def _stable_event_uid(source_name: str, url: str | None, title: str | None, date: datetime | None) -> str:
    d = ""
    if isinstance(date, datetime):
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        d = date.astimezone(timezone.utc).strftime("%Y-%m-%d")
    base = "|".join(
        [
            (source_name or "").strip().lower(),
            (url or "").strip(),
            (title or "").strip().lower(),
            d,
        ]
    )
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def _parse_date(v) -> datetime | None:
    if isinstance(v, datetime):
        return v
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        except Exception:
            return None
    return None


def normalize_item(item: dict, source_name: str, source_tier: int, signal_type: str) -> dict:
    title = item.get("title") or item.get("headline") or item.get("name") or ""
    url = item.get("url") or item.get("link")
    date = _parse_date(item.get("date") or item.get("published") or item.get("created_at"))

    # DB has NOT NULL on event.summary
    summary = item.get("summary")
    if summary is None:
        summary = item.get("description") or item.get("abstract") or ""
    if summary is None:
        summary = ""

    event_uid = item.get("event_uid")
    if not event_uid:
        event_uid = _stable_event_uid(source_name, url, title, date)

    return {
        "event_uid": event_uid,
        "title": (title or "").strip(),
        "summary": summary.strip() if isinstance(summary, str) else "",
        "url": url,
        "date": date,
        "source_name": source_name,
        "source_tier": int(source_tier),
        "signal_type": signal_type,
    }


def _fetch_is_days_only(fetch) -> bool:
    """
    Only run connectors that can be called as fetch(days=...).
    If fetch requires other required positional args (e.g. feed_url), skip it.
    """
    try:
        sig = inspect.signature(fetch)
    except Exception:
        return True

    for p in sig.parameters.values():
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD):
            if p.name == "days":
                continue
            if p.default is inspect._empty:
                return False
    return True


def ingest_from_connectors(connectors: Iterable, days: int = 365) -> int:
    inserted = 0

    with get_session() as session:
        for i, spec in enumerate(connectors, start=1):
            name = getattr(spec, "name", "unknown")
            src = getattr(spec, "source_name", "unknown")
            tier = getattr(spec, "source_tier", 3)
            sig = getattr(spec, "signal_type", "research")
            fetch = getattr(spec, "fetch", None)

            if not callable(fetch):
                print(f"[ingest] skipping template connector {name} (no fetch)")
                continue

            if not _fetch_is_days_only(fetch):
                print(f"[ingest] skipping template connector {name} (requires args)")
                continue

            print(f"[ingest] ({i}/{len(list(connectors)) if hasattr(connectors,'__len__') else '?'}) {name} — {src} (tier {tier}, {sig})")

            try:
                items = fetch(days=days)
            except Exception as e:
                print(f"[ingest] ⚠️  {name} failed: {e}")
                continue

            print(f"[ingest] {name}: fetched {len(items)} items")

            normalized: List[dict] = []
            for it in items:
                try:
                    normalized.append(normalize_item(it, src, tier, sig))
                except Exception as e:
                    print(f"[ingest] normalize failed ({name}): {e}")

            for item in normalized:
                if not isinstance(item.get("date"), datetime):
                    continue

                # Store naive UTC in DB
                d = item["date"]
                if d.tzinfo is not None:
                    d = d.astimezone(timezone.utc).replace(tzinfo=None)
                item["date"] = d

                with session.no_autoflush:
                    exists = session.exec(select(Event).where(Event.event_uid == item["event_uid"])).first()
                if exists:
                    continue

                session.add(Event(**item))
                inserted += 1

        session.commit()

    print(f"[ingest] done. total inserted={inserted}")
    return inserted
