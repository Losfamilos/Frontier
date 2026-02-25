from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Set, List

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

# Capitalized phrases: "Federal Reserve", "Bank of England", "OpenAI" (single word)
ENTITY_REGEX = re.compile(r"\b([A-Z][a-zA-Z0-9]{2,}(?:\s+[A-Z][a-zA-Z0-9]{2,})*)\b")

# Hard stopwords (sentence starters, months, weekdays, etc.)
STOP_PHRASES = {
    "The","This","That","These","Those","Today","Tomorrow","Following",
    "January","February","March","April","May","June","July","August",
    "September","October","November","December",
    "Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday",
    "And","For","With","From","Based","While","How","What","Once",
    "State","Update","Results","Communication",
    "United States","Europe","France","China","Russia","European",
}

# Single-word junk we’ve observed in your corpus
STOP_SINGLE = {
    "However","Next","Additional","Additionally","When","Although","First","Second","There","Free",
    "Because","Analysis","Instead","During","Note","Some","Most","After","Real","Current","Model",
    "Network","Safety","Secure","Trust","Security","Press","News","Report","Global","International",
    "Market","Capital","Technology","Research","Python","Windows","HTML","API",
}

# Allowlist for single-word entities (v1). We can grow this over time.
ALLOW_SINGLE = {
    "OpenAI","Microsoft","Amazon","Google","Apple","Meta","Nvidia","NVidia",
    "Visa","Mastercard","PayPal","Stripe","Adyen","Revolut","Klarna",
    "SWIFT","Swift","BIS","ECB","Fed","FOMC","BoE","CISA","NCSC","FINRA","DTCC","Nasdaq",
    "SEC","EBA","ESMA","EIOPA",
    "AWS","Azure",
    "ChatGPT","LLM","LLMs",
}

def extract_entities(text: str) -> Set[str]:
    """
    Heuristic extractor tuned for board-grade signal:
    - Multi-word entities are allowed after filtering.
    - Single-word entities are only allowed if in ALLOW_SINGLE.
    """
    if not text:
        return set()

    matches: List[str] = ENTITY_REGEX.findall(text)
    out: Set[str] = set()

    for m in matches:
        m = m.strip()
        if not m:
            continue

        # Drop exact phrase stopwords
        if m in STOP_PHRASES:
            continue

        # Tokenize
        parts = m.split()

        # Drop if any token is very short
        if any(len(p) < 3 for p in parts):
            continue

        # Single-word policy: allowlist only
        if len(parts) == 1:
            if m in STOP_SINGLE:
                continue
            if m not in ALLOW_SINGLE:
                continue
            out.add(m)
            continue

        # Multi-word policy: filter obvious sentence-starter junk
        if parts[0] in STOP_SINGLE or parts[0] in STOP_PHRASES:
            continue

        # Avoid generic endings like "Press Releases" if they sneak in
        if m.endswith("Press Releases") or m.endswith("Press Release") or m.endswith("News"):
            continue

        out.add(m)

    return out


def compute_cross_channel_correlations(days: int = 30):
    cutoff = datetime.utcnow() - timedelta(days=days)
    entity_channels: Dict[str, Set[str]] = defaultdict(set)

    with get_session() as session:
        events = session.exec(select(Event).where(Event.date >= cutoff)).all()

    for e in events:
        channel = CHANNEL_SIGNAL_TYPES.get(e.signal_type)
        if not channel:
            continue

        text = f"{e.title or ''} {e.summary or ''}"
        for ent in extract_entities(text):
            entity_channels[ent].add(channel)

    results = []
    for ent, channels in entity_channels.items():
        if len(channels) >= 2:
            results.append(
                {
                    "entity": ent,
                    "channels": sorted(channels),
                    "channel_count": len(channels),
                }
            )

    results.sort(key=lambda x: x["channel_count"], reverse=True)
    return results


def print_cross_channel_report(days: int = 30, top_n: int = 30):
    results = compute_cross_channel_correlations(days)

    print(f"\nCross-Channel Correlation Report ({days} days)\n")

    for r in results[:top_n]:
        cc = r["channel_count"]
        if cc >= 4:
            level = "🔥 STRUCTURAL SHIFT"
        elif cc == 3:
            level = "⚡ STRONG TRANSITION"
        else:
            level = "• Emerging"

        print(f"{r['entity']}  ({cc} channels)  {level}")
        print(f"  Channels: {', '.join(r['channels'])}")
        print("")
