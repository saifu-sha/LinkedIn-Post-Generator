"""Prompt construction and post generation logic."""

from __future__ import annotations

from typing import Any, Iterable

from .llm import extract_response_text, get_llm
from .repository import FewShotPosts, get_default_repository

LENGTH_OPTIONS = ["Short", "Medium", "Long"]
LANGUAGE_OPTIONS = ["English", "Hinglish"]
LENGTH_TO_DESCRIPTION = {
    "Short": "1 to 5 lines",
    "Medium": "6 to 10 lines",
    "Long": "11 to 15 lines",
}
MAX_EXAMPLES = 5


def get_length_str(length: str) -> str:
    """Return the line-count description for a UI length bucket."""

    try:
        return LENGTH_TO_DESCRIPTION[length]
    except KeyError as error:
        raise ValueError(f"Unsupported length {length!r}.") from error


def build_prompt(length: str, language: str, tag: str, examples: Iterable[dict[str, Any]]) -> str:
    """Build the generation prompt for the requested post."""

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

    prompt_examples = [
        example
        for example in list(examples)[:MAX_EXAMPLES]
        if str(example.get("text", "")).strip()
    ]
    if prompt_examples:
        prompt_parts.append("4) Use the writing style as per the following examples.")
        for index, example in enumerate(prompt_examples, start=1):
            text = str(example.get("text", "")).strip()
            match_label = str(example.get("match_label", "")).strip()
            example_heading = f"Example {index}"
            if match_label:
                example_heading += f" ({match_label})"
            prompt_parts.append("")
            prompt_parts.append(example_heading)
            prompt_parts.append(text)

    return "\n".join(prompt_parts).strip()


def get_prompt(length: str, language: str, tag: str, repository: FewShotPosts | None = None) -> str:
    """Compatibility wrapper that builds the prompt from stored examples."""

    examples_repo = repository or get_default_repository()
    examples = examples_repo.get_prompt_examples(length, language, tag, limit=MAX_EXAMPLES)
    return build_prompt(length, language, tag, examples)


def generate_post(
    length: str,
    language: str,
    tag: str,
    *,
    llm_client: Any | None = None,
    repository: FewShotPosts | None = None,
) -> str:
    """Generate a LinkedIn post for the requested attributes."""

    prompt = get_prompt(length, language, tag, repository=repository)
    client = llm_client or get_llm()
    response = client.invoke(prompt)
    return extract_response_text(response)
