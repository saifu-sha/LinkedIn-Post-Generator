"""Metadata extraction and JSON enrichment for scraped posts."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Iterable, TypeVar

from .config import get_paths
from .llm import extract_response_text, get_llm
from .models import PostRecord, ProcessedPost, SUPPORTED_LANGUAGES, normalize_tags
from .quality import (
    build_text_preview,
    get_low_quality_reason,
    sanitize_post_text,
)

DEFAULT_MAX_RETRIES = 3
T = TypeVar("T")


class LLMResponseError(ValueError):
    """Raised when the model returns invalid or incomplete JSON."""


class LLMInvocationError(RuntimeError):
    """Raised when an LLM call fails before a response can be parsed."""


class LowQualityPostError(ValueError):
    """Raised when a post is filtered out for low data quality."""


RETRYABLE_PREPROCESSING_ERRORS = (LLMResponseError, LLMInvocationError)


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
    try:
        response = client.invoke(prompt)
    except Exception as error:
        raise LLMInvocationError(f"LLM invocation failed: {error}") from error
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

    try:
        line_count = int(payload["line_count"])
    except (TypeError, ValueError) as error:
        raise LLMResponseError("Metadata response contained a non-integer line_count.") from error

    return {
        "line_count": line_count,
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


def _build_sidecar_path(target_path: Path, label: str) -> Path:
    """Build a sidecar JSON path beside the processed output."""

    return target_path.with_name(f"{target_path.stem}.{label}.json")


def _load_checkpoint(checkpoint_path: Path) -> dict[int, dict[str, Any]]:
    """Load checkpointed successful records indexed by source position."""

    if not checkpoint_path.exists():
        return {}

    with checkpoint_path.open(encoding="utf-8") as file:
        payload = json.load(file)

    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise ValueError("Checkpoint file is malformed; expected an object with a 'records' list.")

    checkpointed_posts: dict[int, dict[str, Any]] = {}
    for item in payload["records"]:
        if not isinstance(item, dict) or "index" not in item or "post" not in item:
            raise ValueError("Checkpoint record is malformed.")
        index = int(item["index"])
        checkpointed_posts[index] = ProcessedPost.from_mapping(item["post"], index=index).to_dict()
    return checkpointed_posts


def _write_checkpoint(checkpoint_path: Path, checkpointed_posts: dict[int, dict[str, Any]]) -> None:
    """Write checkpointed successful records to disk."""

    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "records": [
            {"index": index, "post": checkpointed_posts[index]}
            for index in sorted(checkpointed_posts)
        ]
    }
    with checkpoint_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def _write_failures_report(failures_path: Path, failures: list[dict[str, Any]]) -> None:
    """Write the preprocessing failures report to disk."""

    failures_path.parent.mkdir(parents=True, exist_ok=True)
    with failures_path.open("w", encoding="utf-8") as file:
        json.dump(failures, file, ensure_ascii=False, indent=2)


def _build_failure_record(
    index: int | None,
    *,
    stage: str,
    reason: str,
    text: str,
    error: BaseException | None = None,
    attempts: int | None = None,
) -> dict[str, Any]:
    """Build a structured failure record for the sidecar report."""

    return {
        "index": index,
        "stage": stage,
        "reason": reason,
        "error_type": type(error).__name__ if error is not None else "",
        "error_message": str(error) if error is not None else "",
        "attempts": attempts,
        "text_preview": build_text_preview(text),
    }


def _run_with_retries(operation: Callable[[], T], *, max_retries: int) -> tuple[T, int]:
    """Run a retryable operation and return its result plus attempt count."""

    attempts = max(max_retries, 0) + 1
    for attempt in range(1, attempts + 1):
        try:
            return operation(), attempt
        except RETRYABLE_PREPROCESSING_ERRORS:
            if attempt == attempts:
                raise
    raise RuntimeError("Retry loop exited unexpectedly.")


def process_posts(
    raw_file_path: str | Path,
    processed_file_path: str | Path | None = None,
    *,
    llm_client: Any | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    resume: bool = True,
    checkpoint_file_path: str | Path | None = None,
    failures_file_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Read raw posts, enrich them with metadata, and persist the processed dataset."""

    source_path = Path(raw_file_path)
    target_path = (
        Path(processed_file_path)
        if processed_file_path is not None
        else get_paths().processed_posts_path
    )
    checkpoint_path = (
        Path(checkpoint_file_path)
        if checkpoint_file_path is not None
        else _build_sidecar_path(target_path, "checkpoint")
    )
    failures_path = (
        Path(failures_file_path)
        if failures_file_path is not None
        else _build_sidecar_path(target_path, "failures")
    )

    with source_path.open(encoding="utf-8") as file:
        payload = json.load(file)

    if not isinstance(payload, list):
        raise ValueError("Raw posts JSON must contain a list of posts.")

    checkpointed_posts = _load_checkpoint(checkpoint_path) if resume else {}
    successful_posts = {
        index: post
        for index, post in checkpointed_posts.items()
        if 0 <= index < len(payload)
    }
    failures: list[dict[str, Any]] = []

    for index, item in enumerate(payload):
        if index in successful_posts:
            continue
        if not isinstance(item, dict):
            raise ValueError(f"Raw post at index {index} is not an object.")

        raw_post = PostRecord.from_mapping(item, index=index)
        low_quality_reason = get_low_quality_reason(raw_post.text)
        if low_quality_reason is not None:
            failures.append(
                _build_failure_record(
                    index,
                    stage="quality_filter",
                    reason="filtered_low_quality",
                    text=raw_post.text,
                    error=LowQualityPostError(low_quality_reason),
                    attempts=1,
                )
            )
            continue

        cleaned_text = sanitize_post_text(raw_post.text)
        try:
            metadata, _ = _run_with_retries(
                lambda: extract_metadata(cleaned_text, llm_client=llm_client),
                max_retries=max_retries,
            )
        except RETRYABLE_PREPROCESSING_ERRORS as error:
            failures.append(
                _build_failure_record(
                    index,
                    stage="metadata_extraction",
                    reason="retry_exhausted",
                    text=raw_post.text,
                    error=error,
                    attempts=max(max_retries, 0) + 1,
                )
            )
            continue

        processed_post = ProcessedPost(
            text=cleaned_text,
            engagement=raw_post.engagement,
            line_count=metadata["line_count"],
            language=metadata["language"],
            tags=metadata["tags"],
        )
        successful_posts[index] = processed_post.to_dict()
        _write_checkpoint(checkpoint_path, successful_posts)

    unified_tags: dict[str, str] = {}
    if successful_posts:
        try:
            unified_tags, _ = _run_with_retries(
                lambda: get_unified_tags(successful_posts.values(), llm_client=llm_client),
                max_retries=max_retries,
            )
        except RETRYABLE_PREPROCESSING_ERRORS as error:
            failures.append(
                _build_failure_record(
                    None,
                    stage="tag_unification",
                    reason="retry_exhausted",
                    text="",
                    error=error,
                    attempts=max(max_retries, 0) + 1,
                )
            )

    retained_checkpoint_posts: dict[int, dict[str, Any]] = {}
    final_posts: list[dict[str, Any]] = []
    for index in sorted(successful_posts):
        checkpoint_post = successful_posts[index]
        cleaned_text = sanitize_post_text(checkpoint_post.get("text", ""))
        low_quality_reason = get_low_quality_reason(cleaned_text or checkpoint_post.get("text", ""))
        if low_quality_reason is not None:
            failures.append(
                _build_failure_record(
                    index,
                    stage="final_quality_filter",
                    reason="filtered_low_quality",
                    text=cleaned_text,
                    error=LowQualityPostError(low_quality_reason),
                    attempts=1,
                )
            )
            continue

        retained_checkpoint_posts[index] = checkpoint_post
        normalized_tags = [
            unified_tags.get(tag, tag)
            for tag in normalize_tags(checkpoint_post.get("tags", []))
        ]
        final_posts.append(
            {
                **checkpoint_post,
                "text": cleaned_text,
                "tags": list(dict.fromkeys(normalized_tags)),
            }
        )

    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open(encoding="utf-8", mode="w") as outfile:
        json.dump(final_posts, outfile, ensure_ascii=False, indent=4)

    _write_checkpoint(checkpoint_path, retained_checkpoint_posts)
    _write_failures_report(failures_path, failures)
    return final_posts
