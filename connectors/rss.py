import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List

import feedparser


def _hash(uid: str) -> str:
    return hashlib.sha256(uid.encode("utf-8")).hexdigest()[:32]


def fetch_rss(feed_url: str, days: int = 365) -> List[Dict[str, Any]]:
    feed = feedparser.parse(feed_url)
    out = []
    cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)

    for entry in feed.entries:
        # try published, fallback updated
        ts = None
        if getattr(entry, "published_parsed", None):
            ts = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).timestamp()
            dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        elif getattr(entry, "updated_parsed", None):
            ts = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc).timestamp()
            dt = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
        else:
            continue

        if ts < cutoff:
            continue

        url = getattr(entry, "link", "")
        title = getattr(entry, "title", "").strip()
        uid = _hash(f"{feed_url}|{url}|{title}|{dt.isoformat()}")

        out.append(
            {
                "event_uid": uid,
                "date": dt,
                "title": title,
                "url": url,
                "raw_text": getattr(entry, "summary", "") or getattr(entry, "description", "") or "",
            }
        )
    return out
