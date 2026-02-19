import hashlib
from datetime import datetime, timedelta, timezone
from typing import Dict, List

import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sqlmodel import delete, select

from database import get_session
from engine.embed import embed_texts
from models import Event, Movement, MovementEventLink


def cluster_embeddings(embeddings: np.ndarray, distance_threshold: float = 0.55) -> List[int]:
    if len(embeddings) <= 1:
        return [0] * len(embeddings)

    model = AgglomerativeClustering(
        n_clusters=None,
        metric="cosine",
        linkage="average",
        distance_threshold=distance_threshold,
    )
    labels = model.fit_predict(embeddings)
    return labels.tolist()


def movement_uid_from_event_uids(event_uids: List[str]) -> str:
    core = "|".join(sorted(event_uids)[:10])
    return hashlib.sha256(core.encode("utf-8")).hexdigest()[:24]


def simple_theme_hint(text: str) -> str:
    t = text.lower()
    if any(x in t for x in ["deposit", "stablecoin", "cbdc", "tokenized deposit", "programmable money"]):
        return "Money & Deposit Architecture"
    if any(x in t for x in ["settlement", "clearing", "dtcc", "euroclear", "collateral", "repo"]):
        return "Market Infrastructure & Settlement"
    if any(x in t for x in ["core banking", "ledger", "banking platform", "mainframe", "modernization"]):
        return "Core Banking Architecture"
    if any(x in t for x in ["wealth", "custody", "asset servicing", "private markets", "tokenization of funds"]):
        return "Wealth & Asset Servicing"
    if any(x in t for x in ["capital", "liquidity", "risk model", "credit", "stress test"]):
        return "Balance Sheet & Risk Architecture"
    if any(x in t for x in ["zero-knowledge", "zkp", "mpc", "homomorphic", "post-quantum", "pqc", "privacy"]):
        return "Identity, Privacy & Cryptography"
    if any(x in t for x in ["agent", "autonomous", "agentic", "multi-agent"]):
        return "Autonomous & Agentic Systems"
    if any(x in t for x in ["regulation", "consultation", "ecb", "bis", "eba", "mas", "framework", "guidance"]):
        return "Regulatory & Monetary Shifts"
    return "Regulatory & Monetary Shifts"


def build_movements(days: int = 365, distance_threshold: float = 0.55) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    with get_session() as session:
        events = session.exec(select(Event).where(Event.date >= cutoff)).all()

    if not events:
        return 0

    texts = [f"{e.title}\n{e.summary}" for e in events]
    emb = embed_texts(texts)
    labels = cluster_embeddings(emb, distance_threshold=distance_threshold)

    clusters: Dict[int, List[int]] = {}
    for idx, lab in enumerate(labels):
        clusters.setdefault(lab, []).append(idx)

    created = 0
    with get_session() as session:
        session.exec(delete(MovementEventLink))
        session.exec(delete(Movement))
        session.commit()

        for lab, idxs in clusters.items():
            evs = [events[i] for i in idxs]
            ev_uids = [e.event_uid for e in evs]
            uid = movement_uid_from_event_uids(ev_uids)

            evs_sorted = sorted(evs, key=lambda x: x.date, reverse=True)
            name = evs_sorted[0].title[:120] if evs_sorted else f"Movement {lab}"
            theme = simple_theme_hint(" ".join([e.title for e in evs_sorted[:5]]))

            m = Movement(
                movement_uid=uid,
                name=name,
                theme=theme,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                audit_json="{}",
            )
            session.add(m)
            session.commit()
            session.refresh(m)

            for e in evs:
                session.add(MovementEventLink(movement_id=m.id, event_id=e.id))
            session.commit()
            created += 1

    return created
