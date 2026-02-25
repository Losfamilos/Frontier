from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from sqlmodel import select

from connectors.rss import fetch_rss
from database import get_session
from engine.ingest import normalize_item
from engine.sources import load_sources_config, flatten_enabled_sources
from models import Event


# Map vores 8 channels -> signal_type (bruges downstream i dit system)
CHANNEL_TO_SIGNAL_TYPE = {
    "regulatory_policy": "regulatory",
    "central_banking_macro": "macro",
    "capital_flows_markets": "capital",
    "competitive_moves_fs": "competitive",
    "technology_ai_infra": "technology",
    "cyber_fraud_resilience": "cyber",
    "cross_industry_signals": "cross_industry",
    "research_standards": "research",
}


@dataclass
class Coverage:
    inserted_total: int
    fetched_total: int
    by_channel_inserted: Dict[str, int]
    by_source_inserted: Dict[str, int]   # "channel_key :: source_name" -> inserted
    by_source_fetched: Dict[str, int]    # "channel_key :: source_name" -> fetched
    errors: List[str]


def ingest_from_sources_yaml(days: int = 365) -> Coverage:
    cfg = load_sources_config("sources.yaml")
    pairs = flatten_enabled_sources(cfg)

    inserted_total = 0
    fetched_total = 0

    by_channel_inserted: Dict[str, int] = {}
    by_source_inserted: Dict[str, int] = {}
    by_source_fetched: Dict[str, int] = {}
    errors: List[str] = []

    with get_session() as session:
        for i, (ch, src) in enumerate(pairs, start=1):
            if src.type != "rss":
                # html connectors kommer i senere step
                continue

            signal_type = CHANNEL_TO_SIGNAL_TYPE.get(ch.key, ch.key)

            print(f"[ingest-yaml] ({i}) {ch.key} — {src.name} (tier {src.tier}, {signal_type})")
            try:
                items = fetch_rss(src.url, days=days)
            except Exception as e:
                msg = f"{ch.key}::{src.name} -> {type(e).__name__}: {e}"
                print(f"[ingest-yaml] ⚠️  {msg}")
                errors.append(msg)
                continue

            fetched_total += len(items)
            source_key = f"{ch.key} :: {src.name}"
            by_source_fetched[source_key] = by_source_fetched.get(source_key, 0) + len(items)

            normalized: List[dict] = []
            for it in items:
                try:
                    normalized.append(normalize_item(it, source_name=src.name, source_tier=src.tier, signal_type=signal_type))
                except Exception as e:
                    msg = f"normalize failed {ch.key}::{src.name} -> {type(e).__name__}: {e}"
                    print(f"[ingest-yaml] ⚠️  {msg}")
                    errors.append(msg)

            inserted_this_source = 0

            for item in normalized:
                if not isinstance(item.get("date"), datetime):
                    continue

                # Store naive UTC in DB (samme som engine/ingest.py)
                d = item["date"]
                if d.tzinfo is not None:
                    d = d.astimezone(timezone.utc).replace(tzinfo=None)
                item["date"] = d

                with session.no_autoflush:
                    exists = session.exec(select(Event).where(Event.event_uid == item["event_uid"])).first()
                if exists:
                    continue

                session.add(Event(**item))
                inserted_this_source += 1
                inserted_total += 1

            by_channel_inserted[ch.key] = by_channel_inserted.get(ch.key, 0) + inserted_this_source
            by_source_inserted[source_key] = by_source_inserted.get(source_key, 0) + inserted_this_source

        session.commit()

    print(f"[ingest-yaml] done. fetched={fetched_total}, inserted={inserted_total}")

    return Coverage(
        inserted_total=inserted_total,
        fetched_total=fetched_total,
        by_channel_inserted=by_channel_inserted,
        by_source_inserted=by_source_inserted,
        by_source_fetched=by_source_fetched,
        errors=errors,
    )


def print_coverage(cov: Coverage, top_n: int = 20) -> None:
    print("\nCoverage (inserted per channel):")
    for ch, n in sorted(cov.by_channel_inserted.items(), key=lambda x: x[1], reverse=True):
        print(f"- {ch}: {n}")

    print("\nTop sources (inserted):")
    for k, n in sorted(cov.by_source_inserted.items(), key=lambda x: x[1], reverse=True)[:top_n]:
        fetched = cov.by_source_fetched.get(k, 0)
        print(f"  {n:>4} inserted / {fetched:>4} fetched  —  {k}")

    if cov.errors:
        print("\nErrors (first 20):")
        for e in cov.errors[:20]:
            print("  -", e)
        if len(cov.errors) > 20:
            print(f"  (+{len(cov.errors)-20} more)")


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Ingest from sources.yaml with coverage reporting")
    p.add_argument("--days", type=int, default=30)
    args = p.parse_args()

    cov = ingest_from_sources_yaml(days=args.days)
    print_coverage(cov)
