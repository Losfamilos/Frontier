from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()

THEMES = [
    "Money & Deposit Architecture",
    "Market Infrastructure & Settlement",
    "Core Banking Architecture",
    "Wealth & Asset Servicing",
    "Balance Sheet & Risk Architecture",
    "Identity, Privacy & Cryptography",
    "Autonomous & Agentic Systems",
    "Regulatory & Monetary Shifts",
]

SIGNAL_TYPES = ["research", "capital", "regulatory", "infra", "cross"]


class Settings(BaseModel):
    app_name: str = "Nordic Banking Frontier Radar"
    db_url: str = os.getenv("FR_DB_URL", "sqlite:///./frontier_radar.db")
    embed_model: str = os.getenv("FR_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

    # Scheduler
    enable_scheduler: bool = os.getenv("FR_SCHEDULER", "true").lower() == "true"
    daily_ingest_hour: int = int(os.getenv("FR_DAILY_INGEST_HOUR", "3"))   # local time
    daily_ingest_minute: int = int(os.getenv("FR_DAILY_INGEST_MINUTE", "0"))
    daily_build_hour: int = int(os.getenv("FR_DAILY_BUILD_HOUR", "3"))
    daily_build_minute: int = int(os.getenv("FR_DAILY_BUILD_MINUTE", "30"))

    # Snapshot cadence (quarterly “freeze”)
    snapshot_days: int = int(os.getenv("FR_SNAPSHOT_DAYS", "90"))

    # Scoring weights (fixed v1)
    w_research: float = 0.15
    w_capital: float = 0.25
    w_regulatory: float = 0.25
    w_infra: float = 0.25
    w_cross: float = 0.10


settings = Settings()
