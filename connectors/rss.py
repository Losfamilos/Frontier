import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List

import feedparser
import httpx


def _hash(uid: str) -> str:
    return hashlib.sha256(uid.encode("utf-8")).hexdigest()[:32]


def fetch_rss(feed_url: str, days: int = 365) -> List[Dict[str, Any]]:
    timeout = httpx.Timeout(30.0, connect=5.0)
    headers = {"User-Agent": "frontier-radar/1.0 (+https://github.com/yourrepo)"}

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            r = client.get(feed_url)
            r.raise_for_status()
            content = r.content
    except Exception as e:
        print(f"[rss] ⚠️  failed to fetch {feed_url}: {type(e).__name__}: {e}", flush=True)
        return []

    feed = feedparser.parse(content)

    out: List[Dict[str, Any]] = []
    cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)

    for entry in feed.entries:
        ts = None

        if getattr(entry, "published_parsed", None):
            dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            ts = dt.timestamp()
        elif getattr(entry, "updated_parsed", None):
            dt = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
            ts = dt.timestamp()
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
                "raw_text": getattr(entry, "summary", "")
                or getattr(entry, "description", "")
                or "",
            }
        )

    return out

from connectors.registry import ConnectorSpec, register

register(ConnectorSpec(
    name="rss",
    source_name="RSS",
    source_tier=2,
    signal_type="news",
    fetch=FETCH_FUNCTION_HER,
))

# --- connector registration (must run at import time) ---
from connectors.registry import ConnectorSpec, register

# Find the best fetch function in this module
# Try common names; replace with your actual function if needed
_fetch = globals().get("fetch") or globals().get("fetch_rss") or globals().get("load") or globals().get("run")

if _fetch is None:
    raise RuntimeError("rss connector: could not find a fetch function (expected fetch/fetch_rss/load/run).")

register(ConnectorSpec(
    name="rss",
    source_name="RSS",
    source_tier=2,
    signal_type="news",
    fetch=_fetch,
))
