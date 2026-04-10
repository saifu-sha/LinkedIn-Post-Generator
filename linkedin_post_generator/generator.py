"""Prompt construction and post generation logic."""

from __future__ import annotations

import json
import re
from textwrap import wrap
from typing import Any, Iterable

from .llm import extract_response_text, get_llm
from .models import (
    GENERATION_AUDIENCE_OPTIONS,
    GENERATION_CTA_STRENGTH_OPTIONS,
    GENERATION_GOAL_OPTIONS,
    GENERATION_TONE_OPTIONS,
    GENERATION_VOICE_OPTIONS,
    GenerationOptions,
)
from .quality import normalize_post_text
from .repository import FewShotPosts, get_default_repository

LENGTH_OPTIONS = ["Short", "Medium", "Long"]
LANGUAGE_OPTIONS = ["English", "Hinglish"]
TONE_OPTIONS = list(GENERATION_TONE_OPTIONS)
AUDIENCE_OPTIONS = list(GENERATION_AUDIENCE_OPTIONS)
GOAL_OPTIONS = list(GENERATION_GOAL_OPTIONS)
VOICE_OPTIONS = list(GENERATION_VOICE_OPTIONS)
CTA_STRENGTH_OPTIONS = list(GENERATION_CTA_STRENGTH_OPTIONS)
HASHTAG_COUNT_OPTIONS = [0, 1, 2, 3]
LENGTH_TO_DESCRIPTION = {
    "Short": "1 to 5 lines",
    "Medium": "6 to 10 lines",
    "Long": "11 to 15 lines",
}
MAX_EXAMPLES = 5
DEFAULT_VARIANT_COUNT = 3
VARIANT_ANGLES = (
    "Insight-led hook",
    "Story/problem-solution hook",
    "Action/takeaway-led hook",
)
TARGET_LINE_COUNTS = {
    "Short": (3, 5),
    "Medium": (6, 10),
    "Long": (11, 15),
}
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")
CLAUSE_SPLIT_PATTERN = re.compile(r"(?<=[,:;])\s+")
TRAILING_HASHTAGS_PATTERN = re.compile(r"^(?P<body>.*?)(?:\s+(?P<hashtags>(?:#\w+\s*)+))?$", re.S)


def get_length_str(length: str) -> str:
    """Return the line-count description for a UI length bucket."""

    try:
        return LENGTH_TO_DESCRIPTION[length]
    except KeyError as error:
        raise ValueError(f"Unsupported length {length!r}.") from error


def _resolve_options(options: GenerationOptions | None) -> GenerationOptions:
    return options if options is not None else GenerationOptions()


def _validate_variant_count(variant_count: int) -> None:
    if variant_count != DEFAULT_VARIANT_COUNT:
        raise ValueError(
            f"Only variant_count={DEFAULT_VARIANT_COUNT} is supported in this generator."
        )


def _get_target_line_counts(length: str) -> tuple[int, int]:
    try:
        return TARGET_LINE_COUNTS[length]
    except KeyError as error:
        raise ValueError(f"Unsupported length {length!r}.") from error


def _goal_instruction(goal: str) -> str:
    mapping = {
        "Match examples": "Match the overall intent and framing of the few-shot examples.",
        "Educate": "Teach something practical, clear, and immediately useful.",
        "Inspire": "Leave the reader energized, optimistic, and motivated to act.",
        "Announce": "Present a clear update or announcement with crisp context.",
    }
    return mapping[goal]


def _voice_instruction(voice: str) -> str:
    mapping = {
        "Match examples": "Follow the dominant voice in the provided examples.",
        "First Person": "Use first-person singular language such as I, me, and my.",
        "Brand/Company": "Use company or team voice and avoid first-person singular pronouns.",
    }
    return mapping[voice]


def _cta_instruction(cta_strength: str) -> str:
    mapping = {
        "None": "Do not include an explicit call to action.",
        "Soft": "Close with a light reflective or conversational call to action.",
        "Strong": "Close with a direct and specific call to action.",
    }
    return mapping[cta_strength]


def _hashtag_instruction(hashtag_count: int) -> str:
    if hashtag_count == 0:
        return "Do not include hashtags."
    noun = "hashtag" if hashtag_count == 1 else "hashtags"
    return (
        f"Include exactly {hashtag_count} relevant {noun} on the final line only, "
        "separated by spaces."
    )


def _line_layout_instruction(length: str) -> str:
    minimum, maximum = _get_target_line_counts(length)
    return (
        f"Use compact LinkedIn-ready line breaks so the post reads as about {minimum} to {maximum} visible lines. "
        "Do not compress the full post into one continuous paragraph, and do not add blank spacer lines "
        "between every sentence. "
        'Because the response is JSON, encode those line breaks inside each string as "\\n", '
        "not as literal raw line breaks."
    )


def _emoji_style_instruction() -> str:
    return (
        "Use 1-2 relevant professional emojis only when they feel natural; "
        "do not use emojis on every line."
    )


def _append_style_controls(
    prompt_parts: list[str],
    *,
    section_number: int,
    options: GenerationOptions,
) -> None:
    prompt_parts.extend(
        [
            f"{section_number}) Style Controls:",
            f"- Tone: {options.tone}",
            f"- Audience: {options.audience}",
            f"- Goal: {options.goal}",
            f"- Voice: {options.voice}",
            f"- CTA Strength: {options.cta_strength}",
            f"- Hashtag Count: {options.hashtag_count}",
            "- Follow these controls explicitly while keeping the post natural and readable.",
            f"- Goal rule: {_goal_instruction(options.goal)}",
            f"- Voice rule: {_voice_instruction(options.voice)}",
            f"- CTA rule: {_cta_instruction(options.cta_strength)}",
            f"- Hashtag rule: {_hashtag_instruction(options.hashtag_count)}",
        ]
    )


def _append_examples(
    prompt_parts: list[str],
    *,
    section_number: int,
    examples: Iterable[dict[str, Any]],
) -> None:
    prompt_examples = [
        example
        for example in list(examples)[:MAX_EXAMPLES]
        if str(example.get("text", "")).strip()
    ]
    if not prompt_examples:
        return

    prompt_parts.append(f"{section_number}) Use the writing style as per the following examples.")
    for index, example in enumerate(prompt_examples, start=1):
        text = str(example.get("text", "")).strip()
        match_label = str(example.get("match_label", "")).strip()
        example_heading = f"Example {index}"
        if match_label:
            example_heading += f" ({match_label})"
        prompt_parts.extend(["", example_heading, text])


def _split_trailing_hashtags(text: str) -> tuple[str, str]:
    """Split trailing hashtags from the main body when present."""

    match = TRAILING_HASHTAGS_PATTERN.match(text.strip())
    if match is None:
        return text.strip(), ""

    body = (match.group("body") or "").strip()
    hashtags = " ".join(re.findall(r"#\w+", match.group("hashtags") or ""))
    return body, hashtags


def _split_chunks(text: str, pattern: re.Pattern[str]) -> list[str]:
    """Split text into non-empty chunks using a punctuation-aware pattern."""

    return [chunk.strip() for chunk in pattern.split(text) if chunk.strip()]


def _compact_variant_spacing(text: str) -> str:
    """Remove blank spacer lines while preserving meaningful line breaks."""

    normalized = normalize_post_text(text, preserve_lines=True)
    lines = [
        normalize_post_text(line, preserve_lines=False)
        for line in normalized.splitlines()
    ]
    return "\n".join(line for line in lines if line)


def _reflow_single_paragraph(text: str, *, length: str) -> str:
    """Conservatively reflow a long single paragraph into LinkedIn-style lines."""

    body = normalize_post_text(text, preserve_lines=False)
    if not body:
        return ""

    sentence_chunks = _split_chunks(body, SENTENCE_SPLIT_PATTERN)
    if len(sentence_chunks) > 1:
        return "\n".join(sentence_chunks)

    clause_chunks = _split_chunks(body, CLAUSE_SPLIT_PATTERN)
    if len(clause_chunks) > 1:
        return "\n".join(clause_chunks)

    if len(body) < 90:
        return body

    width = {
        "Short": 48,
        "Medium": 60,
        "Long": 72,
    }[length]
    wrapped = wrap(body, width=width, break_long_words=False, break_on_hyphens=False)
    return "\n".join(chunk.strip() for chunk in wrapped if chunk.strip())


def _normalize_variant_text(text: str, *, length: str) -> str:
    """Normalize a generated variant while preserving meaning and improving layout."""

    normalized = _compact_variant_spacing(text)
    if not normalized:
        return ""

    body, hashtags = _split_trailing_hashtags(normalized)
    body_lines = [line.strip() for line in body.splitlines() if line.strip()]
    if len(body_lines) <= 1:
        body = _reflow_single_paragraph(body, length=length)

    rebuilt = _compact_variant_spacing(body)
    if hashtags:
        rebuilt = f"{rebuilt}\n{hashtags}" if rebuilt else hashtags
    return _compact_variant_spacing(rebuilt)


def build_prompt(
    length: str,
    language: str,
    tag: str,
    examples: Iterable[dict[str, Any]],
    *,
    options: GenerationOptions | None = None,
) -> str:
    """Build the generation prompt for the requested post."""

    resolved_options = _resolve_options(options)
    length_description = get_length_str(length)
    prompt_parts = [
        "Generate a LinkedIn post using the below information. No preamble.",
        "",
        f"1) Topic: {tag}",
        f"2) Length: {length} ({length_description})",
        f"3) Language: {language}",
        "If Language is Hinglish then it means it is a mix of Hindi and English.",
        "The script for the generated post should always be English.",
    ]
    _append_style_controls(prompt_parts, section_number=4, options=resolved_options)
    _append_examples(prompt_parts, section_number=5, examples=examples)
    prompt_parts.extend(
        [
            "",
            "6) Output Format:",
            f"- {_line_layout_instruction(length)}",
            "- Keep one short idea per line, with no empty line between every sentence.",
            "- Do not use markdown bullets unless they genuinely improve readability.",
            f"- {_emoji_style_instruction()}",
            "- If hashtags are included, place them alone on the final line only.",
        ]
    )
    return "\n".join(prompt_parts).strip()


def build_variants_prompt(
    length: str,
    language: str,
    tag: str,
    examples: Iterable[dict[str, Any]],
    *,
    options: GenerationOptions | None = None,
    variant_count: int = DEFAULT_VARIANT_COUNT,
) -> str:
    """Build the prompt used to generate three distinct post variants."""

    _validate_variant_count(variant_count)
    resolved_options = _resolve_options(options)
    length_description = get_length_str(length)
    prompt_parts = [
        f"Generate exactly {variant_count} distinct LinkedIn post variants using the below information.",
        "Return only a valid JSON object. No preamble.",
        "",
        f"1) Topic: {tag}",
        f"2) Length: {length} ({length_description})",
        f"3) Language: {language}",
        "If Language is Hinglish then it means it is a mix of Hindi and English.",
        "The script for every generated post should always be English.",
    ]
    _append_style_controls(prompt_parts, section_number=4, options=resolved_options)
    _append_examples(prompt_parts, section_number=5, examples=examples)
    prompt_parts.extend(
        [
            "6) Return Format:",
            f"- {_line_layout_instruction(length)}",
            "- Keep one short idea per line, with no empty line between every sentence.",
            "- Do not use markdown bullets unless they genuinely improve readability.",
            f"- {_emoji_style_instruction()}",
            "- If hashtags are included, place them alone on the final line only.",
            '- Return only a JSON object with exactly one key: "variants".',
            f'- The "variants" value must be an array of exactly {variant_count} non-empty strings.',
            "- Keep the selected tone, audience, goal, voice, CTA, and hashtag rules identical across all variants.",
            f"- Variant 1 must use an {VARIANT_ANGLES[0].lower()}.",
            f"- Variant 2 must use a {VARIANT_ANGLES[1].lower()}.",
            f"- Variant 3 must use an {VARIANT_ANGLES[2].lower()}.",
            "- Make the variants meaningfully different in opening structure and angle, not just minor rewrites.",
        ]
    )
    return "\n".join(prompt_parts).strip()


def get_prompt(
    length: str,
    language: str,
    tag: str,
    repository: FewShotPosts | None = None,
    *,
    options: GenerationOptions | None = None,
) -> str:
    """Compatibility wrapper that builds the prompt from stored examples."""

    examples_repo = repository or get_default_repository()
    examples = examples_repo.get_prompt_examples(length, language, tag, limit=MAX_EXAMPLES)
    return build_prompt(length, language, tag, examples, options=options)


def get_variants_prompt(
    length: str,
    language: str,
    tag: str,
    repository: FewShotPosts | None = None,
    *,
    options: GenerationOptions | None = None,
    variant_count: int = DEFAULT_VARIANT_COUNT,
) -> str:
    """Build the prompt for multi-variant generation from stored examples."""

    examples_repo = repository or get_default_repository()
    examples = examples_repo.get_prompt_examples(length, language, tag, limit=MAX_EXAMPLES)
    return build_variants_prompt(
        length,
        language,
        tag,
        examples,
        options=options,
        variant_count=variant_count,
    )


def _escape_json_string_control_chars(candidate: str) -> str:
    """Escape invalid raw control characters that appear inside JSON strings."""

    repaired: list[str] = []
    in_string = False
    escaped = False
    index = 0
    while index < len(candidate):
        char = candidate[index]

        if not in_string:
            if char == '"':
                in_string = True
            repaired.append(char)
            index += 1
            continue

        if escaped:
            repaired.append(char)
            escaped = False
            index += 1
            continue

        if char == "\\":
            repaired.append(char)
            escaped = True
        elif char == '"':
            repaired.append(char)
            in_string = False
        elif char == "\r":
            repaired.append("\\n")
            if index + 1 < len(candidate) and candidate[index + 1] == "\n":
                index += 1
        elif char == "\n":
            repaired.append("\\n")
        elif char == "\t":
            repaired.append("\\t")
        elif char == "\b":
            repaired.append("\\b")
        elif char == "\f":
            repaired.append("\\f")
        elif ord(char) < 0x20:
            repaired.append(f"\\u{ord(char):04x}")
        else:
            repaired.append(char)
        index += 1

    return "".join(repaired)


def _parse_json_object(raw_text: str) -> dict[str, Any]:
    """Parse a JSON object from model output, allowing fenced JSON."""

    cleaned_text = raw_text.strip()
    candidates = [cleaned_text]

    fenced_match = re.match(
        r"^```(?:json)?\s*(?P<body>[\s\S]*?)\s*```$",
        cleaned_text,
        flags=re.IGNORECASE,
    )
    if fenced_match:
        candidates.append(fenced_match.group("body").strip())

    start_index = cleaned_text.find("{")
    end_index = cleaned_text.rfind("}")
    if start_index != -1 and end_index != -1 and start_index < end_index:
        candidates.append(cleaned_text[start_index : end_index + 1].strip())

    parse_error: json.JSONDecodeError | None = None
    for candidate in dict.fromkeys(candidates):
        repaired_candidate = _escape_json_string_control_chars(candidate)
        for parse_candidate in dict.fromkeys([candidate, repaired_candidate]):
            try:
                payload = json.loads(parse_candidate)
            except json.JSONDecodeError as error:
                parse_error = error
                continue
            if not isinstance(payload, dict):
                raise ValueError(f"Expected a JSON object, got {type(payload).__name__}.")
            return payload

    raise ValueError(f"Failed to parse variants JSON from model output: {raw_text}") from parse_error


def _parse_variants_response(raw_text: str, *, variant_count: int) -> list[str]:
    """Validate and extract generated variants from model JSON output."""

    _validate_variant_count(variant_count)
    payload = _parse_json_object(raw_text)
    if set(payload) != {"variants"}:
        raise ValueError('Variants response must contain exactly one key: "variants".')

    variants = payload["variants"]
    if not isinstance(variants, list):
        raise ValueError('The "variants" field must be a list.')
    if len(variants) != variant_count:
        raise ValueError(f'Expected exactly {variant_count} variants, got {len(variants)}.')

    normalized_variants = [str(variant).strip() for variant in variants]
    if any(not variant for variant in normalized_variants):
        raise ValueError("All generated variants must be non-empty strings.")
    return normalized_variants


def generate_post(
    length: str,
    language: str,
    tag: str,
    *,
    options: GenerationOptions | None = None,
    llm_client: Any | None = None,
    repository: FewShotPosts | None = None,
) -> str:
    """Generate a single LinkedIn post for the requested attributes."""

    prompt = get_prompt(length, language, tag, repository=repository, options=options)
    client = llm_client or get_llm()
    response = client.invoke(prompt)
    return _normalize_variant_text(extract_response_text(response), length=length)


def generate_post_variants(
    length: str,
    language: str,
    tag: str,
    *,
    options: GenerationOptions | None = None,
    llm_client: Any | None = None,
    repository: FewShotPosts | None = None,
    variant_count: int = DEFAULT_VARIANT_COUNT,
) -> list[str]:
    """Generate multiple prompt-controlled LinkedIn post variants."""

    prompt = get_variants_prompt(
        length,
        language,
        tag,
        repository=repository,
        options=options,
        variant_count=variant_count,
    )
    client = llm_client or get_llm()
    response = client.invoke(prompt)
    parsed_variants = _parse_variants_response(
        extract_response_text(response),
        variant_count=variant_count,
    )
    return [_normalize_variant_text(variant, length=length) for variant in parsed_variants]
