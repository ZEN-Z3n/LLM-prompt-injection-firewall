"""
Structural Analyzer — Layer 2 of the detection engine.

Detects hidden/obfuscated injection techniques that live at the
document structure level rather than in visible text:
  • Zero-width Unicode characters between letters
  • Near-zero font size text in PDF/DOCX
  • White-on-white (invisible) text
  • Homoglyph substitution (Cyrillic/Greek lookalikes in Latin text)
  • Base64 / hex-encoded blobs that decode to instruction-like text
"""

from __future__ import annotations

import base64
import binascii
import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Zero-width / invisible Unicode characters
# ---------------------------------------------------------------------------

ZERO_WIDTH_CHARS: dict[str, str] = {
    "\u200b": "ZERO WIDTH SPACE",
    "\u200c": "ZERO WIDTH NON-JOINER",
    "\u200d": "ZERO WIDTH JOINER",
    "\u200e": "LEFT-TO-RIGHT MARK",
    "\u200f": "RIGHT-TO-LEFT MARK",
    "\u2060": "WORD JOINER",
    "\u2061": "FUNCTION APPLICATION",
    "\u2062": "INVISIBLE TIMES",
    "\u2063": "INVISIBLE SEPARATOR",
    "\u2064": "INVISIBLE PLUS",
    "\ufeff": "ZERO WIDTH NO-BREAK SPACE (BOM)",
    "\u00ad": "SOFT HYPHEN",
    "\u034f": "COMBINING GRAPHEME JOINER",
    "\u180e": "MONGOLIAN VOWEL SEPARATOR",
    "\u17b5": "KHMER VOWEL INHERENT AA",
    "\u17b4": "KHMER VOWEL INHERENT AQ",
}

# ---------------------------------------------------------------------------
# Homoglyph table — common Cyrillic/Greek lookalikes mapped to their Latin
# equivalents.  Source: Unicode Consortium confusables.txt (abridged).
# ---------------------------------------------------------------------------

HOMOGLYPH_MAP: dict[str, str] = {
    # Cyrillic
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H",
    "О": "O", "Р": "P", "С": "C", "Т": "T", "Х": "X", "У": "Y",
    "і": "i", "ї": "i", "І": "I",
    # Greek
    "α": "a", "β": "b", "ε": "e", "ζ": "z", "η": "h", "ι": "i",
    "κ": "k", "ν": "v", "ο": "o", "ρ": "p", "τ": "t", "υ": "u",
    "χ": "x", "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H",
    "Ι": "I", "Κ": "K", "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P",
    "Τ": "T", "Υ": "Y", "Χ": "X",
    # Other common lookalikes
    "ⅼ": "l", "ℓ": "l", "ｌ": "l", "１": "1", "０": "0",
    "ʼ": "'", "ˈ": "'", "‛": "'", "\u2019": "'",
}

# Characters from scripts other than Basic Latin + common extended Latin
_SUSPICIOUS_SCRIPT_RE = re.compile(
    r"[\u0400-\u04FF"   # Cyrillic
    r"\u0370-\u03FF"   # Greek
    r"\u0500-\u052F"   # Cyrillic Supplement
    r"\uFF00-\uFFEF]"  # Fullwidth forms
)

# ---------------------------------------------------------------------------
# Base64 / hex blob detection
# ---------------------------------------------------------------------------

_BASE64_RE = re.compile(r"(?:[A-Za-z0-9+/]{4}){4,}(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?")
_HEX_RE = re.compile(r"\b(?:[0-9a-fA-F]{2}\s*){8,}\b")

# Patterns that would make a decoded blob look like an injection
_DECODED_INJECTION_RE = re.compile(
    r"ignore|disregard|forget|override|system\s*prompt|new\s+instructions?|act\s+as|you\s+are\s+now",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class StructuralFlag:
    kind: str            # e.g. "zero_width_char", "homoglyph", "base64_blob"
    description: str
    location: str        # "char:NN" or "span:NN-NN"
    span: tuple[int, int]
    severity: float      # 0-1


@dataclass
class StructuralAnalysisResult:
    confidence: float
    flags: list[StructuralFlag] = field(default_factory=list)
    processing_time_ms: float = 0.0
    layer: str = "structural_analyzer"

    @property
    def is_flagged(self) -> bool:
        return self.confidence > 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "confidence": round(self.confidence, 4),
            "is_flagged": self.is_flagged,
            "flag_count": len(self.flags),
            "processing_time_ms": round(self.processing_time_ms, 2),
            "flags": [
                {
                    "kind": f.kind,
                    "description": f.description,
                    "location": f.location,
                    "span": list(f.span),
                    "severity": f.severity,
                }
                for f in self.flags
            ],
        }


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class StructuralAnalyzer:
    """
    Detects steganographic and structural injection techniques.
    Operates on plain text; document-level analysis (PDF colors, font sizes)
    is delegated to the caller which pre-extracts text with annotations.
    """

    # Minimum ratio of homoglyphs in a word to flag it
    HOMOGLYPH_WORD_THRESHOLD = 0.3

    def scan(self, text: str, pdf_annotations: list[dict] | None = None) -> StructuralAnalysisResult:
        """
        Scan text for structural injection markers.

        Args:
            text: The plain text to analyse.
            pdf_annotations: Optional list of span dicts from PDF extraction
                             each with keys: {text, font_color, bg_color,
                             font_size, start, end}
        """
        t0 = time.perf_counter()
        flags: list[StructuralFlag] = []

        flags.extend(self._detect_zero_width_chars(text))
        flags.extend(self._detect_homoglyphs(text))
        flags.extend(self._detect_encoded_blobs(text))

        if pdf_annotations:
            flags.extend(self._detect_invisible_text(pdf_annotations))

        confidence = self._aggregate_confidence(flags)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        return StructuralAnalysisResult(
            confidence=confidence,
            flags=flags,
            processing_time_ms=elapsed_ms,
        )

    # ------------------------------------------------------------------
    # Zero-width character detection
    # ------------------------------------------------------------------

    def _detect_zero_width_chars(self, text: str) -> list[StructuralFlag]:
        flags = []
        for i, ch in enumerate(text):
            if ch in ZERO_WIDTH_CHARS:
                name = ZERO_WIDTH_CHARS[ch]
                # Check if it appears *inside* a word (more suspicious)
                is_inside_word = (
                    i > 0
                    and i < len(text) - 1
                    and text[i - 1].isalpha()
                    and text[i + 1].isalpha()
                )
                severity = 0.75 if is_inside_word else 0.40
                flags.append(
                    StructuralFlag(
                        kind="zero_width_char",
                        description=f"{name} (U+{ord(ch):04X}) {'inside word' if is_inside_word else 'in text'}",
                        location=f"char:{i}",
                        span=(i, i + 1),
                        severity=severity,
                    )
                )
        return flags

    # ------------------------------------------------------------------
    # Homoglyph detection
    # ------------------------------------------------------------------

    def _detect_homoglyphs(self, text: str) -> list[StructuralFlag]:
        flags = []
        words = list(re.finditer(r"\b\w+\b", text))
        for m in words:
            word = m.group(0)
            homoglyph_chars = [ch for ch in word if ch in HOMOGLYPH_MAP]
            # Also flag characters from suspicious scripts not in the map
            script_chars = _SUSPICIOUS_SCRIPT_RE.findall(word)
            suspicious = homoglyph_chars + [c for c in script_chars if c not in HOMOGLYPH_MAP]
            if not suspicious:
                continue
            ratio = len(suspicious) / len(word)
            if ratio >= self.HOMOGLYPH_WORD_THRESHOLD:
                # Reconstruct normalised version
                normalised = "".join(HOMOGLYPH_MAP.get(c, c) for c in word)
                flags.append(
                    StructuralFlag(
                        kind="homoglyph",
                        description=(
                            f"Word '{word}' contains {len(suspicious)} homoglyph character(s), "
                            f"normalises to '{normalised}'"
                        ),
                        location=f"span:{m.start()}-{m.end()}",
                        span=(m.start(), m.end()),
                        severity=min(0.5 + ratio * 0.5, 0.95),
                    )
                )
        return flags

    # ------------------------------------------------------------------
    # Base64 / hex blob detection
    # ------------------------------------------------------------------

    def _detect_encoded_blobs(self, text: str) -> list[StructuralFlag]:
        flags = []

        # --- Base64 ---
        for m in _BASE64_RE.finditer(text):
            blob = m.group(0).strip()
            try:
                decoded = base64.b64decode(blob + "==").decode("utf-8", errors="ignore")
                if _DECODED_INJECTION_RE.search(decoded):
                    flags.append(
                        StructuralFlag(
                            kind="base64_encoded_injection",
                            description=f"Base64 blob decodes to injection-like text: '{decoded[:100]}'",
                            location=f"span:{m.start()}-{m.end()}",
                            span=(m.start(), m.end()),
                            severity=0.90,
                        )
                    )
                elif len(decoded) > 20 and decoded.isprintable():
                    # Suspicious but not confirmed — flag with lower severity
                    flags.append(
                        StructuralFlag(
                            kind="base64_blob",
                            description=f"Base64 blob found (decoded: '{decoded[:80]}')",
                            location=f"span:{m.start()}-{m.end()}",
                            span=(m.start(), m.end()),
                            severity=0.40,
                        )
                    )
            except (binascii.Error, ValueError):
                pass

        # --- Hex sequences ---
        for m in _HEX_RE.finditer(text):
            hex_str = re.sub(r"\s+", "", m.group(0))
            try:
                decoded = bytes.fromhex(hex_str).decode("utf-8", errors="ignore")
                if _DECODED_INJECTION_RE.search(decoded):
                    flags.append(
                        StructuralFlag(
                            kind="hex_encoded_injection",
                            description=f"Hex blob decodes to injection-like text: '{decoded[:100]}'",
                            location=f"span:{m.start()}-{m.end()}",
                            span=(m.start(), m.end()),
                            severity=0.88,
                        )
                    )
            except ValueError:
                pass

        return flags

    # ------------------------------------------------------------------
    # Invisible text (from PDF/DOCX annotations)
    # ------------------------------------------------------------------

    def _detect_invisible_text(self, annotations: list[dict]) -> list[StructuralFlag]:
        flags = []
        for ann in annotations:
            text = ann.get("text", "").strip()
            if not text:
                continue

            font_size = ann.get("font_size", 12)
            font_color = ann.get("font_color")  # (r,g,b) tuple 0-1
            bg_color = ann.get("bg_color")      # (r,g,b) tuple 0-1

            # Near-zero font size
            if isinstance(font_size, (int, float)) and 0 < font_size < 2:
                flags.append(
                    StructuralFlag(
                        kind="tiny_font",
                        description=f"Text with font size {font_size}pt: '{text[:80]}'",
                        location=f"span:{ann.get('start', 0)}-{ann.get('end', 0)}",
                        span=(ann.get("start", 0), ann.get("end", 0)),
                        severity=0.80,
                    )
                )

            # White-on-white / invisible text
            if font_color and bg_color:
                color_distance = sum(
                    (a - b) ** 2 for a, b in zip(font_color, bg_color)
                ) ** 0.5
                if color_distance < 0.1:  # very close colors
                    flags.append(
                        StructuralFlag(
                            kind="invisible_text",
                            description=f"Font color ≈ background color (distance={color_distance:.3f}): '{text[:80]}'",
                            location=f"span:{ann.get('start', 0)}-{ann.get('end', 0)}",
                            span=(ann.get("start", 0), ann.get("end", 0)),
                            severity=0.85,
                        )
                    )

        return flags

    # ------------------------------------------------------------------
    # Confidence aggregation
    # ------------------------------------------------------------------

    def _aggregate_confidence(self, flags: list[StructuralFlag]) -> float:
        if not flags:
            return 0.0
        # Group by kind, take max severity per kind, then combine
        by_kind: dict[str, float] = {}
        for f in flags:
            by_kind[f.kind] = max(by_kind.get(f.kind, 0.0), f.severity)
        prob_clean = 1.0
        for sev in by_kind.values():
            prob_clean *= 1.0 - sev
        return min(1.0 - prob_clean, 1.0)


# ---------------------------------------------------------------------------
# Convenience: strip zero-width chars from text (used by sanitizer)
# ---------------------------------------------------------------------------

def strip_zero_width_chars(text: str) -> str:
    return "".join(ch for ch in text if ch not in ZERO_WIDTH_CHARS)


def normalize_homoglyphs(text: str) -> str:
    return "".join(HOMOGLYPH_MAP.get(ch, ch) for ch in text)
