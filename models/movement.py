from datetime import datetime
from typing import List, Optional

from sqlmodel import Field, Relationship, SQLModel


class MovementEventLink(SQLModel, table=True):
    movement_id: Optional[int] = Field(default=None, foreign_key="movement.id", primary_key=True)
    event_id: Optional[int] = Field(default=None, foreign_key="event.id", primary_key=True)


class Movement(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    movement_uid: str = Field(index=True, unique=True)  # stable id (hash of core)
    name: str
    theme: str = Field(index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow, index=True)

    # component scores 0..1
    research_momentum: float = 0.0
    capital_momentum: float = 0.0
    reg_momentum: float = 0.0
    infra_deploy: float = 0.0
    cross_adoption: float = 0.0

    impact_score: float = 0.0
    stabilized_impact: float = 0.0

    confidence_score: float = 0.0
    confidence_label: str = "Low"

    accel_raw: float = 1.0
    acceleration_arrow: str = "→"

    persistence: float = 0.0
    impact_horizon: str = "3-5 years"

    audit_json: str = "{}"  # store dict as JSON string in v1

    events: List["Event"] = Relationship(back_populates=None, link_model=MovementEventLink)  # resolved manually
