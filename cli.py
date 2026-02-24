import argparse
import json
from datetime import datetime

from sqlmodel import select


def register_default_connectors():
    """
    Keep this idempotent-ish: if registry already has connectors, don't double register.
    """
    from connectors.registry import list_connectors

    if list_connectors():
        return

    from connectors.arxiv import fetch_arxiv
    from connectors.registry import ConnectorSpec, register
    from connectors.rss import fetch_rss

    register(
        ConnectorSpec(
            name="arxiv_fininfra",
            source_name="arXiv",
            source_tier=3,
            signal_type="research",
            fetch=lambda days=365: fetch_arxiv(
                query='all:"tokenized deposits" OR all:"post-quantum cryptography" OR all:"zero-knowledge" OR all:"MPC" OR all:"settlement" OR all:"collateral" OR all:"fully homomorphic encryption"',
                days=days,
                max_results=80,
            ),
        )
    )

    register(
        ConnectorSpec(
            name="ecb_rss",
            source_name="ECB",
            source_tier=1,
            signal_type="regulatory",
            fetch=lambda days=365: fetch_rss("https://www.ecb.europa.eu/rss/press.html", days=days),
        )
    )
    register(
        ConnectorSpec(
            name="bis_rss",
            source_name="BIS",
            source_tier=1,
            signal_type="regulatory",
            fetch=lambda days=365: fetch_rss("https://www.bis.org/doclist/rss.htm", days=days),
        )
    )
    register(
        ConnectorSpec(
            name="swift_rss",
            source_name="SWIFT",
            source_tier=1,
            signal_type="infra",
            fetch=lambda days=365: fetch_rss("https://www.swift.com/rss.xml", days=days),
        )
    )
    register(
        ConnectorSpec(
            name="a16z_rss",
            source_name="a16z",
            source_tier=2,
            signal_type="capital",
            fetch=lambda days=365: fetch_rss("https://a16z.com/feed/", days=days),
        )
    )


def movement_history_impacts(movement_id: int):
    from database import get_session
    from models import MovementSnapshot

    with get_session() as session:
        snaps = session.exec(
            select(MovementSnapshot)
            .where(MovementSnapshot.movement_id == movement_id)
            .order_by(MovementSnapshot.created_at)
        ).all()
        return [s.impact_score for s in snaps]


def build(days: int = 365, cluster_threshold: float = 0.55):
    from database import get_session
    from engine.baseline import baseline_counts_90d_for_movement
    from engine.cluster import build_movements
    from engine.score import (
        audit_payload,
        compute_acceleration,
        compute_component_scores,
        compute_confidence,
        compute_impact,
        stabilize_with_persistence,
    )
    from engine.summary import generate_discussion_topics, generate_executive_summary
    from engine.themes import aggregate_themes
    from models import Event, Movement

    # 1) cluster events -> movements (creates/updates Movement + MovementEventLink)
    n = build_movements(days=days, distance_threshold=cluster_threshold)

    # 2) compute scoring per movement
    with get_session() as session:
        movements = session.exec(select(Movement)).all()

        for m in movements:
            # If you later wire ORM relationship, you can replace this with m.events
            # For now, pull events via join on MovementEventLink
            from models import MovementEventLink

            links = session.exec(select(MovementEventLink).where(MovementEventLink.movement_id == m.id)).all()
            ev_ids = [l.event_id for l in links if l.event_id is not None]
            if not ev_ids:
                continue

            evs = session.exec(select(Event).where(Event.id.in_(ev_ids))).all()
            if not evs:
                continue

            ev_dicts = [
                {
                    "signal_type": e.signal_type,
                    "source_tier": e.source_tier,
                    "date": e.date,
                    "url": e.url,
                }
                for e in evs
            ]

            components = compute_component_scores(ev_dicts)
            impact = compute_impact(components)
            conf_score, conf_label, conf_meta = compute_confidence(ev_dicts, components)

            # ✅ Correct baseline: historical window excluding last 90 days
            baseline90 = baseline_counts_90d_for_movement(session, m.id)
            accel_raw, arrow, accel_meta = compute_acceleration(ev_dicts, baseline90)

            history = movement_history_impacts(m.id)
            if history:
                hits = sum(1 for x in history[-4:] if x >= 50.0)
                persistence = hits / 4.0
            else:
                persistence = 0.0

            stabilized = stabilize_with_persistence(impact, persistence)

            m.research_momentum = components["research_momentum"]
            m.capital_momentum = components["capital_momentum"]
            m.reg_momentum = components["reg_momentum"]
            m.infra_deploy = components["infra_deploy"]
            m.cross_adoption = components["cross_adoption"]
            m.impact_score = impact
            m.stabilized_impact = stabilized
            m.confidence_score = conf_score
            m.confidence_label = conf_label
            m.accel_raw = accel_raw
            m.acceleration_arrow = arrow
            m.persistence = round(persistence, 3)
            m.updated_at = datetime.utcnow()

            audit = audit_payload(components, impact, conf_meta, accel_meta)
            audit["movement_event_count"] = len(evs)
            # source_name might not be present on Event; guard it
            audit["tier1_sources"] = len({getattr(e, "source_name", None) for e in evs if e.source_tier == 1})
            m.audit_json = json.dumps(audit)

            session.add(m)

        session.commit()

    # 3) themes + summaries
    from database import get_session

    with get_session() as session:
        movements = session.exec(select(Movement)).all()
        m_dicts = [
            {
                "id": m.id,
                "theme": m.theme,
                "stabilized_impact": m.stabilized_impact,
                "confidence_score": m.confidence_score,
                "confidence_label": m.confidence_label,
                "acceleration_arrow": m.acceleration_arrow,
            }
            for m in movements
        ]

    themes = aggregate_themes(m_dicts)
    exec_sum = generate_executive_summary(themes, m_dicts)
    discuss = generate_discussion_topics(themes, m_dicts)

    return {
        "movements_built": n,
        "themes": themes,
        "executive_summary": exec_sum,
        "discussion_topics": discuss,
    }


def snapshot():
    from database import get_session
    from engine.snapshot import create_snapshot
    from engine.summary import generate_discussion_topics, generate_executive_summary
    from engine.themes import aggregate_themes
    from models import Movement

    with get_session() as session:
        movements = session.exec(select(Movement)).all()
        m_dicts = [
            {
                "id": m.id,
                "theme": m.theme,
                "stabilized_impact": m.stabilized_impact,
                "confidence_score": m.confidence_score,
                "confidence_label": m.confidence_label,
                "acceleration_arrow": m.acceleration_arrow,
            }
            for m in movements
        ]

    themes = aggregate_themes(m_dicts)
    exec_sum = generate_executive_summary(themes, m_dicts)
    discuss = generate_discussion_topics(themes, m_dicts)

    qid = create_snapshot(themes, exec_sum, discuss)
    return qid


def main():
    parser = argparse.ArgumentParser(prog="frontier_radar")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db")

    p_ing = sub.add_parser("ingest")
    p_ing.add_argument("--days", type=int, default=365)

    p_build = sub.add_parser("build")
    p_build.add_argument("--days", type=int, default=365)
    p_build.add_argument("--cluster-threshold", type=float, default=0.55)

    sub.add_parser("snapshot")

    p_serve = sub.add_parser("serve")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)

    args = parser.parse_args()

    # Ensure connectors exist for ingest
    register_default_connectors()

    if args.cmd == "init-db":
        from database import create_db_and_tables

        create_db_and_tables()
        print("DB initialized.")
        return

    if args.cmd == "ingest":
        from connectors.registry import list_connectors
        from engine.ingest import ingest_from_connectors

        inserted = ingest_from_connectors(list_connectors(), days=args.days)
        print(f"Ingested {inserted} new events.")
        return

    if args.cmd == "build":
        result = build(days=args.days, cluster_threshold=args.cluster_threshold)
        print(f"Built movements: {result['movements_built']}")
        print(f"Top themes: {[t['theme'] for t in result['themes'][:5]]}")
        return

    if args.cmd == "snapshot":
        qid = snapshot()
        print(f"Snapshot created: {qid}")
        return

    if args.cmd == "serve":
        try:
            import uvicorn  # type: ignore
        except Exception:
            raise SystemExit("Missing dependency: uvicorn. Install with: pip install uvicorn")

        try:
            from radar_app import app  # expects FastAPI app in radar_app.py
        except Exception:
            raise SystemExit("radar_app.py with FastAPI `app` not found (or import failed).")

        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
        return


if __name__ == "__main__":
    main()
