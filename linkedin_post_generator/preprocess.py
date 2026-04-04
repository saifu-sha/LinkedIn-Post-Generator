"""Metadata extraction and JSON enrichment for scraped posts."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from .config import get_paths
from .llm import extract_response_text, get_llm
from .models import PostRecord, ProcessedPost, SUPPORTED_LANGUAGES, normalize_tags


class LLMResponseError(ValueError):
    """Raised when the model returns invalid or incomplete JSON."""


def build_metadata_prompt(post: str) -> str:
    """Build the prompt used to extract metadata from a post."""

    return (
        "You are given a LinkedIn post. You need to extract number of lines, "
        "language of the post and tags.\n"
        "1. Return a valid JSON. No preamble.\n"
        "2. JSON object should have exactly three keys: line_count, language and tags.\n"
        "3. tags is an array of text tags. Extract maximum two tags.\n"
        '4. Language should be "English" or "Hinglish" (Hinglish means Hindi + English).\n\n'
        "Here is the actual post on which you need to perform this task:\n"
        f"{post}"
    )


def build_unified_tags_prompt(tags: Iterable[str]) -> str:
    """Build the prompt used to normalize extracted tags."""

    unique_tags = ", ".join(sorted({tag.strip() for tag in tags if tag and tag.strip()}))
    return (
        "I will give you a list of tags. You need to unify tags with the following requirements:\n"
        "1. Merge similar tags into a shorter unified list. Examples:\n"
        "   - Jobseekers, Job Hunting -> Job Search\n"
        "   - Motivation, Inpiration, Drive -> Motivation\n"
        "   - Personal Growth, Personal Development, Self Improvement -> Self Improvement\n"
        "   - Scam Alert, Job Scam -> Scams\n"
        '2. Each output tag must follow Title Case (e.g. "Job Search").\n'
        "3. Output only a JSON object (no explanation or preamble).\n"
        "4. The JSON object should map each original tag to its unified tag.\n\n"
        "Here is the list of tags:\n"
        f"{unique_tags}"
    )


def parse_json_object(raw_text: str) -> dict[str, Any]:
    """Parse a JSON object from model output."""

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

    payload: Any | None = None
    parse_error: json.JSONDecodeError | None = None
    for candidate in dict.fromkeys(candidates):
        try:
            payload = json.loads(candidate)
            break
        except json.JSONDecodeError as error:
            parse_error = error
    else:
        raise LLMResponseError(
            f"Failed to parse model output as JSON. Model output:\n{raw_text}"
        ) from parse_error

    if not isinstance(payload, dict):
        raise LLMResponseError(f"Expected a JSON object, got {type(payload).__name__}.")
    return payload


def invoke_json_prompt(prompt: str, *, llm_client: Any | None = None) -> dict[str, Any]:
    """Execute a prompt and parse the response as JSON."""

    client = llm_client or get_llm()
    response = client.invoke(prompt)
    return parse_json_object(extract_response_text(response))


def _validate_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    expected_keys = {"line_count", "language", "tags"}
    if set(payload) != expected_keys:
        raise LLMResponseError(
            f"Metadata response must contain exactly {sorted(expected_keys)}, got {sorted(payload)}."
        )

    language = str(payload["language"]).strip()
    if language not in SUPPORTED_LANGUAGES:
        raise LLMResponseError(f"Unsupported language {language!r} returned by the model.")

    return {
        "line_count": int(payload["line_count"]),
        "language": language,
        "tags": normalize_tags(payload["tags"])[:2],
    }


def extract_metadata(post: str, *, llm_client: Any | None = None) -> dict[str, Any]:
    """Extract line count, language, and tags for a post."""

    prompt = build_metadata_prompt(post)
    payload = invoke_json_prompt(prompt, llm_client=llm_client)
    return _validate_metadata(payload)


def get_unified_tags(
    posts_with_metadata: Iterable[dict[str, Any]],
    *,
    llm_client: Any | None = None,
) -> dict[str, str]:
    """Generate a mapping from raw tags to unified tags."""

    all_tags: list[str] = []
    for post in posts_with_metadata:
        all_tags.extend(normalize_tags(post.get("tags", [])))

    if not all_tags:
        return {}

    payload = invoke_json_prompt(
        build_unified_tags_prompt(all_tags),
        llm_client=llm_client,
    )
    return {str(key): str(value).strip() for key, value in payload.items() if str(value).strip()}


def process_posts(
    raw_file_path: str | Path,
    processed_file_path: str | Path | None = None,
    *,
    llm_client: Any | None = None,
) -> list[dict[str, Any]]:
    """Read raw posts, enrich them with metadata, and persist the processed dataset."""

    source_path = Path(raw_file_path)
    target_path = Path(processed_file_path) if processed_file_path is not None else get_paths().processed_posts_path

    with source_path.open(encoding="utf-8") as file:
        payload = json.load(file)

    if not isinstance(payload, list):
        raise ValueError("Raw posts JSON must contain a list of posts.")

    enriched_posts: list[dict[str, Any]] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"Raw post at index {index} is not an object.")

        raw_post = PostRecord.from_mapping(item, index=index)
        metadata = extract_metadata(raw_post.text, llm_client=llm_client)
        processed_post = ProcessedPost(
            text=raw_post.text,
            engagement=raw_post.engagement,
            line_count=metadata["line_count"],
            language=metadata["language"],
            tags=metadata["tags"],
        )
        enriched_posts.append(processed_post.to_dict())

    unified_tags = get_unified_tags(enriched_posts, llm_client=llm_client)
    for post in enriched_posts:
        normalized_tags = [unified_tags.get(tag, tag) for tag in normalize_tags(post.get("tags", []))]
        post["tags"] = list(dict.fromkeys(normalized_tags))

    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open(encoding="utf-8", mode="w") as outfile:
        json.dump(enriched_posts, outfile, ensure_ascii=False, indent=4)

    return enriched_posts
