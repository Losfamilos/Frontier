from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple


def _as_dt(v) -> datetime | None:
    if isinstance(v, datetime):
        return v
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        except Exception:
            return None
    return None


def compute_component_scores(events: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Turn raw events into 0–100 component signals.
    We keep it simple + deterministic (board-grade explainability).
    """
    n = len(events) or 1

    # normalize signal_type buckets
    buckets = {
        "research_momentum": 0,
        "capital_momentum": 0,
        "reg_momentum": 0,
        "infra_deploy": 0,
        "cross_adoption": 0,
    }

    for e in events:
        st = (e.get("signal_type") or "").lower()
        if st in ("research", "research_standards"):
            buckets["research_momentum"] += 1
        elif st in ("capital", "capital_flows_markets", "markets"):
            buckets["capital_momentum"] += 1
        elif st in ("regulatory", "regulatory_policy", "policy"):
            buckets["reg_momentum"] += 1
        elif st in ("infra", "technology", "technology_ai_infra", "cyber", "cyber_fraud_resilience"):
            buckets["infra_deploy"] += 1
        else:
            buckets["cross_adoption"] += 1

    # convert counts -> 0..100 (share-based)
    out: Dict[str, float] = {}
    for k, c in buckets.items():
        out[k] = round(100.0 * (c / n), 2)

    return out


def compute_impact(components: Dict[str, float]) -> float:
    """
    Impact is weighted “so what” — tuned to prefer cross-signal + binding forces.
    """
    w = {
        "research_momentum": 0.20,
        "capital_momentum": 0.25,
        "reg_momentum": 0.25,
        "infra_deploy": 0.20,
        "cross_adoption": 0.10,
    }
    score = 0.0
    for k, weight in w.items():
        score += weight * float(components.get(k, 0.0))

    return round(score, 2)


def compute_confidence(
    events: List[Dict[str, Any]],
    components: Dict[str, float],
) -> Tuple[float, str, Dict[str, Any]]:
    """
    Confidence = “can we defend this in a boardroom?”
    Uses: source diversity + tier1 presence + volume.
    """
    sources = set()
    tier1 = 0
    for e in events:
        src = e.get("source_name") or ""
        if src:
            sources.add(src)
        if int(e.get("source_tier") or 3) == 1:
            tier1 += 1

    n = len(events)
    src_div = min(1.0, (len(sources) / 6.0))  # saturates at 6 unique sources
    tier1_share = (tier1 / n) if n else 0.0
    vol = min(1.0, (n / 25.0))  # saturates at 25 events

    conf = 100.0 * (0.45 * src_div + 0.40 * tier1_share + 0.15 * vol)
    conf = round(conf, 2)

    if conf >= 70:
        label = "high"
    elif conf >= 45:
        label = "medium"
    else:
        label = "low"

    meta = {
        "n_events": n,
        "unique_sources": len(sources),
        "tier1_count": tier1,
        "tier1_share": round(tier1_share, 3),
    }
    return conf, label, meta


def compute_acceleration(
    events: List[Dict[str, Any]],
    baseline90,  # BaselineCounts or (recent_90, baseline_90)
) -> Tuple[float, str, Dict[str, Any]]:
    """
    Acceleration compares last-90-days vs prior-90-days baseline (90–180d ago).
    Returns:
      - accel_raw (0..100-ish)
      - arrow: "↑" "→" "↓"
      - meta with ratio + counts
    """
    now = datetime.utcnow()
    cutoff_90 = now - timedelta(days=90)

    recent_90 = 0
    for e in events:
        d = _as_dt(e.get("date"))
        if not d:
            continue
        if d >= cutoff_90:
            recent_90 += 1

    # baseline90 can be BaselineCounts (iterable) or dict-like
    baseline_90 = 0.0
    try:
        r, b = baseline90  # __iter__
        baseline_90 = float(b)
    except Exception:
        baseline_90 = float(getattr(baseline90, "baseline_90", 0.0) or 0.0)

    ratio = (recent_90 + 1.0) / (baseline_90 + 1.0)

    if ratio >= 1.35:
        arrow = "↑"
    elif ratio <= 0.75:
        arrow = "↓"
    else:
        arrow = "→"

    # scale ratio into a bounded-ish score
    accel_raw = 50.0 + 25.0 * (ratio - 1.0)
    accel_raw = max(0.0, min(100.0, accel_raw))

    meta = {
        "recent_90": int(recent_90),
        "baseline_90": float(round(baseline_90, 2)),
        "accel_ratio": float(round(ratio, 3)),
    }
    return round(accel_raw, 2), arrow, meta


def stabilize_with_persistence(impact: float, persistence: float) -> float:
    """
    Persistence dampens one-off spikes.
    """
    p = max(0.0, min(1.0, float(persistence)))
    stabilized = (0.65 * float(impact)) + (0.35 * float(impact) * (0.5 + 0.5 * p))
    return round(stabilized, 2)


def audit_payload(
    components: Dict[str, float],
    impact: float,
    conf_meta: Dict[str, Any],
    accel_meta: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "components": components,
        "impact": float(impact),
        "confidence_meta": conf_meta,
        "acceleration_meta": accel_meta,
    }
