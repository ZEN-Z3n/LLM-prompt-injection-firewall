"""
Neutralizer — Phase 2, Part 1.

Strips or escapes detected injection phrases from text so they
cannot be executed by the downstream LLM.

Strategy:
  1. For HIGH-confidence pattern matches: replace matched span with
     a clearly marked [NEUTRALIZED: <reason>] placeholder.
  2. For homoglyph-substituted words: normalise back to ASCII equivalents.
  3. For zero-width characters: strip entirely.
  4. For encoded blobs (base64/hex): replace with [REDACTED_ENCODED_CONTENT].
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from detection.orchestrator import ScanReport
from detection.structural_analyzer import normalize_homoglyphs, strip_zero_width_chars


@dataclass
class NeutralizationEdit:
    start: int
    end: int
    original: str
    replacement: str
    reason: str


@dataclass
class NeutralizedText:
    original_text: str
    neutralized_text: str
    edits: list[NeutralizationEdit] = field(default_factory=list)

    @property
    def was_modified(self) -> bool:
        return self.original_text != self.neutralized_text

    def to_dict(self) -> dict[str, Any]:
        return {
            "was_modified": self.was_modified,
            "edit_count": len(self.edits),
            "edits": [
                {
                    "span": [e.start, e.end],
                    "original": e.original[:100],
                    "replacement": e.replacement,
                    "reason": e.reason,
                }
                for e in self.edits
            ],
        }


class Neutralizer:
    """
    Sanitizes text by replacing detected injection content with
    safe, literal placeholders.
    """

    # Confidence threshold above which a pattern match triggers replacement
    REPLACE_THRESHOLD = 0.50

    def neutralize(self, text: str, report: ScanReport) -> NeutralizedText:
        """
        Apply neutralization based on the scan report.
        """
        edits: list[NeutralizationEdit] = []
        working = text

        # --- Step 1: Strip zero-width characters ---
        cleaned = strip_zero_width_chars(working)
        if cleaned != working:
            edits.append(
                NeutralizationEdit(
                    start=0,
                    end=len(working),
                    original=working,
                    replacement=cleaned,
                    reason="Stripped zero-width Unicode characters",
                )
            )
            working = cleaned

        # --- Step 2: Normalise homoglyphs ---
        normalized = normalize_homoglyphs(working)
        if normalized != working:
            edits.append(
                NeutralizationEdit(
                    start=0,
                    end=len(working),
                    original=working,
                    replacement=normalized,
                    reason="Normalised homoglyph characters to ASCII equivalents",
                )
            )
            working = normalized

        # --- Step 3: Replace matched injection patterns ---
        if report.pattern_result and report.pattern_result.confidence >= self.REPLACE_THRESHOLD:
            working, pattern_edits = self._replace_pattern_matches(working, report)
            edits.extend(pattern_edits)

        # --- Step 4: Replace encoded blobs flagged by structural analyzer ---
        if report.structural_result:
            working, struct_edits = self._replace_encoded_blobs(working, report)
            edits.extend(struct_edits)

        return NeutralizedText(
            original_text=text,
            neutralized_text=working,
            edits=edits,
        )

    def _replace_pattern_matches(
        self, text: str, report: ScanReport
    ) -> tuple[str, list[NeutralizationEdit]]:
        """Replace all matched injection spans with [NEUTRALIZED] markers."""
        edits: list[NeutralizationEdit] = []
        if not report.pattern_result:
            return text, edits

        # Sort matches by start position descending so replacements don't
        # invalidate earlier span indices
        matches = sorted(report.pattern_result.matched_patterns, key=lambda m: m.start, reverse=True)
        result = text

        seen_spans: set[tuple[int, int]] = set()
        for match in matches:
            span = (match.start, match.end)
            if span in seen_spans:
                continue
            seen_spans.add(span)

            original = result[match.start : match.end]
            marker = f'[NEUTRALIZED:{match.pattern_id}:"{original[:50]}"]'
            result = result[: match.start] + marker + result[match.end :]
            edits.append(
                NeutralizationEdit(
                    start=match.start,
                    end=match.end,
                    original=original,
                    replacement=marker,
                    reason=f"Matched pattern {match.pattern_id} ({match.category}): {match.description}",
                )
            )

        return result, edits

    def _replace_encoded_blobs(
        self, text: str, report: ScanReport
    ) -> tuple[str, list[NeutralizationEdit]]:
        """Replace base64/hex blobs that decode to injection-like text."""
        edits: list[NeutralizationEdit] = []
        if not report.structural_result:
            return text, edits

        result = text
        offset = 0  # Track text position shift from replacements

        encoded_flags = [
            f
            for f in report.structural_result.flags
            if f.kind in ("base64_encoded_injection", "hex_encoded_injection", "base64_blob")
        ]

        for flag in sorted(encoded_flags, key=lambda f: f.span[0]):
            start = flag.span[0] + offset
            end = flag.span[1] + offset
            original = result[start:end]
            marker = f"[REDACTED_ENCODED_CONTENT:{flag.kind}]"
            result = result[:start] + marker + result[end:]
            delta = len(marker) - len(original)
            offset += delta
            edits.append(
                NeutralizationEdit(
                    start=flag.span[0],
                    end=flag.span[1],
                    original=original[:100],
                    replacement=marker,
                    reason=flag.description,
                )
            )

        return result, edits
