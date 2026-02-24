import feedparser
from datetime import datetime, timedelta


def fetch_arxiv(query: str, days: int = 365, max_results: int = 50):
    """
    Very simple arXiv RSS fetcher.
    """
    url = f"http://export.arxiv.org/api/query?search_query={query}&start=0&max_results={max_results}"
    feed = feedparser.parse(url)

    cutoff = datetime.utcnow() - timedelta(days=days)

    events = []

    for entry in feed.entries:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            published = datetime(*entry.published_parsed[:6])
        else:
            continue

        if published < cutoff:
            continue

        events.append(
            {
                "title": entry.title,
                "url": entry.link,
                "date": published,
                "source_name": "arXiv",
            }
        )

    return events
