"""Pydantic v2 request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class ScanTextRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500_000, description="Text to scan")
    source_name: str = Field(default="inline", description="Identifier for the source")


class ProxyRequest(BaseModel):
    user_query: str = Field(..., description="The user's original query")
    document_text: str = Field(default="", description="Attached document/email text")
    source_name: str = Field(default="document", description="Source identifier")
    llm_provider: str = Field(default="openai", description="'openai' or 'anthropic'")


class FeedbackRequest(BaseModel):
    scan_id: int
    is_false_positive: bool
    note: str = Field(default="", max_length=500)


class UpdateThresholdsRequest(BaseModel):
    low_threshold: float = Field(..., ge=0.0, le=1.0)
    high_threshold: float = Field(..., ge=0.0, le=1.0)


class ToggleLayerRequest(BaseModel):
    layer: str = Field(..., description="Layer name to toggle")
    enabled: bool


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class PatternMatchSchema(BaseModel):
    pattern_id: str
    category: str
    description: str
    matched_text: str
    start: int
    end: int
    weight: float


class LayerResultSchema(BaseModel):
    layer: str
    confidence: float
    is_flagged: bool
    processing_time_ms: float
    details: dict[str, Any] = Field(default_factory=dict)


class ScanResponse(BaseModel):
    scan_id: int | None = None
    risk_score: float
    risk_level: str
    action: str
    primary_reason: str
    total_processing_time_ms: float
    layer_contributions: dict[str, float]
    layers: dict[str, Any | None]


class LogEntry(BaseModel):
    id: int
    timestamp: datetime
    source_type: str
    source_name: str
    risk_score: float
    risk_level: str
    action_taken: str
    matched_patterns: list[str]
    primary_reason: str
    layer_contributions: dict[str, float]
    raw_snippet: str
    is_false_positive: bool | None

    model_config = {"from_attributes": True}


class LogsResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[LogEntry]


class StatsResponse(BaseModel):
    total_scans: int
    blocked_count: int
    sanitized_count: int
    passed_count: int
    blocked_pct: float
    false_positive_count: int
    false_positive_rate: float
    top_patterns: list[dict[str, Any]]
    risk_distribution: dict[str, int]
    scans_over_time: list[dict[str, Any]]


class ProxyResponse(BaseModel):
    scan_id: int | None = None
    risk_score: float
    risk_level: str
    action: str
    primary_reason: str
    llm_response: str | None = None
    sanitized_text: str | None = None
    llm_error: str | None = None


class SettingsResponse(BaseModel):
    low_threshold: float
    high_threshold: float
    enabled_layers: list[str]
    layer_weights: dict[str, float]
