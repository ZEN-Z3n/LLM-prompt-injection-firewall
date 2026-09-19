"""
Orchestrator — combines all 4 detection layers into a single
weighted risk score with full explainability.

Decision mapping:
  - confidence < LOW_THRESHOLD   → RiskLevel.LOW   → action: PASS_THROUGH
  - LOW ≤ confidence < HIGH      → RiskLevel.MEDIUM → action: SANITIZE
  - confidence ≥ HIGH_THRESHOLD  → RiskLevel.HIGH   → action: BLOCK
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from detection.ml_classifier import MLClassifier, MLPrediction
from detection.pattern_matcher import PatternMatcher, PatternMatchResult
from detection.statistical_analyzer import StatisticalAnalyzer, StatisticalAnalysisResult
from detection.structural_analyzer import StructuralAnalyzer, StructuralAnalysisResult


# ---------------------------------------------------------------------------
# Risk types
# ---------------------------------------------------------------------------


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Action(str, Enum):
    PASS_THROUGH = "PASS_THROUGH"    # Allow with metadata
    SANITIZE = "SANITIZE"            # Strip & isolate, then allow
    BLOCK = "BLOCK"                  # Quarantine, do not forward


# ---------------------------------------------------------------------------
# Layer weights (must sum to 1.0)
# ---------------------------------------------------------------------------

DEFAULT_LAYER_WEIGHTS = {
    "pattern_matcher":    0.35,   # Highest — direct rule matches are very reliable
    "structural_analyzer": 0.25,  # High — structural tricks are strong signals
    "ml_classifier":      0.25,   # High — semantic understanding
    "statistical_analyzer": 0.15, # Medium — heuristics, more false-positives
}

DEFAULT_LOW_THRESHOLD = 0.20
DEFAULT_HIGH_THRESHOLD = 0.55


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class OrchestratorConfig:
    low_threshold: float = DEFAULT_LOW_THRESHOLD
    high_threshold: float = DEFAULT_HIGH_THRESHOLD
    layer_weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_LAYER_WEIGHTS))
    enabled_layers: set[str] = field(
        default_factory=lambda: {
            "pattern_matcher",
            "structural_analyzer",
            "ml_classifier",
            "statistical_analyzer",
        }
    )

    def validate(self) -> None:
        assert 0.0 < self.low_threshold < self.high_threshold <= 1.0, "Invalid thresholds"
        active = {k: v for k, v in self.layer_weights.items() if k in self.enabled_layers}
        total = sum(active.values())
        if abs(total) < 1e-9:
            raise ValueError("All enabled layer weights are zero")
        # Normalise weights to sum to 1
        for k in active:
            self.layer_weights[k] = active[k] / total


@dataclass
class ScanReport:
    """Complete, explainable report of a single scan."""

    # Aggregate
    risk_score: float
    risk_level: RiskLevel
    action: Action
    total_processing_time_ms: float

    # Per-layer results
    pattern_result: PatternMatchResult | None = None
    structural_result: StructuralAnalysisResult | None = None
    statistical_result: StatisticalAnalysisResult | None = None
    ml_result: MLPrediction | None = None

    # Summary
    primary_reason: str = ""
    layer_contributions: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_score": round(self.risk_score, 4),
            "risk_level": self.risk_level.value,
            "action": self.action.value,
            "primary_reason": self.primary_reason,
            "total_processing_time_ms": round(self.total_processing_time_ms, 2),
            "layer_contributions": {
                k: round(v, 4) for k, v in self.layer_contributions.items()
            },
            "layers": {
                "pattern_matcher": self.pattern_result.to_dict() if self.pattern_result else None,
                "structural_analyzer": self.structural_result.to_dict() if self.structural_result else None,
                "statistical_analyzer": self.statistical_result.to_dict() if self.statistical_result else None,
                "ml_classifier": self.ml_result.to_dict() if self.ml_result else None,
            },
        }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class DetectionOrchestrator:
    """
    Runs all enabled detection layers and aggregates their scores
    into a final risk decision.

    Usage:
        orch = DetectionOrchestrator()
        report = orch.scan("ignore all previous instructions and...")
        print(report.risk_level, report.action)
    """

    def __init__(
        self,
        config: OrchestratorConfig | None = None,
        pattern_matcher: PatternMatcher | None = None,
        structural_analyzer: StructuralAnalyzer | None = None,
        statistical_analyzer: StatisticalAnalyzer | None = None,
        ml_classifier: MLClassifier | None = None,
    ) -> None:
        self.config = config or OrchestratorConfig()
        self.config.validate()

        # Allow dependency injection for testing
        self._pm = pattern_matcher or PatternMatcher()
        self._sa = structural_analyzer or StructuralAnalyzer()
        self._sta = statistical_analyzer or StatisticalAnalyzer(use_embeddings=False)
        self._ml = ml_classifier or MLClassifier(prefer_zero_shot=False)  # use sklearn by default

    # ------------------------------------------------------------------
    # Public scan API
    # ------------------------------------------------------------------

    def scan(
        self,
        text: str,
        pdf_annotations: list[dict] | None = None,
    ) -> ScanReport:
        """
        Run all enabled detection layers and return a full ScanReport.

        Args:
            text: Plain text to analyse.
            pdf_annotations: Optional PDF span annotations for structural checks.
        """
        t_total = time.perf_counter()
        enabled = self.config.enabled_layers
        weights = self.config.layer_weights

        pm_result = sta_result = sa_result = ml_result = None
        layer_scores: dict[str, float] = {}

        # --- Layer 1: Pattern Matcher ---
        if "pattern_matcher" in enabled:
            pm_result = self._pm.scan(text)
            layer_scores["pattern_matcher"] = pm_result.confidence

        # --- Layer 2: Structural Analyzer ---
        if "structural_analyzer" in enabled:
            sa_result = self._sa.scan(text, pdf_annotations=pdf_annotations)
            layer_scores["structural_analyzer"] = sa_result.confidence

        # --- Layer 3: Statistical Analyzer ---
        if "statistical_analyzer" in enabled:
            sta_result = self._sta.scan(text)
            layer_scores["statistical_analyzer"] = sta_result.confidence

        # --- Layer 4: ML Classifier ---
        if "ml_classifier" in enabled:
            ml_result = self._ml.predict(text)
            # ML gives injection probability; map label → score
            ml_score = ml_result.confidence if ml_result.is_injection else (1.0 - ml_result.confidence) * 0.3
            layer_scores["ml_classifier"] = ml_score

        # --- Aggregate ---
        risk_score, contributions = self._aggregate(layer_scores, weights, enabled)
        risk_level = self._classify(risk_score)
        action = self._decide_action(risk_level)
        primary_reason = self._build_reason(
            risk_score, pm_result, sa_result, sta_result, ml_result
        )

        total_ms = (time.perf_counter() - t_total) * 1000

        return ScanReport(
            risk_score=risk_score,
            risk_level=risk_level,
            action=action,
            total_processing_time_ms=total_ms,
            pattern_result=pm_result,
            structural_result=sa_result,
            statistical_result=sta_result,
            ml_result=ml_result,
            primary_reason=primary_reason,
            layer_contributions=contributions,
        )

    # ------------------------------------------------------------------
    # Config updates (for settings endpoint)
    # ------------------------------------------------------------------

    def update_config(self, new_config: OrchestratorConfig) -> None:
        new_config.validate()
        self.config = new_config

    def update_thresholds(self, low: float, high: float) -> None:
        self.config.low_threshold = low
        self.config.high_threshold = high
        self.config.validate()

    def toggle_layer(self, layer: str, enabled: bool) -> None:
        if enabled:
            self.config.enabled_layers.add(layer)
        else:
            self.config.enabled_layers.discard(layer)
        self.config.validate()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _aggregate(
        self,
        layer_scores: dict[str, float],
        weights: dict[str, float],
        enabled: set[str],
    ) -> tuple[float, dict[str, float]]:
        """Weighted average of active layer scores."""
        active_weights = {k: weights.get(k, 0.0) for k in layer_scores if k in enabled}
        total_weight = sum(active_weights.values())
        if total_weight < 1e-9:
            return 0.0, {}

        contributions: dict[str, float] = {}
        weighted_sum = 0.0
        for layer, score in layer_scores.items():
            w = active_weights.get(layer, 0.0)
            contribution = score * (w / total_weight)
            contributions[layer] = contribution
            weighted_sum += contribution

        return round(min(weighted_sum, 1.0), 4), contributions

    def _classify(self, score: float) -> RiskLevel:
        if score >= self.config.high_threshold:
            return RiskLevel.HIGH
        if score >= self.config.low_threshold:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def _decide_action(self, level: RiskLevel) -> Action:
        return {
            RiskLevel.HIGH: Action.BLOCK,
            RiskLevel.MEDIUM: Action.SANITIZE,
            RiskLevel.LOW: Action.PASS_THROUGH,
        }[level]

    def _build_reason(
        self,
        score: float,
        pm: PatternMatchResult | None,
        sa: StructuralAnalysisResult | None,
        sta: StatisticalAnalysisResult | None,
        ml: MLPrediction | None,
    ) -> str:
        parts = []

        if pm and pm.is_flagged:
            cats = list({m.category for m in pm.matched_patterns})
            parts.append(f"pattern_matcher: {len(pm.matched_patterns)} match(es) in [{', '.join(cats)}]")

        if sa and sa.is_flagged:
            kinds = list({f.kind for f in sa.flags})
            parts.append(f"structural_analyzer: {len(sa.flags)} flag(s) [{', '.join(kinds)}]")

        if sta and sta.is_flagged:
            top_signal = max(sta.signals, key=lambda s: s.value * s.weight, default=None)
            if top_signal:
                parts.append(f"statistical_analyzer: top signal '{top_signal.name}'={top_signal.value:.2f}")

        if ml and ml.is_injection:
            parts.append(f"ml_classifier: '{ml.label}' ({ml.confidence:.0%}) via {ml.model_used}")

        if not parts:
            return f"All layers clear (score={score:.3f})"

        return "; ".join(parts)
