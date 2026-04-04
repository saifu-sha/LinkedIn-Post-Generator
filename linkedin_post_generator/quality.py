"""Shared text quality, normalization, and ranking helpers."""

from __future__ import annotations

import html
import math
import re
import unicodedata
from typing import Iterable

INVISIBLE_CHARACTER_TRANSLATION = str.maketrans(
    "",
    "",
    "\u200b\u200c\u200d\u2060\ufeff\u00ad",
)
MOJIBAKE_MARKERS = (
    "\u00c3",
    "\u00c2",
    "\u00e2\u20ac",
    "\u00f0\u0178",
)
LOW_SIGNAL_LINES = frozenset(
    {
        "activate to view larger image",
        "activate to view larger image,",
        "media player modal window",
        "no alternative text description for this image",
        "play video",
        "video player",
    }
)


def _looks_like_mojibake(text: str) -> bool:
    """Return whether the text contains common UTF-8 mojibake markers."""

    return any(marker in text for marker in MOJIBAKE_MARKERS)


def _mojibake_score(text: str) -> int:
    """Score how likely the text still contains mojibake artifacts."""

    return sum(text.count(marker) for marker in MOJIBAKE_MARKERS)


def _repair_utf8_mojibake(text: str) -> str:
    """Attempt to repair text that was decoded as cp1252 instead of UTF-8."""

    repaired = text
    for _ in range(2):
        if not _looks_like_mojibake(repaired):
            break
        try:
            candidate = repaired.encode("cp1252").decode("utf-8")
        except UnicodeError:
            break
        if _mojibake_score(candidate) >= _mojibake_score(repaired):
            break
        repaired = candidate
    return repaired


def repair_common_encoding_issues(text: str | None) -> str:
    """Repair common encoding artifacts and invisible characters."""

    repaired = "" if text is None else str(text)
    repaired = html.unescape(repaired)
    repaired = repaired.replace("\r\n", "\n").replace("\r", "\n")
    repaired = repaired.replace("\xa0", " ")
    repaired = repaired.translate(INVISIBLE_CHARACTER_TRANSLATION)
    repaired = _repair_utf8_mojibake(repaired)
    repaired = unicodedata.normalize("NFKC", repaired)
    return repaired.translate(INVISIBLE_CHARACTER_TRANSLATION)


def normalize_post_text(text: str | None, *, preserve_lines: bool = True) -> str:
    """Normalize post text while optionally preserving line breaks."""

    normalized = repair_common_encoding_issues(text)
    normalized = re.sub(r"[ \t]+\n", "\n", normalized)
    normalized = re.sub(r"\n[ \t]+", "\n", normalized)
    normalized = re.sub(r"[ \t]{2,}", " ", normalized)
    if preserve_lines:
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    else:
        normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _normalize_comparison_text(text: str) -> str:
    """Normalize already-clean text for matching and deduplication."""

    normalized = text.lower()
    normalized = re.sub(r"[^\w\s#]", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def sanitize_post_text(text: str | None) -> str:
    """Drop obvious media placeholders while preserving meaningful content."""

    normalized = normalize_post_text(text, preserve_lines=True)
    if not normalized:
        return ""

    cleaned_lines = [
        line.strip()
        for line in normalized.splitlines()
        if _normalize_comparison_text(line) not in LOW_SIGNAL_LINES
    ]
    return normalize_post_text("\n".join(cleaned_lines), preserve_lines=True)


def normalize_for_comparison(text: str | None) -> str:
    """Normalize text for deduplication and pattern matching."""

    sanitized = sanitize_post_text(text)
    return _normalize_comparison_text(
        normalize_post_text(sanitized, preserve_lines=False)
    )


def build_text_fingerprint(text: str | None) -> str:
    """Build a stable text fingerprint for near-duplicate detection."""

    return normalize_for_comparison(text)


def get_low_quality_reason(text: str | None) -> str | None:
    """Return a reason when the text is an obvious non-post artifact."""

    normalized_text = normalize_post_text(text, preserve_lines=True)
    normalized_lines = [
        _normalize_comparison_text(line)
        for line in normalized_text.splitlines()
        if _normalize_comparison_text(line)
    ]
    if not normalized_lines:
        return "empty_text"

    if all(line == "activate to view larger image" for line in normalized_lines):
        return "image_placeholder"
    if all(line in LOW_SIGNAL_LINES for line in normalized_lines):
        return "media_placeholder"

    if not sanitize_post_text(normalized_text):
        return "empty_text"

    compact = "".join(character for character in " ".join(normalized_lines) if character.isalnum())
    if not compact:
        return "empty_text"
    return None


def is_low_quality_post(text: str | None) -> bool:
    """Return whether the text is too low quality for downstream use."""

    return get_low_quality_reason(text) is not None


def build_text_preview(text: str | None, limit: int = 160) -> str:
    """Build a single-line preview for logging and reports."""

    preview = normalize_post_text(text, preserve_lines=False)
    if len(preview) > limit:
        return preview[:limit] + "..."
    return preview


def score_post_example(
    text: str,
    *,
    engagement: int = 0,
    tags: Iterable[str] | None = None,
    line_count: int = 0,
) -> float:
    """Score a post example for few-shot ranking."""

    normalized = sanitize_post_text(text)
    if is_low_quality_post(normalized):
        return float("-inf")

    words = re.findall(r"\b\w+\b", normalized)
    word_count = len(words)
    unique_word_count = len({word.lower() for word in words})
    char_count = len(normalized)
    effective_line_count = line_count or (normalized.count("\n") + 1 if normalized else 0)

    richness_score = min(word_count, 80) / 8.0
    density_score = min(char_count, 600) / 150.0
    diversity_bonus = min(unique_word_count, 50) / 50.0
    multiline_bonus = 1.25 if effective_line_count > 1 else 0.0
    tag_bonus = min(len(list(tags or [])), 2) * 0.35
    engagement_bonus = math.log1p(max(engagement, 0)) * 0.45
    title_penalty = 2.0 if effective_line_count <= 1 and word_count < 10 else 0.0

    return (
        richness_score
        + density_score
        + diversity_bonus
        + multiline_bonus
        + tag_bonus
        + engagement_bonus
        - title_penalty
    )
