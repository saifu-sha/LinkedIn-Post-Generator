"""Read and filter processed LinkedIn post examples without pandas."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import get_paths
from .models import ProcessedPost


def categorize_length(line_count: int) -> str:
    """Map a line count to the UI length buckets."""

    if line_count < 5:
        return "Short"
    if line_count <= 10:
        return "Medium"
    return "Long"


def load_processed_posts(file_path: str | Path | None = None) -> list[ProcessedPost]:
    """Load processed example posts from JSON."""

    path = Path(file_path) if file_path is not None else get_paths().processed_posts_path
    with path.open(encoding="utf-8") as file:
        payload = json.load(file)

    if not isinstance(payload, list):
        raise ValueError("Processed posts JSON must contain a list of posts.")

    return [ProcessedPost.from_mapping(item, index=index) for index, item in enumerate(payload)]


class FewShotPosts:
    """Repository of processed posts used to seed generation prompts."""

    def __init__(self, file_path: str | Path | None = None) -> None:
        self.file_path = Path(file_path) if file_path is not None else get_paths().processed_posts_path
        self.posts = load_processed_posts(self.file_path)
        self.unique_tags = sorted({tag for post in self.posts for tag in post.tags})

    def get_tags(self) -> list[str]:
        """Return all available tags in sorted order."""

        return list(self.unique_tags)

    def get_filtered_posts(self, length: str, language: str, tag: str) -> list[dict[str, Any]]:
        """Return posts matching the requested length, language, and tag."""

        return [
            post.to_dict()
            for post in self.posts
            if post.language == language
            and categorize_length(post.line_count) == length
            and tag in post.tags
        ]


@lru_cache(maxsize=1)
def get_default_repository() -> FewShotPosts:
    """Return a cached repository for the default processed posts file."""

    return FewShotPosts()
