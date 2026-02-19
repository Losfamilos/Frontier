from datetime import datetime
from typing import List, Optional

from sqlmodel import Field, Relationship, SQLModel


class EventSourceRef(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    event_id: int = Field(foreign_key="event.id", index=True)
    source_name: str
    source_tier: int
    url: str


class Event(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    event_uid: str = Field(index=True, unique=True)  # stable id (hash)
    date: datetime = Field(index=True)
    source_name: str = Field(index=True)
    source_tier: int = Field(index=True)
    signal_type: str = Field(index=True)  # research|capital|regulatory|infra|cross
    title: str
    summary: str
    url: str
    raw_text: Optional[str] = None

    entities: Optional[str] = None  # comma-separated for v1
    theme_hint: Optional[str] = None  # one of themes (hint)
    embedding: Optional[str] = None  # store as JSON string (v1)

    source_refs: List[EventSourceRef] = Relationship()
