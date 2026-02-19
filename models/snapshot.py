from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class ThemeSnapshot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    quarter_id: str = Field(index=True)  # e.g. 2026Q1
    theme: str = Field(index=True)
    theme_score: float
    confidence_label: str
    acceleration_arrow: str
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    top_movement_ids: str  # comma-separated movement ids


class MovementSnapshot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    quarter_id: str = Field(index=True)
    movement_id: int = Field(index=True)
    theme: str = Field(index=True)
    impact_score: float
    stabilized_impact: float
    confidence_label: str
    acceleration_arrow: str
    persistence: float
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class TextSnapshot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    quarter_id: str = Field(index=True, unique=True)
    executive_summary: str
    discussion_topics: str
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
