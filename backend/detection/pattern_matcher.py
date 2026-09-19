"""
Pattern Matcher — Layer 1 of the detection engine.

Loads injection patterns from a YAML ruleset and uses compiled regex
to detect known injection phrases.  Returns a confidence score and the
list of matched spans so every decision is fully explainable.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Default path relative to this file's parent's parent
_DEFAULT_RULES_PATH = Path(__file__).parent.parent / "rules" / "injection_patterns.yaml"


@dataclass
class PatternMatch:
    pattern_id: str
    category: str
    description: str
    matched_text: str
    start: int
    end: int
    weight: float


@dataclass
class PatternMatchResult:
    confidence: float                           # 0-1 aggregated score
    matched_patterns: list[PatternMatch] = field(default_factory=list)
    processing_time_ms: float = 0.0
    layer: str = "pattern_matcher"

    @property
    def is_flagged(self) -> bool:
        return self.confidence > 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "confidence": round(self.confidence, 4),
            "is_flagged": self.is_flagged,
            "matched_count": len(self.matched_patterns),
            "processing_time_ms": round(self.processing_time_ms, 2),
            "matches": [
                {
                    "pattern_id": m.pattern_id,
                    "category": m.category,
                    "description": m.description,
                    "matched_text": m.matched_text[:200],  # truncate for safety
                    "start": m.start,
                    "end": m.end,
                    "weight": m.weight,
                }
                for m in self.matched_patterns
            ],
        }


class PatternMatcher:
    """
    Regex/keyword-based detector.  Loads rules from an external YAML file
    so patterns can be updated without touching code.
    """

    def __init__(self, rules_path: Path | str | None = None) -> None:
        self._rules_path = Path(rules_path) if rules_path else _DEFAULT_RULES_PATH
        self._categories: list[dict] = []
        self._compiled: list[tuple[re.Pattern, dict, float]] = []  # (pattern, meta, weight)
        self.load_rules()

    # ------------------------------------------------------------------
    # Rule loading
    # ------------------------------------------------------------------

    def load_rules(self) -> None:
        """Load (or reload) rules from the YAML file."""
        with open(self._rules_path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)

        self._categories = data.get("categories", [])
        self._compiled = []

        for category in self._categories:
            cat_name = category["name"]
            cat_weight = float(category.get("weight", 0.8))
            for pat in category.get("patterns", []):
                try:
                    compiled = re.compile(
                        pat["pattern"],
                        flags=re.IGNORECASE | re.UNICODE | re.DOTALL,
                    )
                    self._compiled.append(
                        (
                            compiled,
                            {
                                "id": pat["id"],
                                "category": cat_name,
                                "description": pat.get("description", ""),
                            },
                            cat_weight,
                        )
                    )
                except re.error as exc:
                    # Log bad patterns but don't crash
                    print(f"[PatternMatcher] Bad regex pattern {pat.get('id', '?')}: {exc}")

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def scan(self, text: str) -> PatternMatchResult:
        """
        Scan *text* against all loaded patterns.

        Confidence is computed as:
            1 - product(1 - w_i for each unique category matched)
        This means multiple matches from the same category don't compound
        indefinitely, but matches across different categories do.
        """
        t0 = time.perf_counter()
        matches: list[PatternMatch] = []
        seen_categories: dict[str, float] = {}  # category -> highest weight match

        for compiled_re, meta, weight in self._compiled:
            for m in compiled_re.finditer(text):
                pm = PatternMatch(
                    pattern_id=meta["id"],
                    category=meta["category"],
                    description=meta["description"],
                    matched_text=m.group(0),
                    start=m.start(),
                    end=m.end(),
                    weight=weight,
                )
                matches.append(pm)
                # Track highest weight per category for aggregation
                if meta["category"] not in seen_categories or weight > seen_categories[meta["category"]]:
                    seen_categories[meta["category"]] = weight

        # Aggregate: combine evidence across categories
        if seen_categories:
            prob_no_injection = 1.0
            for w in seen_categories.values():
                prob_no_injection *= 1.0 - w
            confidence = 1.0 - prob_no_injection
        else:
            confidence = 0.0

        elapsed_ms = (time.perf_counter() - t0) * 1000
        return PatternMatchResult(
            confidence=min(confidence, 1.0),
            matched_patterns=matches,
            processing_time_ms=elapsed_ms,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def rule_count(self) -> int:
        return len(self._compiled)

    @property
    def category_count(self) -> int:
        return len(self._categories)
