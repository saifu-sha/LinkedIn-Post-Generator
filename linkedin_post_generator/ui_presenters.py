"""Pure presentation helpers for the Streamlit application."""

from __future__ import annotations

import math
import re
from typing import Sequence

from .generator import VARIANT_ANGLES
from .models import GenerationOptions
from .quality import normalize_post_text

HASHTAG_PATTERN = re.compile(r"(?<!\w)#\w+")
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")
CLAUSE_SPLIT_PATTERN = re.compile(r"(?<=[,:;])\s+")
TRAILING_HASHTAGS_PATTERN = re.compile(r"^(?P<body>.*?)(?:\s+(?P<hashtags>(?:#\w+\s*)+))?$", re.S)


def build_brief_signature(
    topic: str,
    length: str,
    language: str,
    options: GenerationOptions,
) -> tuple[str, str, str, str, str, str, str, str, int]:
    """Build a stable signature for the current generation brief."""

    return (
        topic,
        length,
        language,
        options.tone,
        options.audience,
        options.goal,
        options.voice,
        options.cta_strength,
        options.hashtag_count,
    )


def build_brief_chips(
    topic: str,
    length: str,
    language: str,
    options: GenerationOptions,
) -> list[dict[str, str]]:
    """Build compact chip payloads for the selected generation brief."""

    hashtag_text = "No hashtags"
    if options.hashtag_count == 1:
        hashtag_text = "1 hashtag"
    elif options.hashtag_count > 1:
        hashtag_text = f"{options.hashtag_count} hashtags"

    return [
        {"label": "Topic", "value": topic},
        {"label": "Format", "value": f"{length} / {language}"},
        {"label": "Tone", "value": options.tone},
        {"label": "Audience", "value": options.audience},
        {"label": "Goal", "value": options.goal},
        {"label": "Voice", "value": options.voice},
        {
            "label": "Finish",
            "value": f"CTA: {options.cta_strength} / {hashtag_text}",
        },
    ]


def _split_trailing_hashtags(text: str) -> tuple[str, str]:
    """Split trailing hashtags from the main body when present."""

    match = TRAILING_HASHTAGS_PATTERN.match(text.strip())
    if match is None:
        return text.strip(), ""

    body = (match.group("body") or "").strip()
    hashtags = " ".join(re.findall(r"#\w+", match.group("hashtags") or ""))
    return body, hashtags


def estimate_display_lines(text: str) -> int:
    """Estimate readable line count for result-card metadata."""

    normalized = normalize_post_text(text, preserve_lines=True)
    if not normalized:
        return 0

    body, hashtags = _split_trailing_hashtags(normalized)
    explicit_lines = [line.strip() for line in body.splitlines() if line.strip()]
    if len(explicit_lines) > 1:
        return len(explicit_lines) + (1 if hashtags else 0)

    compact_body = normalize_post_text(body, preserve_lines=False)
    if not compact_body:
        return 1 if hashtags else 0

    sentence_chunks = [chunk.strip() for chunk in SENTENCE_SPLIT_PATTERN.split(compact_body) if chunk.strip()]
    if len(sentence_chunks) > 1:
        return len(sentence_chunks) + (1 if hashtags else 0)

    clause_chunks = [chunk.strip() for chunk in CLAUSE_SPLIT_PATTERN.split(compact_body) if chunk.strip()]
    if len(clause_chunks) > 1:
        return len(clause_chunks) + (1 if hashtags else 0)

    estimated_lines = max(1, math.ceil(len(compact_body) / 90))
    if hashtags:
        estimated_lines += 1
    return estimated_lines


def format_line_label(line_count: int) -> str:
    """Return a singular/plural line label."""

    noun = "line" if line_count == 1 else "lines"
    return f"{line_count} {noun}"


def format_hashtag_label(hashtag_count: int) -> str:
    """Return a singular/plural hashtag label."""

    noun = "hashtag" if hashtag_count == 1 else "hashtags"
    return f"{hashtag_count} {noun}"


def build_variant_cards(
    variants: Sequence[str],
    *,
    variant_angles: Sequence[str] = VARIANT_ANGLES,
) -> list[dict[str, str | int]]:
    """Build card labels and metadata for generated variants."""

    cards: list[dict[str, str | int]] = []
    for index, raw_text in enumerate(variants, start=1):
        text = normalize_post_text(raw_text, preserve_lines=True)
        angle_label = (
            str(variant_angles[index - 1]).strip()
            if index - 1 < len(variant_angles)
            else f"Variant {index}"
        )
        slug = re.sub(r"[^a-z0-9]+", "-", angle_label.lower()).strip("-") or f"variant-{index}"
        estimated_lines = estimate_display_lines(text)
        cards.append(
            {
                "index": index,
                "angle_label": angle_label,
                "card_label": f"Variant {index}",
                "text": text,
                "estimated_lines": estimated_lines,
                "line_label": format_line_label(estimated_lines),
                "hashtag_count": len(HASHTAG_PATTERN.findall(text)),
                "hashtag_label": format_hashtag_label(len(HASHTAG_PATTERN.findall(text))),
                "copy_label": "Copy",
                "copy_feedback": "Copied",
                "copy_target": f"variant-{index}-{slug}",
            }
        )
    return cards
