from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import feedparser
import requests


def _to_datetime(entry) -> Optional[datetime]:
    # feedparser gives *_parsed as time.struct_time
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        t = getattr(entry, key, None)
        if t:
            try:
                dt = datetime(*t[:6])
                # treat naive as UTC
                return dt.replace(tzinfo=timezone.utc)
            except Exception:
                pass

    # fallback: try string fields (best-effort)
    for key in ("published", "updated", "created"):
        s = getattr(entry, key, None)
        if isinstance(s, str) and s.strip():
            try:
                dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception:
                return None
    return None


def fetch_rss(feed_url: str, days: int = 365, max_items: int = 200) -> List[Dict]:
    """
    Robust RSS/Atom fetcher.
    Returns list of dicts: {title, summary, url, date}
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (FrontierRadar/1.0; +https://github.com/Losfamilos/Frontier)",
        "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.7",
    }

    r = requests.get(feed_url, headers=headers, timeout=25, allow_redirects=True)
    r.raise_for_status()

    feed = feedparser.parse(r.text)

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out: List[Dict] = []

    for entry in getattr(feed, "entries", [])[:max_items]:
        title = (getattr(entry, "title", "") or "").strip()
        url = getattr(entry, "link", None)

        summary = getattr(entry, "summary", None) or getattr(entry, "description", None) or ""
        if not isinstance(summary, str):
            summary = ""

        dt = _to_datetime(entry)
        if not dt:
            continue
        if dt < cutoff:
            continue

        out.append(
            {
                "title": title,
                "summary": summary.strip(),
                "url": url,
                "date": dt,
            }
        )

    return out
