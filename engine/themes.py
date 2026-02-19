from collections import defaultdict
from typing import Any, Dict, List


def aggregate_themes(movements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_theme = defaultdict(list)
    for m in movements:
        by_theme[m["theme"]].append(m)

    out = []
    for theme, ms in by_theme.items():
        ms_sorted = sorted(ms, key=lambda x: x["stabilized_impact"], reverse=True)
        top3 = ms_sorted[:3]
        next7 = ms_sorted[3:10]

        def avg(xs):
            if not xs:
                return 0.0
            return sum(x["stabilized_impact"] for x in xs) / len(xs)

        theme_score = 0.6 * avg(top3) + 0.4 * avg(next7)

        # Confidence weighted average of top5
        top5 = ms_sorted[:5]
        if top5:
            wsum = sum(x["stabilized_impact"] for x in top5)
            c = sum(x["confidence_score"] * x["stabilized_impact"] for x in top5) / (wsum if wsum else 1)
        else:
            c = 0.0

        if c >= 0.70:
            conf_label = "High"
        elif c >= 0.45:
            conf_label = "Medium"
        else:
            conf_label = "Low"

        # acceleration = most common among top5 (deterministic tie-break)
        arrows = [x["acceleration_arrow"] for x in top5] or ["→"]
        counts = {a: arrows.count(a) for a in set(arrows)}
        arrow_order = ["↑↑", "↑", "→", "↓"]
        arrow = sorted(counts.items(), key=lambda item: (-item[1], arrow_order.index(item[0])))[0][0]

        out.append(
            {
                "theme": theme,
                "theme_score": round(theme_score, 2),
                "confidence_label": conf_label,
                "acceleration_arrow": arrow,
                "top_movements": [x["id"] for x in ms_sorted[:10]],
            }
        )

    out.sort(key=lambda x: x["theme_score"], reverse=True)
    return out
