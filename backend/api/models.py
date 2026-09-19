"""SQLAlchemy ORM models."""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from api.database import Base


class ScanLog(Base):
    __tablename__ = "scan_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    source_type: Mapped[str] = mapped_column(String(32), default="text")  # text | pdf | docx | html | url
    source_name: Mapped[str] = mapped_column(String(256), default="")
    risk_score: Mapped[float] = mapped_column(Float, index=True)
    risk_level: Mapped[str] = mapped_column(String(8), index=True)   # LOW | MEDIUM | HIGH
    action_taken: Mapped[str] = mapped_column(String(16))             # PASS_THROUGH | SANITIZE | BLOCK
    matched_patterns: Mapped[str] = mapped_column(Text, default="[]") # JSON list of pattern IDs
    primary_reason: Mapped[str] = mapped_column(Text, default="")
    layer_contributions: Mapped[str] = mapped_column(Text, default="{}") # JSON dict
    raw_snippet: Mapped[str] = mapped_column(Text, default="")        # First 500 chars
    is_false_positive: Mapped[bool | None] = mapped_column(default=None)  # None = unreviewed
    feedback_note: Mapped[str] = mapped_column(Text, default="")

    def matched_patterns_list(self) -> list[str]:
        try:
            return json.loads(self.matched_patterns)
        except (json.JSONDecodeError, TypeError):
            return []

    def layer_contributions_dict(self) -> dict[str, float]:
        try:
            return json.loads(self.layer_contributions)
        except (json.JSONDecodeError, TypeError):
            return {}
