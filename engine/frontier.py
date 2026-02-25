from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Set, Tuple

from sqlmodel import select

from database import get_session
from models import Event

from engine.entity_brief import (
    convergence_score,
    normalize_entity,
    is_entity_useful,
    select_events_balanced,
)

# signal_type -> channel_key
SIGNAL_TO_CHANNEL = {
    "regulatory": "regulatory_policy",
    "macro": "central_banking_macro",
    "capital": "capital_flows_markets",
    "competitive": "competitive_moves_fs",
    "technology": "technology_ai_infra",
    "cyber": "cyber_fraud_resilience",
    "cross_industry": "cross_industry_signals",
    "research": "research_standards",
}

# High-auth channels = where board actually acts
HIGH_AUTH_CHANNELS = {
    "capital_flows_markets",
    "regulatory_policy",
    "central_banking_macro",
    "competitive_moves_fs",
}

# "Frontier maturity" bonus pr channel (board logic)
CHANNEL_MATURITY_WEIGHT = {
    "capital_flows_markets": 2.2,
    "regulatory_policy": 2.2,
    "competitive_moves_fs": 2.0,
    "central_banking_macro": 1.7,
    "cyber_fraud_resilience": 1.2,
    "technology_ai_infra": 1.0,
    "cross_industry_signals": 1.0,
    "research_standards": 0.6,
}

# Generic umbrella terms that easily dominate but aren’t board-actionable alone.
# (We keep them, but require them to clear high-auth + accel/novelty gates.)
GENERIC_THEME_ENTITIES = {"LLM", "LLMs", "API", "APIs"}


@dataclass
class FrontierItem:
    entity: str
    frontier_score: float
    channels: List[str]
    channel_count: int
    first_seen: datetime | None
    count_90d: int
    count_365d: int
    accel_ratio: float
    has_tier1: bool
    has_tier1_high_auth: bool
    has_any_high_auth: bool


def _channel_of_event(ev: Event) -> str:
    return SIGNAL_TO_CHANNEL.get((ev.signal_type or "").strip(), "unknown")


def _contains_entity(ev: Event, entity: str) -> bool:
    hay = ((ev.title or "") + " " + (ev.summary or "")).lower()
    return entity.lower() in hay


def _first_seen(entity: str) -> datetime | None:
    # simple scan (ok for now)
    with get_session() as session:
        events = session.exec(select(Event).order_by(Event.date.asc())).all()
    for e in events:
        if _contains_entity(e, entity):
            return e.date
    return None


def _counts_and_flags(entity: str) -> Tuple[int, int, Set[str], bool, bool, bool]:
    """
    Returns (count_90d, count_365d, channels_set, has_tier1, has_tier1_high_auth, has_any_high_auth)
    """
    now = datetime.utcnow()
    cutoff_365 = now - timedelta(days=365)
    cutoff_90 = now - timedelta(days=90)

    count_365 = 0
    count_90 = 0
    channels: Set[str] = set()
    has_tier1 = False
    has_tier1_high_auth = False
    has_any_high_auth = False

    with get_session() as session:
        events = session.exec(select(Event).where(Event.date >= cutoff_365)).all()

    for ev in events:
        if not _contains_entity(ev, entity):
            continue

        count_365 += 1
        if ev.date and ev.date >= cutoff_90:
            count_90 += 1

        ch = _channel_of_event(ev)
        if ch != "unknown":
            channels.add(ch)
            if ch in HIGH_AUTH_CHANNELS:
                has_any_high_auth = True

        tier = int(getattr(ev, "source_tier", 3) or 3)
        if tier == 1:
            has_tier1 = True
            if ch in HIGH_AUTH_CHANNELS:
                has_tier1_high_auth = True

    return count_90, count_365, channels, has_tier1, has_tier1_high_auth, has_any_high_auth


def _maturity_bonus(channels: Set[str]) -> float:
    return round(sum(CHANNEL_MATURITY_WEIGHT.get(c, 0.5) for c in channels), 2)


def _novelty_bonus(first_seen: datetime | None) -> float:
    if not first_seen:
        return 0.0
    days = (datetime.utcnow() - first_seen).days
    if days <= 30:
        return 1.5
    if days <= 90:
        return 0.8
    return 0.0


def _accel_bonus(count_90d: int, count_365d: int) -> Tuple[float, float]:
    """
    Structural acceleration = density(90d) / density(365d)
    density = count / window_days
    """
    # Need enough baseline to trust the ratio
    if count_365d < 10:
        return 0.0, 1.0

    recent_density = count_90d / 90
    baseline_density = count_365d / 365
    if baseline_density == 0:
        return 2.0, 2.0

    ratio = recent_density / baseline_density

    if ratio >= 2.0:
        return 2.5, round(ratio, 2)
    if ratio >= 1.5:
        return 1.8, round(ratio, 2)
    if ratio >= 1.2:
        return 0.8, round(ratio, 2)
    return 0.0, round(ratio, 2)


def _passes_frontier_gate(
    entity: str,
    channels: Set[str],
    first_seen: datetime | None,
    accel_ratio: float,
    has_any_high_auth: bool,
) -> bool:
    """
    Board-grade frontier gate:
    - must have at least one high-auth channel
    - plus either acceleration OR novelty (<= 90d)
    """
    if not has_any_high_auth:
        return False

    novelty_ok = False
    if first_seen:
        novelty_ok = (datetime.utcnow() - first_seen).days <= 90

    accel_ok = accel_ratio >= 1.5

    # If the entity is generic (LLM/API), require BOTH accel and high-auth (already true) and at least 3 channels
    if entity in GENERIC_THEME_ENTITIES:
        return accel_ok and len(channels) >= 3

    return accel_ok or novelty_ok


def frontier_score(entity: str) -> FrontierItem | None:
    entity = normalize_entity(entity)
    if not is_entity_useful(entity):
        return None

    first = _first_seen(entity)
    c90, c365, chs, has_tier1, has_tier1_high_auth, has_any_high_auth = _counts_and_flags(entity)

    if len(chs) < 2:
        return None

    accel_bonus, accel_ratio = _accel_bonus(c90, c365)

    if not _passes_frontier_gate(entity, chs, first, accel_ratio, has_any_high_auth):
        return None

    base = convergence_score(sorted(chs))
    maturity = _maturity_bonus(chs)
    novelty = _novelty_bonus(first)

    authority_bonus = 0.0
    if has_tier1_high_auth:
        authority_bonus = 2.2
    elif has_tier1:
        authority_bonus = 0.8

    score = round(base + maturity + novelty + accel_bonus + authority_bonus, 2)

    return FrontierItem(
        entity=entity,
        frontier_score=score,
        channels=sorted(chs),
        channel_count=len(chs),
        first_seen=first,
        count_90d=c90,
        count_365d=c365,
        accel_ratio=accel_ratio,
        has_tier1=has_tier1,
        has_tier1_high_auth=has_tier1_high_auth,
        has_any_high_auth=has_any_high_auth,
    )


def build_frontier_watchlist(days: int = 365, top_n: int = 20) -> List[FrontierItem]:
    """
    Candidates come from correlation engine (days window), but scoring uses 365d baseline.
    """
    from engine.correlation import compute_cross_channel_correlations

    candidates = compute_cross_channel_correlations(days=days)
    seen: Set[str] = set()
    items: List[FrontierItem] = []

    for r in candidates:
        ent = normalize_entity(r["entity"])
        if ent in seen:
            continue
        seen.add(ent)

        fi = frontier_score(ent)
        if fi:
            items.append(fi)

    items.sort(key=lambda x: x.frontier_score, reverse=True)
    return items[:top_n]


def print_frontier_watchlist(days: int = 365, top_n: int = 12, events_per_entity: int = 5) -> None:
    items = build_frontier_watchlist(days=days, top_n=top_n)
    print(f"\nFrontier Watchlist (gate: high-auth + accel(90/365) OR novelty<=90d) — top {top_n}\n")

    for it in items:
        lvl = "🔥" if it.frontier_score >= 9 else ("⚡" if it.frontier_score >= 7 else "•")
        fs = it.first_seen.strftime("%Y-%m-%d") if it.first_seen else "n/a"
        print(f"{it.entity}  | frontier={it.frontier_score} {lvl}")
        print(f"  Channels: {', '.join(it.channels)}")
        print(f"  First seen: {fs} | 90d: {it.count_90d} | 365d: {it.count_365d} | accel_ratio: {it.accel_ratio}")
        print(f"  Tier1: {it.has_tier1} | Tier1(high-auth): {it.has_tier1_high_auth}")

        # board-friendly: show last 90d events, balanced and capped per source
        evs = select_events_balanced(it.entity, days=90, limit=events_per_entity, per_source_cap=2)
        for ev in evs:
            d = ev.date.strftime("%Y-%m-%d") if ev.date else "n/a"
            print(f"  - {d} | {ev.source_name} | {ev.title}")
            if ev.url:
                print(f"    {ev.url}")
        print("")
