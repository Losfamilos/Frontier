from typing import Dict, List


def generate_executive_summary(themes: List[Dict], movements: List[Dict]) -> str:
    # v1 deterministic text (no LLM). You can swap to LLM later.
    top = themes[:5]
    lines = []
    lines.append("What this radar covers")
    lines.append("- Signals collected from trusted sources (regulators, infrastructure, research, and capital).")
    lines.append("- Scores reflect quantity + diversity of supporting datapoints; not opinions.")
    lines.append("")
    lines.append("What is accelerating right now (top themes)")
    for t in top:
        lines.append(
            f"- {t['theme']} (score {t['theme_score']}, {t['acceleration_arrow']}, confidence {t['confidence_label']})"
        )
    lines.append("")
    lines.append("Notes")
    lines.append("- Use drill-down to see the audit trail and the sources behind each movement.")
    return "\n".join(lines)


def generate_discussion_topics(themes: List[Dict], movements: List[Dict]) -> str:
    # 6-10 concrete questions tied to top themes
    top = themes[:5]
    qs = []
    for t in top:
        theme = t["theme"]
        qs.append(f"- For {theme}: what would we need to test in 60–90 days to learn fast?")
        qs.append(f"- For {theme}: where are we exposed if this becomes standard in 3–5 years?")
    # keep to ~10
    qs = qs[:10]
    return "ELT / Board discussion topics\n" + "\n".join(qs)
