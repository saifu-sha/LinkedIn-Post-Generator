"""Text normalization and safe numeric parsing for scraper output."""

from __future__ import annotations

import html
import re
from typing import Any

ABBREVIATED_NUMBER_PATTERN = re.compile(
    r"\b(\d{1,3}(?:[.,]\d{3})+|\d+(?:\.\d+)?(?:\s?[KkMm])?)\b"
)
SOCIAL_COUNT_PATTERN = re.compile(
    r"\b(\d{1,3}(?:[.,]\d{3})+|\d+(?:\.\d+)?(?:\s?[KkMm])?)\s*"
    r"(?:reactions?|likes?|react)\b",
    re.IGNORECASE,
)
REVERSED_SOCIAL_COUNT_PATTERN = re.compile(
    r"(?:reactions?|likes?|react)\s*[:\-]?\s*"
    r"(\d{1,3}(?:[.,]\d{3})+|\d+(?:\.\d+)?(?:\s?[KkMm])?)\b",
    re.IGNORECASE,
)
MAGNITUDE_PATTERN = re.compile(
    r"(?i)^(\d{1,3}(?:[.,]\d{3})+|\d+(?:\.\d+)?)(?:\s?([KM]))?$"
)


def basic_clean(value: Any) -> str:
    """Apply light HTML and whitespace cleanup to scraped text."""

    cleaned = "" if value is None else str(value)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"http\S+|www\.\S+", "", cleaned)
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    cleaned = re.sub(r"\r\n?", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n[ \t]+", "\n", cleaned)
    cleaned = "".join(character for character in cleaned if ord(character) >= 32 or character == "\n")
    cleaned = re.sub(r"([!?.]){2,}", r"\1", cleaned)
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"([,;:!?.])([A-Za-z0-9])", r"\1 \2", cleaned)
    cleaned = re.sub(r"\s+\)", ")", cleaned)
    cleaned = re.sub(r"\(\s+", "(", cleaned)
    return cleaned.strip()


def sentence_capitalize(text: str) -> str:
    """Normalize case while preserving acronyms and line breaks."""

    if not text:
        return text

    normalized = re.sub(r"[ \t]+", " ", text.strip())

    def preserve_token(token: str) -> str:
        if token.isalpha() and sum(1 for character in token if character.isupper()) > 1:
            return token
        return token.lower()

    tokens = re.findall(r"\S+|\n", normalized)
    rebuilt = [token if token == "\n" else preserve_token(token) for token in tokens]
    normalized = " ".join(token for token in rebuilt if token != " ").replace(" \n ", "\n")

    def capitalize_match(match: re.Match[str]) -> str:
        return match.group(1) + match.group(2).upper()

    normalized = re.sub(r"(^|[.!?\n]\s+)([a-z])", capitalize_match, normalized)
    normalized = re.sub(r"\bi\b", "I", normalized)
    normalized = re.sub(r" *\n *", "\n", normalized)
    return normalized.strip()


def simple_normalize_hashtags(text: str) -> str:
    """Remove repeated hashtag labels and normalize hashtag spacing."""

    if not text:
        return text
    text = re.sub(r"(?i)hashtag", "", text)
    text = re.sub(r"[\n\s]+#\s*([A-Za-z0-9_]+)", r" #\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def clean_post_text(raw_text: str | None) -> str:
    """Apply the full cleaning pipeline while preserving line breaks."""

    if raw_text is None:
        return ""

    cleaned = basic_clean(raw_text)
    cleaned = re.sub(r"\s*[â€¢Â·â€”â€“]\s*", "\n", cleaned)
    lines = [line.strip() for line in cleaned.split("\n")]
    cleaned = "\n".join(line for line in lines if line)
    cleaned = sentence_capitalize(cleaned)
    cleaned = simple_normalize_hashtags(cleaned)
    cleaned = re.sub(r"[ \t]+$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def convert_abbreviated_to_number(value: str | int | float | None) -> int:
    """Convert a normalized count string like 1.2K into an integer."""

    if value in (None, ""):
        return 0

    text = str(value).strip().replace(",", "")
    match = MAGNITUDE_PATTERN.fullmatch(text)
    if not match:
        return 0

    number_text, suffix = match.groups()
    try:
        number = float(number_text)
    except ValueError:
        return 0

    if suffix:
        multiplier = 1000 if suffix.upper() == "K" else 1_000_000
        return int(number * multiplier)
    return int(number)


def extract_number_from_text(text: str | None) -> int:
    """Extract the first count-like token from text."""

    if not text:
        return 0

    match = ABBREVIATED_NUMBER_PATTERN.search(text)
    if not match:
        return 0
    return convert_abbreviated_to_number(match.group(1))


def extract_likes_from_text_blob(text_blob: str | None) -> int:
    """Extract a social count only when it is tied to social keywords."""

    normalized = normalize_inline_text(text_blob)
    if not normalized:
        return 0

    for pattern in (SOCIAL_COUNT_PATTERN, REVERSED_SOCIAL_COUNT_PATTERN):
        match = pattern.search(normalized)
        if match:
            return convert_abbreviated_to_number(match.group(1))
    return 0


def normalize_inline_text(text: str | None) -> str:
    """Collapse inline whitespace."""

    return re.sub(r"\s+", " ", text or "").strip()


def response_preview(response: Any, limit: int = 240) -> str:
    """Return a short preview of an HTTP response body."""

    if response is None:
        return "no response received"

    try:
        snippet = normalize_inline_text(response.text)
    except Exception:
        snippet = ""

    if not snippet:
        return "empty response body"
    if len(snippet) > limit:
        return snippet[:limit] + "..."
    return snippet


def fingerprint_text(text: str | None) -> str:
    """Build a stable fingerprint for deduplicating posts."""

    if not text:
        return ""

    normalized = text.strip().lower()
    normalized = re.sub(r"\r\n?", "\n", normalized)
    normalized = re.sub(r"\n\s+", "\n", normalized)
    normalized = re.sub(r"[^\w\s#\n]", "", normalized)
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n+", "\n", normalized)
    return normalized.strip()
