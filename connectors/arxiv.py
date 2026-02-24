import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx


def _hash(uid: str) -> str:
    return hashlib.sha256(uid.encode("utf-8")).hexdigest()[:32]


ARXIV_API = "https://export.arxiv.org/api/query"


def fetch_arxiv(query: str, days: int = 365, max_results: int = 50) -> List[Dict[str, Any]]:
    # arXiv returns Atom XML. We'll parse minimal fields.
    # Example query: all:"tokenized deposits" OR all:"post-quantum cryptography finance"
    params = {
        "search_query": query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }

    timeout = httpx.Timeout(30.0, connect=5.0)
    headers = {"User-Agent": "frontier-radar/1.0"}
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        r = client.get(ARXIV_API, params=params)
        r.raise_for_status()

    root = ET.fromstring(r.text)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    out = []

    cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)

    for entry in root.findall("atom:entry", ns):
        title = (entry.find("atom:title", ns).text or "").strip().replace("\n", " ")
        link_el = entry.find("atom:id", ns)
        url = (link_el.text or "").strip() if link_el is not None else ""

        published_el = entry.find("atom:published", ns)
        if published_el is None:
            continue
        dt = datetime.fromisoformat(published_el.text.replace("Z", "+00:00"))
        if dt.timestamp() < cutoff:
            continue

        summary_el = entry.find("atom:summary", ns)
        raw_text = (summary_el.text or "").strip() if summary_el is not None else ""

        uid = _hash(f"arxiv|{url}|{dt.isoformat()}|{title}")

        out.append(
            {
                "event_uid": uid,
                "date": dt,
                "title": title,
                "url": url,
                "raw_text": raw_text,
            }
        )
    return out

from connectors.registry import ConnectorSpec, register

register(ConnectorSpec(
    name="arxiv",
    source_name="arXiv",
    source_tier=2,
    signal_type="research",
    fetch=FETCH_FUNCTION_HER,
))

# --- connector registration (must run at import time) ---
from connectors.registry import ConnectorSpec, register

_fetch = globals().get("fetch") or globals().get("fetch_arxiv") or globals().get("load") or globals().get("run")

if _fetch is None:
    raise RuntimeError("arxiv connector: could not find a fetch function (expected fetch/fetch_arxiv/load/run).")

register(ConnectorSpec(
    name="arxiv",
    source_name="arXiv",
    source_tier=2,
    signal_type="research",
    fetch=_fetch,
))
