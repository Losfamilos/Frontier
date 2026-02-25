from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List

from sqlmodel import select

from database import get_session
from models import Event

from engine.frontier_themes import THEMES, compute_theme_watchlist
from engine.frontier import SIGNAL_TO_CHANNEL


@dataclass
class ThemeBrief:
    theme: str
    score: float
    channels: List[str]
    first_seen: datetime | None
    count_90d: int
    count_365d: int
    accel_ratio: float
    events: List[Event]
    why_now: str
    board_question: str


def _text(ev: Event) -> str:
    return f"{ev.title or ''} {ev.summary or ''}".lower()


def _match(ev: Event, keywords: List[str]) -> bool:
    t = _text(ev)
    return any(k in t for k in keywords)


def _channel(ev: Event) -> str:
    return SIGNAL_TO_CHANNEL.get((ev.signal_type or "").strip(), "unknown")


def select_theme_events(theme: str, keywords: List[str], days: int = 90, limit: int = 5, per_source_cap: int = 2) -> List[Event]:
    cutoff = datetime.utcnow() - timedelta(days=days)

    with get_session() as session:
        events = session.exec(select(Event).where(Event.date >= cutoff).order_by(Event.date.desc())).all()

    matches = [ev for ev in events if _match(ev, keywords)]

    selected: List[Event] = []
    used_sources: Dict[str, int] = {}
    used_channels: Dict[str, int] = {}

    # Prefer diversity: 1 per channel first
    for ev in matches:
        ch = _channel(ev)
        src = ev.source_name or "unknown"

        if used_channels.get(ch, 0) >= 1:
            continue
        if used_sources.get(src, 0) >= per_source_cap:
            continue

        selected.append(ev)
        used_sources[src] = used_sources.get(src, 0) + 1
        used_channels[ch] = used_channels.get(ch, 0) + 1

        if len(selected) >= limit:
            return selected

    # Fill remaining by recency with per-source cap
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


def _why_now(theme: str, accel_ratio: float, channels: List[str]) -> str:
    # simple v1 explanation
    ch_hint = []
    for c in ("regulatory_policy", "capital_flows_markets", "competitive_moves_fs", "central_banking_macro"):
        if c in channels:
            ch_hint.append(c.replace("_", " "))
    ch_str = ", ".join(ch_hint) if ch_hint else "multiple channels"

    if accel_ratio >= 2.0:
        return f"Signal density has accelerated materially (90d vs 365d). Now showing up across {ch_str}."
    if accel_ratio >= 1.5:
        return f"Signal density is rising (90d vs 365d) and appearing across {ch_str}."
    return f"Cross-channel convergence across {ch_str} suggests a transition is forming."


def _board_question(theme: str) -> str:
    mapping = {
        "LLM: Governance & compliance": "Where would AI governance become binding (controls, audit, model risk) in our value chain within 6–18 months, and what must be true for us to be ahead?",
        "LLM: Agentic execution": "Which workflows could be safely delegated to agents first (payments, servicing, ops), and what is the minimum control layer to stay audit-ready?",
        "LLM: Infra economics": "What is our unit cost of intelligence (inference/throughput), and where does infra economics change build-vs-buy decisions?",
        "LLM: Security & fraud": "Which fraud and security failure-modes become dominant with agentic systems, and how do we harden identity + controls accordingly?",
        "Digital money & settlement": "Where would settlement/time-to-finality create a step-change in our products or risk, and what capabilities must we build now?",
        "Identity & trust": "Which identity primitives (KYC, credentials, authentication) become a platform dependency, and what do we need to control vs partner?",
    }
    return mapping.get(theme, "What would have to be true for this transition to create a step-change in our business, and what is our earliest action?")


def build_theme_briefs(top_n: int = 8, events_per_theme: int = 5) -> List[ThemeBrief]:
    watch = compute_theme_watchlist(top_n=top_n)
    briefs: List[ThemeBrief] = []

    for it in watch:
        keywords = THEMES.get(it.theme, [])
        evs = select_theme_events(it.theme, keywords, days=90, limit=events_per_theme, per_source_cap=2)
        briefs.append(
            ThemeBrief(
                theme=it.theme,
                score=it.frontier_score,
                channels=it.channels,
                first_seen=it.first_seen,
                count_90d=it.count_90d,
                count_365d=it.count_365d,
                accel_ratio=it.accel_ratio,
                events=evs,
                why_now=_why_now(it.theme, it.accel_ratio, it.channels),
                board_question=_board_question(it.theme),
            )
        )

    return briefs


def print_theme_briefs(top_n: int = 8, events_per_theme: int = 5) -> None:
    briefs = build_theme_briefs(top_n=top_n, events_per_theme=events_per_theme)
    print(f"\nFrontier Theme Briefs — top {top_n}\n")

    for b in briefs:
        fs = b.first_seen.strftime("%Y-%m-%d") if b.first_seen else "n/a"
        lvl = "🔥" if b.score >= 6 else ("⚡" if b.score >= 4 else "•")
        print(f"{b.theme}  | score={b.score} {lvl}")
        print(f"  Why now: {b.why_now}")
        print(f"  Channels: {', '.join(b.channels)}")
        print(f"  First seen: {fs} | 90d: {b.count_90d} | 365d: {b.count_365d} | accel_ratio: {b.accel_ratio}")
        print(f"  Board question: {b.board_question}")
        if b.events:
            print("  Evidence:")
            for ev in b.events:
                d = ev.date.strftime("%Y-%m-%d") if ev.date else "n/a"
                print(f"  - {d} | {ev.source_name} | {ev.title}")
                if ev.url:
                    print(f"    {ev.url}")
        print("")
