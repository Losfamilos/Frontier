import hashlib
import random
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx


def _hash(uid: str) -> str:
    return hashlib.sha256(uid.encode("utf-8")).hexdigest()[:32]


ARXIV_API = "https://export.arxiv.org/api/query"


def fetch_arxiv(query: str, days: int = 365, max_results: int = 50) -> List[Dict[str, Any]]:
    params = {
        "search_query": query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }

    timeout = httpx.Timeout(30.0, connect=5.0)
    headers = {"User-Agent": "frontier-radar/1.0"}

    # ---- fetch with retry/backoff for 429 ----
    last_exc: Exception | None = None
    r = None

    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        for attempt in range(1, 4):  # 3 attempts
            try:
                r = client.get(ARXIV_API, params=params)
                r.raise_for_status()
                break
            except httpx.HTTPStatusError as e:
                last_exc = e
                status = e.response.status_code if e.response is not None else None

                if status == 429:
                    # exponential backoff + jitter
                    sleep_s = (2 ** (attempt - 1)) + random.random()
                    print(
                        f"[arxiv] 429 rate limited, retrying in {sleep_s:.1f}s (attempt {attempt}/3)",
                        flush=True,
                    )
                    time.sleep(sleep_s)
                    continue

                # other HTTP errors should surface
                raise
            except Exception as e:
                last_exc = e
                # transient network error: short backoff and retry
                sleep_s = 0.5 * attempt + random.random() * 0.5
                print(
                    f"[arxiv] transient error {type(e).__name__}, retrying in {sleep_s:.1f}s (attempt {attempt}/3)",
                    flush=True,
                )
                time.sleep(sleep_s)
                continue
        else:
            # exhausted retries -> degrade gracefully
            print(f"[arxiv] failed after retries: {type(last_exc).__name__}: {last_exc}", flush=True)
            return []

    assert r is not None  # for type checkers

    root = ET.fromstring(r.text)
    ns = {"atom": "http://www.w3.org/2005/Atom"}

    out: List[Dict[str, Any]] = []
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


# --- REGISTER CONNECTOR ---
from connectors.registry import ConnectorSpec, register

register(
    ConnectorSpec(
        name="arxiv",
        source_name="arXiv",
        source_tier=2,
        signal_type="research",
        fetch=fetch_arxiv,
    )
)
