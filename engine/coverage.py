from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict

from sqlmodel import select

from database import get_session
from models import Event


CHANNEL_SIGNAL_TYPES = {
    "regulatory": "regulatory_policy",
    "macro": "central_banking_macro",
    "capital": "capital_flows_markets",
    "competitive": "competitive_moves_fs",
    "technology": "technology_ai_infra",
    "cyber": "cyber_fraud_resilience",
    "cross_industry": "cross_industry_signals",
    "research": "research_standards",
}


def compute_coverage(days: int = 30):
    cutoff = datetime.utcnow() - timedelta(days=days)

    by_channel = defaultdict(list)
    by_source = defaultdict(lambda: defaultdict(int))

    with get_session() as session:
        events = session.exec(
            select(Event).where(Event.date >= cutoff)
        ).all()

    for e in events:
        channel = CHANNEL_SIGNAL_TYPES.get(e.signal_type)
        if not channel:
            continue

        by_channel[channel].append(e)
        by_source[channel][e.source_name] += 1

    report = {}

    for channel, events in by_channel.items():
        total = len(events)
        unique_sources = len(by_source[channel])

        # concentration
        if total > 0:
            top_share = max(by_source[channel].values()) / total
        else:
            top_share = 0

        flags = []
        if total < 5:
            flags.append("LOW_VOLUME")
        if unique_sources <= 1:
            flags.append("SOURCE_CONCENTRATION")
        if top_share > 0.6:
            flags.append("HIGH_CONCENTRATION")

        report[channel] = {
            "signals_30d": total,
            "unique_sources": unique_sources,
            "top_source_share": round(top_share, 2),
            "flags": flags,
        }

    return report


def print_coverage_report(days: int = 30):
    report = compute_coverage(days)

    print(f"\nCoverage Intelligence Report ({days} days)\n")
    for ch, data in report.items():
        print(f"{ch}")
        print(f"  Signals: {data['signals_30d']}")
        print(f"  Unique sources: {data['unique_sources']}")
        print(f"  Top source share: {data['top_source_share']}")
        if data["flags"]:
            print(f"  ⚠ Flags: {', '.join(data['flags'])}")
        print("")
