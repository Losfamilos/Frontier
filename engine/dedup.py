import hashlib
from typing import Any, Dict, List


def canonical_uid(source_name: str, url: str, title: str, date_iso: str) -> str:
    base = f"{source_name}|{url.strip()}|{title.strip()}|{date_iso}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:32]


def dedup_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for it in items:
        uid = it.get("event_uid") or canonical_uid(
            it.get("source_name", ""),
            it.get("url", ""),
            it.get("title", ""),
            it.get("date").isoformat() if it.get("date") else "",
        )
        if uid in seen:
            continue
        seen.add(uid)
        it["event_uid"] = uid
        out.append(it)
    return out
