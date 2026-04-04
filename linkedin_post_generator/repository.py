"""Read and filter processed LinkedIn post examples without pandas."""

from __future__ import annotations

import json
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import get_paths
from .models import ProcessedPost
from .quality import build_text_fingerprint, is_low_quality_post, score_post_example

MATCH_LABELS = {
    "exact_match": "Exact match",
    "same_tag_same_language": "Same tag and language; length relaxed",
    "same_tag_any_language": "Same tag; language and length relaxed",
    "global_best": "Global fallback",
}


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
        self.unique_tags = sorted(
            {
                tag
                for post in self.posts
                if not is_low_quality_post(post.text)
                for tag in post.tags
            }
        )

    def get_tags(self) -> list[str]:
        """Return all available tags in sorted order."""

        return list(self.unique_tags)

    def _rank_posts(self, posts: list[ProcessedPost]) -> list[ProcessedPost]:
        """Deduplicate and rank candidate posts by example quality."""

        best_by_fingerprint: dict[str, tuple[float, int, int, ProcessedPost]] = {}
        for post in posts:
            fingerprint = build_text_fingerprint(post.text)
            if not fingerprint:
                continue

            score = score_post_example(
                post.text,
                engagement=post.engagement,
                tags=post.tags,
                line_count=post.line_count,
            )
            ranking = (score, post.engagement, len(post.text))
            current_best = best_by_fingerprint.get(fingerprint)
            if current_best is None or ranking > current_best[:3]:
                best_by_fingerprint[fingerprint] = (*ranking, post)

        ranked_posts = sorted(
            best_by_fingerprint.values(),
            key=lambda item: item[:3],
            reverse=True,
        )
        return [post for _, _, _, post in ranked_posts]

    def _get_exact_match_posts(self, length: str, language: str, tag: str) -> list[ProcessedPost]:
        """Return exact-match usable posts before serialization."""

        return [
            post
            for post in self.posts
            if post.language == language
            and categorize_length(post.line_count) == length
            and tag in post.tags
            and not is_low_quality_post(post.text)
        ]

    def get_filtered_posts(self, length: str, language: str, tag: str) -> list[dict[str, Any]]:
        """Return posts matching the requested length, language, and tag."""

        ranked_posts = self._rank_posts(
            self._get_exact_match_posts(length, language, tag)
        )
        return [asdict(post) for post in ranked_posts]

    def get_prompt_examples(
        self,
        length: str,
        language: str,
        tag: str,
        *,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Return prompt-ready examples with fallback provenance."""

        if limit <= 0:
            return []

        tiered_candidates = [
            (
                "exact_match",
                self._get_exact_match_posts(length, language, tag),
            ),
            (
                "same_tag_same_language",
                [
                    post
                    for post in self.posts
                    if post.language == language
                    and tag in post.tags
                    and not is_low_quality_post(post.text)
                ],
            ),
            (
                "same_tag_any_language",
                [
                    post
                    for post in self.posts
                    if tag in post.tags
                    and not is_low_quality_post(post.text)
                ],
            ),
            (
                "global_best",
                [
                    post
                    for post in self.posts
                    if not is_low_quality_post(post.text)
                ],
            ),
        ]

        selected_examples: list[dict[str, Any]] = []
        seen_fingerprints: set[str] = set()
        for match_tier, candidates in tiered_candidates:
            for post in self._rank_posts(candidates):
                fingerprint = build_text_fingerprint(post.text)
                if not fingerprint or fingerprint in seen_fingerprints:
                    continue

                seen_fingerprints.add(fingerprint)
                selected_examples.append(
                    {
                        **asdict(post),
                        "match_tier": match_tier,
                        "match_label": MATCH_LABELS[match_tier],
                    }
                )
                if len(selected_examples) >= limit:
                    return selected_examples

        return selected_examples


@lru_cache(maxsize=1)
def get_default_repository() -> FewShotPosts:
    """Return a cached repository for the default processed posts file."""

    return FewShotPosts()
