"""
FastAPI main application — the prompt injection firewall proxy.

Endpoints:
  POST /scan         — scan text without forwarding to LLM
  POST /scan/file    — scan uploaded file (PDF/DOCX/HTML/TXT)
  POST /proxy        — scan + sanitize + forward to downstream LLM
  GET  /logs         — paginated scan history
  GET  /stats        — aggregate statistics
  POST /feedback     — mark a scan as false positive
  GET  /settings     — get current detection settings
  PUT  /settings/thresholds — update risk thresholds
  PUT  /settings/layers     — toggle individual detection layers
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, text
from sqlalchemy.orm import Session

# --- Path setup so backend modules are importable ---
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.database import engine, get_db, init_db
from api.models import ScanLog
from api.schemas import (
    FeedbackRequest,
    LogEntry,
    LogsResponse,
    ProxyRequest,
    ProxyResponse,
    ScanResponse,
    ScanTextRequest,
    SettingsResponse,
    StatsResponse,
    ToggleLayerRequest,
    UpdateThresholdsRequest,
)
from detection.orchestrator import DetectionOrchestrator, OrchestratorConfig
from sanitize.isolator import Isolator
from sanitize.neutralizer import Neutralizer

# ---------------------------------------------------------------------------
# App lifecycle — init components on startup
# ---------------------------------------------------------------------------

_orchestrator: DetectionOrchestrator | None = None
_neutralizer = Neutralizer()
_isolator = Isolator()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _orchestrator
    init_db()
    _orchestrator = DetectionOrchestrator()
    yield


app = FastAPI(
    title="LLM Prompt Injection Firewall",
    description=(
        "A production-grade proxy that detects and neutralizes prompt injection "
        "attacks before content reaches your LLM.  Multi-layer detection engine "
        "combining rules, structural analysis, statistical heuristics, and ML."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_orchestrator() -> DetectionOrchestrator:
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Detection engine not ready")
    return _orchestrator


# ---------------------------------------------------------------------------
# Helper: extract text from uploaded files
# ---------------------------------------------------------------------------

async def _extract_text(file: UploadFile) -> tuple[str, str]:
    """Returns (text, source_type)."""
    content = await file.read()
    filename = file.filename or ""
    ext = Path(filename).suffix.lower()

    if ext == ".pdf":
        try:
            import fitz  # type: ignore
            doc = fitz.open(stream=content, filetype="pdf")
            text = "\n".join(page.get_text() for page in doc)
            return text, "pdf"
        except Exception:
            pass

    if ext in (".docx", ".doc"):
        try:
            import io
            from docx import Document  # type: ignore
            doc = Document(io.BytesIO(content))
            text = "\n".join(p.text for p in doc.paragraphs)
            return text, "docx"
        except Exception:
            pass

    if ext in (".html", ".htm"):
        try:
            from bs4 import BeautifulSoup  # type: ignore
            soup = BeautifulSoup(content, "lxml")
            text = soup.get_text(separator="\n")
            return text, "html"
        except Exception:
            pass

    # Fallback: treat as plain text
    return content.decode("utf-8", errors="replace"), "text"


# ---------------------------------------------------------------------------
# Helper: persist scan log to SQLite
# ---------------------------------------------------------------------------

def _log_scan(db: Session, report, source_type: str, source_name: str, snippet: str) -> ScanLog:
    matched_ids: list[str] = []
    if report.pattern_result:
        matched_ids = [m.pattern_id for m in report.pattern_result.matched_patterns]

    log = ScanLog(
        source_type=source_type,
        source_name=source_name,
        risk_score=report.risk_score,
        risk_level=report.risk_level.value,
        action_taken=report.action.value,
        matched_patterns=json.dumps(list(set(matched_ids))),
        primary_reason=report.primary_reason,
        layer_contributions=json.dumps(report.layer_contributions),
        raw_snippet=snippet[:500],
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


# ---------------------------------------------------------------------------
# POST /scan — text analysis
# ---------------------------------------------------------------------------

@app.post("/scan", response_model=ScanResponse, tags=["Detection"])
async def scan_text(
    request: ScanTextRequest,
    db: Session = Depends(get_db),
    orch: DetectionOrchestrator = Depends(get_orchestrator),
):
    """
    Scan raw text through the full detection pipeline.
    Returns a detailed risk report without forwarding to any LLM.
    """
    report = orch.scan(request.text)
    log = _log_scan(db, report, "text", request.source_name, request.text)
    return ScanResponse(
        scan_id=log.id,
        risk_score=report.risk_score,
        risk_level=report.risk_level.value,
        action=report.action.value,
        primary_reason=report.primary_reason,
        total_processing_time_ms=report.total_processing_time_ms,
        layer_contributions=report.layer_contributions,
        layers=report.to_dict()["layers"],
    )


# ---------------------------------------------------------------------------
# POST /scan/file — file upload analysis
# ---------------------------------------------------------------------------

@app.post("/scan/file", response_model=ScanResponse, tags=["Detection"])
async def scan_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    orch: DetectionOrchestrator = Depends(get_orchestrator),
):
    """
    Upload a PDF, DOCX, HTML, or TXT file for injection scanning.
    """
    text, source_type = await _extract_text(file)
    if not text.strip():
        raise HTTPException(status_code=400, detail="Could not extract text from file")

    report = orch.scan(text)
    log = _log_scan(db, report, source_type, file.filename or "upload", text)
    return ScanResponse(
        scan_id=log.id,
        risk_score=report.risk_score,
        risk_level=report.risk_level.value,
        action=report.action.value,
        primary_reason=report.primary_reason,
        total_processing_time_ms=report.total_processing_time_ms,
        layer_contributions=report.layer_contributions,
        layers=report.to_dict()["layers"],
    )


# ---------------------------------------------------------------------------
# POST /proxy — scan + sanitize + forward to LLM
# ---------------------------------------------------------------------------

@app.post("/proxy", response_model=ProxyResponse, tags=["Proxy"])
async def proxy_to_llm(
    request: ProxyRequest,
    db: Session = Depends(get_db),
    orch: DetectionOrchestrator = Depends(get_orchestrator),
):
    """
    Full pipeline: scan document, sanitize, wrap in security framing,
    then forward to the configured downstream LLM.
    """
    combined_text = f"{request.user_query}\n\n{request.document_text}".strip()
    report = orch.scan(combined_text)
    log = _log_scan(db, report, "proxy", request.source_name, combined_text)

    # --- BLOCK: don't forward ---
    if report.action.value == "BLOCK":
        return ProxyResponse(
            scan_id=log.id,
            risk_score=report.risk_score,
            risk_level=report.risk_level.value,
            action=report.action.value,
            primary_reason=report.primary_reason,
            llm_response=None,
            sanitized_text=None,
        )

    # --- SANITIZE or PASS_THROUGH: build safe prompt ---
    neutralized = _neutralizer.neutralize(combined_text, report)
    isolated = _isolator.isolate(
        neutralized.neutralized_text,
        report,
        user_query=request.user_query,
        source_name=request.source_name,
    )

    # --- Forward to LLM ---
    llm_response = None
    llm_error = None

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if api_key:
        try:
            llm_response = await _call_llm(
                isolated.full_prompt,
                request.llm_provider,
            )
        except Exception as exc:
            llm_error = str(exc)
    else:
        llm_error = "No LLM API key configured (set OPENAI_API_KEY or ANTHROPIC_API_KEY)"

    return ProxyResponse(
        scan_id=log.id,
        risk_score=report.risk_score,
        risk_level=report.risk_level.value,
        action=report.action.value,
        primary_reason=report.primary_reason,
        llm_response=llm_response,
        sanitized_text=isolated.full_prompt if not llm_response else None,
        llm_error=llm_error,
    )


async def _call_llm(prompt: str, provider: str) -> str:
    """Call the downstream LLM API."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        if provider == "anthropic":
            api_key = os.getenv("ANTHROPIC_API_KEY", "")
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307"),
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            return resp.json()["content"][0]["text"]
        else:  # openai-compatible
            api_key = os.getenv("OPENAI_API_KEY", "")
            base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": os.getenv("OPENAI_MODEL", "gpt-3.5-turbo"),
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1024,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# GET /logs — paginated scan history
# ---------------------------------------------------------------------------

@app.get("/logs", response_model=LogsResponse, tags=["Monitoring"])
def get_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    risk_level: str | None = Query(None, description="Filter by LOW/MEDIUM/HIGH"),
    db: Session = Depends(get_db),
):
    """Paginated list of all scan attempts with risk scores."""
    q = db.query(ScanLog).order_by(ScanLog.timestamp.desc())
    if risk_level:
        q = q.filter(ScanLog.risk_level == risk_level.upper())
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()

    return LogsResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[
            LogEntry(
                id=item.id,
                timestamp=item.timestamp,
                source_type=item.source_type,
                source_name=item.source_name,
                risk_score=item.risk_score,
                risk_level=item.risk_level,
                action_taken=item.action_taken,
                matched_patterns=item.matched_patterns_list(),
                primary_reason=item.primary_reason,
                layer_contributions=item.layer_contributions_dict(),
                raw_snippet=item.raw_snippet,
                is_false_positive=item.is_false_positive,
            )
            for item in items
        ],
    )


# ---------------------------------------------------------------------------
# GET /stats — aggregate statistics
# ---------------------------------------------------------------------------

@app.get("/stats", response_model=StatsResponse, tags=["Monitoring"])
def get_stats(
    days: int = Query(30, ge=1, le=365, description="Lookback period in days"),
    db: Session = Depends(get_db),
):
    """Aggregate statistics for dashboard analytics."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
    logs = db.query(ScanLog).filter(ScanLog.timestamp >= cutoff).all()

    total = len(logs)
    blocked = sum(1 for l in logs if l.action_taken == "BLOCK")
    sanitized = sum(1 for l in logs if l.action_taken == "SANITIZE")
    passed = sum(1 for l in logs if l.action_taken == "PASS_THROUGH")
    fp_count = sum(1 for l in logs if l.is_false_positive is True)

    # Top attack patterns
    pattern_counter: Counter = Counter()
    for log in logs:
        for p in log.matched_patterns_list():
            pattern_counter[p] += 1
    top_patterns = [
        {"pattern_id": pid, "count": cnt}
        for pid, cnt in pattern_counter.most_common(10)
    ]

    # Risk distribution
    risk_dist = Counter(l.risk_level for l in logs)

    # Scans over time (daily buckets)
    from collections import defaultdict
    daily: dict[str, int] = defaultdict(int)
    for log in logs:
        ts = log.timestamp
        if ts:
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            day = ts.strftime("%Y-%m-%d")
            daily[day] += 1

    scans_over_time = [
        {"date": d, "count": c} for d, c in sorted(daily.items())
    ]

    return StatsResponse(
        total_scans=total,
        blocked_count=blocked,
        sanitized_count=sanitized,
        passed_count=passed,
        blocked_pct=round(blocked / max(total, 1) * 100, 1),
        false_positive_count=fp_count,
        false_positive_rate=round(fp_count / max(blocked + sanitized, 1) * 100, 1),
        top_patterns=top_patterns,
        risk_distribution=dict(risk_dist),
        scans_over_time=scans_over_time,
    )


# ---------------------------------------------------------------------------
# POST /feedback — mark scan as false positive
# ---------------------------------------------------------------------------

@app.post("/feedback", tags=["Monitoring"])
def submit_feedback(
    request: FeedbackRequest,
    db: Session = Depends(get_db),
):
    """Mark a flagged scan as a false positive for continuous tuning."""
    log = db.query(ScanLog).filter(ScanLog.id == request.scan_id).first()
    if not log:
        raise HTTPException(status_code=404, detail=f"Scan ID {request.scan_id} not found")
    log.is_false_positive = request.is_false_positive
    log.feedback_note = request.note
    db.commit()
    return {"message": "Feedback recorded", "scan_id": request.scan_id}


# ---------------------------------------------------------------------------
# GET /settings — current detection config
# ---------------------------------------------------------------------------

@app.get("/settings", response_model=SettingsResponse, tags=["Configuration"])
def get_settings(orch: DetectionOrchestrator = Depends(get_orchestrator)):
    cfg = orch.config
    return SettingsResponse(
        low_threshold=cfg.low_threshold,
        high_threshold=cfg.high_threshold,
        enabled_layers=sorted(cfg.enabled_layers),
        layer_weights=cfg.layer_weights,
    )


# ---------------------------------------------------------------------------
# PUT /settings/thresholds
# ---------------------------------------------------------------------------

@app.put("/settings/thresholds", tags=["Configuration"])
def update_thresholds(
    request: UpdateThresholdsRequest,
    orch: DetectionOrchestrator = Depends(get_orchestrator),
):
    if request.low_threshold >= request.high_threshold:
        raise HTTPException(status_code=400, detail="low_threshold must be < high_threshold")
    orch.update_thresholds(request.low_threshold, request.high_threshold)
    return {"message": "Thresholds updated", "low": request.low_threshold, "high": request.high_threshold}


# ---------------------------------------------------------------------------
# PUT /settings/layers
# ---------------------------------------------------------------------------

@app.put("/settings/layers", tags=["Configuration"])
def toggle_layer(
    request: ToggleLayerRequest,
    orch: DetectionOrchestrator = Depends(get_orchestrator),
):
    valid_layers = {"pattern_matcher", "structural_analyzer", "statistical_analyzer", "ml_classifier"}
    if request.layer not in valid_layers:
        raise HTTPException(status_code=400, detail=f"Unknown layer: {request.layer}")
    try:
        orch.toggle_layer(request.layer, request.enabled)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": f"Layer '{request.layer}' {'enabled' if request.enabled else 'disabled'}"}


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Meta"])
def health():
    return {"status": "ok", "version": "1.0.0"}
