from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Set, Tuple

from sqlmodel import select

from database import get_session
from models import Event

from engine.frontier import (
    SIGNAL_TO_CHANNEL,
    HIGH_AUTH_CHANNELS,
    _accel_bonus,
    _novelty_bonus,
)

# Theme clusters: keywords -> theme name
THEMES: Dict[str, List[str]] = {
    "LLM: Agentic execution": ["agent", "agents", "tool use", "tools", "workflow", "autonomous", "operator", "execute", "action"],
    "LLM: Security & fraud": ["prompt injection", "jailbreak", "phishing", "malware", "exploit", "vulnerability", "attack", "bias", "safety", "privacy"],
    "LLM: Governance & compliance": ["audit", "compliance", "policy", "controls", "risk", "governance", "regulatory", "model risk", "aml"],
    "LLM: Infra economics": ["throughput", "latency", "inference", "gpu", "compute", "cost", "capacity", "scaling", "provisioned"],
    "Digital money & settlement": ["settlement", "clearing", "dtcc", "token", "tokenization", "stablecoin", "cbdc", "instant payments"],
    "Identity & trust": ["identity", "kyc", "authentication", "fraud", "credential", "digital identity", "privacy-preserving"],
}

@dataclass
class ThemeItem:
    theme: str
    frontier_score: float
    channels: List[str]
    first_seen: datetime | None
    count_90d: int
    count_365d: int
    accel_ratio: float
    has_any_high_auth: bool


def _text(ev: Event) -> str:
    return f"{ev.title or ''} {ev.summary or ''}".lower()


def _channel(ev: Event) -> str:
    return SIGNAL_TO_CHANNEL.get((ev.signal_type or "").strip(), "unknown")


def _match_theme(ev: Event, keywords: List[str]) -> bool:
    t = _text(ev)
    return any(k in t for k in keywords)


def _first_seen_theme(theme: str, keywords: List[str]) -> datetime | None:
    with get_session() as session:
        events = session.exec(select(Event).order_by(Event.date.asc())).all()
    for ev in events:
        if _match_theme(ev, keywords):
            return ev.date
    return None


def _counts_theme(theme: str, keywords: List[str]) -> Tuple[int, int, Set[str], bool]:
    now = datetime.utcnow()
    cutoff_365 = now - timedelta(days=365)
    cutoff_90 = now - timedelta(days=90)

    c365 = 0
    c90 = 0
    chs: Set[str] = set()
    has_high_auth = False

    with get_session() as session:
        events = session.exec(select(Event).where(Event.date >= cutoff_365)).all()

    for ev in events:
        if not _match_theme(ev, keywords):
            continue

        c365 += 1
        if ev.date and ev.date >= cutoff_90:
            c90 += 1

        ch = _channel(ev)
        if ch != "unknown":
            chs.add(ch)
            if ch in HIGH_AUTH_CHANNELS:
                has_high_auth = True

    return c90, c365, chs, has_high_auth


def compute_theme_watchlist(top_n: int = 10) -> List[ThemeItem]:
    items: List[ThemeItem] = []
    for theme, keywords in THEMES.items():
        first = _first_seen_theme(theme, keywords)
        c90, c365, chs, has_high_auth = _counts_theme(theme, keywords)
        accel_bonus, accel_ratio = _accel_bonus(c90, c365)
        novelty = _novelty_bonus(first)

        # gate: needs >=2 channels or high-auth presence
        if len(chs) < 2 and not has_high_auth:
            continue

        # base score: acceleration + novelty + breadth
        base = 0.5 * len(chs)
        score = round(base + accel_bonus + novelty + (2.0 if has_high_auth else 0.0), 2)

        items.append(
            ThemeItem(
                theme=theme,
                frontier_score=score,
                channels=sorted(chs),
                first_seen=first,
                count_90d=c90,
                count_365d=c365,
                accel_ratio=accel_ratio,
                has_any_high_auth=has_high_auth,
            )
        )

    items.sort(key=lambda x: x.frontier_score, reverse=True)
    return items[:top_n]


def print_theme_watchlist(top_n: int = 10) -> None:
    items = compute_theme_watchlist(top_n=top_n)
    print(f"\nFrontier Theme Watchlist (90d vs 365d) — top {top_n}\n")
    for it in items:
        fs = it.first_seen.strftime("%Y-%m-%d") if it.first_seen else "n/a"
        lvl = "🔥" if it.frontier_score >= 6 else ("⚡" if it.frontier_score >= 4 else "•")
        print(f"{it.theme}  | score={it.frontier_score} {lvl}")
        print(f"  Channels: {', '.join(it.channels)}")
        print(f"  First seen: {fs} | 90d: {it.count_90d} | 365d: {it.count_365d} | accel_ratio: {it.accel_ratio}")
        print(f"  High-auth present: {it.has_any_high_auth}")
        print("")
