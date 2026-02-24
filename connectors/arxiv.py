from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List
from urllib.parse import quote_plus

import feedparser


def fetch_arxiv(query: str, days: int = 365, max_results: int = 80) -> List[Dict]:
    """
    Minimal arXiv fetcher that returns a list of event dicts:
    {title, url, date, source_name}
    Uses arXiv API (Atom).
    """

    # ✅ FIX: URL-encode query to avoid InvalidURL errors
    encoded_query = quote_plus(query)

    url = (
        f"http://export.arxiv.org/api/query?"
        f"search_query={encoded_query}"
        f"&start=0"
        f"&max_results={max_results}"
    )

    feed = feedparser.parse(url)

    cutoff = datetime.utcnow() - timedelta(days=days)
    events: List[Dict] = []

    for entry in getattr(feed, "entries", []):
        published = None

        if getattr(entry, "published_parsed", None):
            published = datetime(*entry.published_parsed[:6])

        if not published or published < cutoff:
            continue

        events.append(
            {
                "title": getattr(entry, "title", "").strip(),
                "url": getattr(entry, "link", None),
                "date": published,
                "source_name": "arXiv",
            }
        )

    return events
