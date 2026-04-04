"""Compatibility wrapper for preprocessing raw LinkedIn posts."""

from linkedin_post_generator.preprocess import (
    LLMResponseError,
    build_metadata_prompt,
    build_unified_tags_prompt,
    extract_metadata,
    get_unified_tags,
    process_posts,
)

__all__ = [
    "LLMResponseError",
    "build_metadata_prompt",
    "build_unified_tags_prompt",
    "extract_metadata",
    "get_unified_tags",
    "process_posts",
]


if __name__ == "__main__":
    process_posts("data/raw_posts.json", "data/processed_posts.json")
