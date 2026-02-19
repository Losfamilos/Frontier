import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

from config import settings


def _log_norm(n: int, max_n: int = 20) -> float:
    # 0..1
    return min(1.0, math.log(1 + n) / math.log(1 + max_n))


def compute_component_scores(events: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    events: list of dict with keys: signal_type, source_tier, date (datetime)
    returns A..E in 0..1 (simple v1 heuristics)
    """
    # Count per signal type, tier-boost for Tier 1
    counts = {k: 0 for k in ["research", "capital", "regulatory", "infra", "cross"]}
    tier1_bonus = {k: 0 for k in counts}
    for e in events:
        st = e["signal_type"]
        counts[st] += 1
        if int(e.get("source_tier", 3)) == 1:
            tier1_bonus[st] += 1

    # Simple saturation curves
    def sat(c):
        return 1 - math.exp(-c / 4.0)  # quickly saturate

    A = min(1.0, sat(counts["research"]) + 0.10 * sat(tier1_bonus["research"]))
    B = min(1.0, sat(counts["capital"]) + 0.15 * sat(tier1_bonus["capital"]))
    C = min(1.0, sat(counts["regulatory"]) + 0.20 * sat(tier1_bonus["regulatory"]))
    D = min(1.0, sat(counts["infra"]) + 0.20 * sat(tier1_bonus["infra"]))
    E = min(1.0, sat(counts["cross"]) + 0.10 * sat(tier1_bonus["cross"]))

    return {
        "research_momentum": A,
        "capital_momentum": B,
        "reg_momentum": C,
        "infra_deploy": D,
        "cross_adoption": E,
    }


def compute_impact(components: Dict[str, float]) -> float:
    A = components["research_momentum"]
    B = components["capital_momentum"]
    C = components["reg_momentum"]
    D = components["infra_deploy"]
    E = components["cross_adoption"]
    impact = 100.0 * (
        settings.w_research * A
        + settings.w_capital * B
        + settings.w_regulatory * C
        + settings.w_infra * D
        + settings.w_cross * E
    )
    return round(impact, 2)


def compute_confidence(events: List[Dict[str, Any]], components: Dict[str, float]) -> Tuple[float, str, Dict[str, Any]]:
    n_sources = len({e["url"] for e in events if e.get("url")})
    breadth = _log_norm(n_sources, 20)
    diversity = sum(1 for k in components.values() if k > 0.2) / 5.0
    confidence = 0.6 * breadth + 0.4 * diversity
    if confidence >= 0.70:
        label = "High"
    elif confidence >= 0.45:
        label = "Medium"
    else:
        label = "Low"
    return round(confidence, 3), label, {"n_sources": n_sources, "breadth": breadth, "diversity": diversity}


def compute_acceleration(events: List[Dict[str, Any]], baseline_counts: Dict[str, float]) -> Tuple[float, str, Dict[str, Any]]:
    """
    baseline_counts: avg count per 90d for each signal_type (from last 12m)
    """
    now = datetime.now(timezone.utc)
    cutoff_90 = now - timedelta(days=90)

    last90 = {k: 0 for k in baseline_counts}
    for e in events:
        if e["date"].astimezone(timezone.utc) >= cutoff_90:
            last90[e["signal_type"]] += 1

    ratios = []
    ratio_detail = {}
    for k in baseline_counts:
        r = (last90[k] + 1.0) / (baseline_counts[k] + 1.0)
        ratios.append(r)
        ratio_detail[k] = {"last90": last90[k], "baseline90": baseline_counts[k], "ratio": round(r, 3)}

    ratios_sorted = sorted(ratios)
    median = ratios_sorted[len(ratios_sorted) // 2]
    if median >= 2.0:
        arrow = "↑↑"
    elif median >= 1.3:
        arrow = "↑"
    elif median >= 0.8:
        arrow = "→"
    else:
        arrow = "↓"
    return round(median, 3), arrow, ratio_detail


def stabilize_with_persistence(impact: float, persistence: float) -> float:
    # max +15% lift
    stabilized = impact * (0.85 + 0.15 * persistence)
    return round(stabilized, 2)


def compute_persistence(movement_history_impacts: List[float], threshold: float = 50.0, window_quarters: int = 4) -> float:
    # fraction of quarters in last window where impact >= threshold
    if not movement_history_impacts:
        return 0.0
    last = movement_history_impacts[-window_quarters:]
    hits = sum(1 for x in last if x >= threshold)
    return round(hits / float(window_quarters), 3)


def audit_payload(components, impact, conf_meta, accel_meta) -> Dict[str, Any]:
    return {
        "weighting": {
            "research": settings.w_research,
            "capital": settings.w_capital,
            "regulatory": settings.w_regulatory,
            "infra": settings.w_infra,
            "cross": settings.w_cross,
        },
        "components": components,
        "impact": impact,
        "confidence_meta": conf_meta,
        "acceleration_meta": accel_meta,
    }
