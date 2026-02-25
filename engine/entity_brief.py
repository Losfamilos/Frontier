from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Set

from sqlmodel import select

from database import get_session
from models import Event
from engine.correlation import compute_cross_channel_correlations


PAIR_WEIGHTS: Dict[Tuple[str, str], float] = {
    ("regulatory_policy", "capital_flows_markets"): 3.0,
    ("central_banking_macro", "capital_flows_markets"): 2.5,
    ("regulatory_policy", "technology_ai_infra"): 2.0,
    ("cyber_fraud_resilience", "technology_ai_infra"): 2.0,
    ("competitive_moves_fs", "technology_ai_infra"): 1.8,
    ("research_standards", "technology_ai_infra"): 1.3,
    ("research_standards", "capital_flows_markets"): 1.6,
    ("cross_industry_signals", "technology_ai_infra"): 1.4,
}

# simple normalizations (v1)
ALIASES = {
    "LLMs": "LLM",
    "LLM Agents": "LLM",
}

# v1: filter pseudo-entities that aren't board-useful
ENTITY_BLACKLIST_SUFFIX = (
    "Study", "Server", "Servers", "Machines", "Case", "Management", "Virtual Machines"
)
ENTITY_BLACKLIST_EXACT = {
    "Case Study",
    "Management Server",
    "Virtual Machines",
    "Vibe Coding",
    "Augmented Generation",
}


def _pair_key(a: str, b: str) -> Tuple[str, str]:
    return (a, b) if a <= b else (b, a)


def convergence_score(channels: List[str]) -> float:
    chs = sorted(set(channels))
    score = 0.0
    for i in range(len(chs)):
        for j in range(i + 1, len(chs)):
            k = _pair_key(chs[i], chs[j])
            score += PAIR_WEIGHTS.get(k, 1.0)
    score += 0.25 * len(chs)
    return round(score, 2)


def normalize_entity(entity: str) -> str:
    entity = entity.strip()
    if entity in ALIASES:
        return ALIASES[entity]
    # collapse simple plural: "LLMs" -> "LLM"
    if entity.endswith("s") and entity[:-1] in ALIASES.values():
        return entity[:-1]
    return entity


def is_entity_useful(entity: str) -> bool:
    if entity in ENTITY_BLACKLIST_EXACT:
        return False
    for suf in ENTITY_BLACKLIST_SUFFIX:
        if entity.endswith(suf):
            return False
    return True


def _contains_entity(ev: Event, entity: str) -> bool:
    hay = ((ev.title or "") + " " + (ev.summary or "")).lower()
    return entity.lower() in hay


def _channel_from_signal_type(ev: Event) -> str:
    # in your DB, signal_type is the proxy for channel
    st = (ev.signal_type or "").strip()
    return {
        "regulatory": "regulatory_policy",
        "macro": "central_banking_macro",
        "capital": "capital_flows_markets",
        "competitive": "competitive_moves_fs",
        "technology": "technology_ai_infra",
        "cyber": "cyber_fraud_resilience",
        "cross_industry": "cross_industry_signals",
        "research": "research_standards",
    }.get(st, "unknown")


def select_events_balanced(entity: str, days: int = 30, limit: int = 6, per_source_cap: int = 2) -> List[Event]:
    """
    Pick events in a board-friendly way:
    - try to cover as many channels as possible
    - cap per source to avoid arXiv spam
    - then fill remaining slots by recency
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    with get_session() as session:
        events = session.exec(select(Event).where(Event.date >= cutoff).order_by(Event.date.desc())).all()

    # filter matches
    matches: List[Event] = [ev for ev in events if _contains_entity(ev, entity)]

    # group by channel, keep recency order
    by_channel: Dict[str, List[Event]] = {}
    for ev in matches:
        ch = _channel_from_signal_type(ev)
        by_channel.setdefault(ch, []).append(ev)

    selected: List[Event] = []
    used_sources: Dict[str, int] = {}
    used_channels: Set[str] = set()

    # first pass: 1 per channel
    for ch, evs in sorted(by_channel.items(), key=lambda x: x[0]):
        for ev in evs:
            src = ev.source_name or "unknown"
            if used_sources.get(src, 0) >= per_source_cap:
                continue
            selected.append(ev)
            used_sources[src] = used_sources.get(src, 0) + 1
            used_channels.add(ch)
            break
        if len(selected) >= limit:
            return selected

    # second pass: fill by recency, respecting per-source cap
    for ev in matches:
        if len(selected) >= limit:
            break
        if ev in selected:
            continue
        src = ev.source_name or "unknown"
        if used_sources.get(src, 0) >= per_source_cap:
            continue
        selected.append(ev)
        used_sources[src] = used_sources.get(src, 0) + 1

    return selected[:limit]


@dataclass
class EntityBrief:
    entity: str
    channels: List[str]
    channel_count: int
    score: float
    events: List[Event]


def build_entity_briefs(days: int = 30, top_n: int = 20, events_per_entity: int = 6) -> List[EntityBrief]:
    corr = compute_cross_channel_correlations(days=days)

    # normalize + merge channels per entity
    merged: Dict[str, Set[str]] = {}
    for r in corr:
        ent = normalize_entity(r["entity"])
        if not is_entity_useful(ent):
            continue
        merged.setdefault(ent, set()).update(r["channels"])

    briefs: List[EntityBrief] = []
    for ent, chs_set in merged.items():
        chs = sorted(chs_set)
        cc = len(chs)
        if cc < 2:
            continue
        score = convergence_score(chs)
        evs = select_events_balanced(ent, days=days, limit=events_per_entity, per_source_cap=2)
        briefs.append(EntityBrief(entity=ent, channels=chs, channel_count=cc, score=score, events=evs))

    briefs.sort(key=lambda b: (b.score, b.channel_count), reverse=True)
    return briefs[:top_n]


def print_entity_briefs(days: int = 30, top_n: int = 12, events_per_entity: int = 6) -> None:
    briefs = build_entity_briefs(days=days, top_n=top_n, events_per_entity=events_per_entity)
    print(f"\nEntity Briefs ({days} days) — top {top_n}\n")

    for b in briefs:
        level = "🔥 STRUCTURAL" if b.channel_count >= 4 else ("⚡ STRONG" if b.channel_count == 3 else "• Emerging")
        print(f"{b.entity}  | score={b.score} | {b.channel_count} channels | {level}")
        print(f"  Channels: {', '.join(b.channels)}")
        if not b.events:
            print("  (No matching events found in last window)")
        else:
            for ev in b.events:
                d = ev.date.strftime('%Y-%m-%d') if ev.date else "n/a"
                print(f"  - {d} | {ev.source_name} | {ev.title}")
                if ev.url:
                    print(f"    {ev.url}")
        print("")
