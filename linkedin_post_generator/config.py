"""Project configuration helpers and environment-backed settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_GROQ_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"


@dataclass(frozen=True, slots=True)
class ProjectPaths:
    """Absolute paths used across the project."""

    project_root: Path
    data_dir: Path
    env_file: Path
    raw_posts_path: Path
    processed_posts_path: Path


@dataclass(frozen=True, slots=True)
class ScraperSettings:
    """Environment-backed configuration for the LinkedIn scraper."""

    username: str | None
    password: str | None
    page_url: str | None
    output_path: Path
    scroll_pause_time: float
    max_scrolls: int
    post_load_timeout: int

    def missing_required_env_vars(self) -> list[str]:
        """Return missing required scraper environment variable names."""

        missing: list[str] = []
        if not self.username:
            missing.append("LINKEDIN_USERNAME")
        if not self.password:
            missing.append("LINKEDIN_PASSWORD")
        if not self.page_url:
            missing.append("LINKEDIN_PAGE")
        return missing


@lru_cache(maxsize=1)
def get_paths() -> ProjectPaths:
    """Return project-wide filesystem paths."""

    project_root = Path(__file__).resolve().parent.parent
    data_dir = project_root / "data"
    return ProjectPaths(
        project_root=project_root,
        data_dir=data_dir,
        env_file=project_root / ".env",
        raw_posts_path=data_dir / "raw_posts.json",
        processed_posts_path=data_dir / "processed_posts.json",
    )


def load_environment() -> None:
    """Load environment variables from the project .env file if it exists."""

    load_dotenv(dotenv_path=get_paths().env_file, override=False)


def _getenv_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _getenv_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    try:
        return float(value)
    except ValueError:
        return default


def resolve_path(path_like: str | Path | None, default: Path) -> Path:
    """Resolve a path relative to the project root when needed."""

    if path_like is None:
        return default

    candidate = Path(path_like)
    if candidate.is_absolute():
        return candidate
    return get_paths().project_root / candidate


def get_scraper_settings(output_path: str | Path | None = None) -> ScraperSettings:
    """Build scraper settings from the current environment."""

    load_environment()
    paths = get_paths()
    return ScraperSettings(
        username=os.getenv("LINKEDIN_USERNAME"),
        password=os.getenv("LINKEDIN_PASSWORD"),
        page_url=os.getenv("LINKEDIN_PAGE"),
        output_path=resolve_path(output_path, paths.raw_posts_path),
        scroll_pause_time=_getenv_float("SCROLL_PAUSE_TIME", 0.8),
        max_scrolls=_getenv_int("MAX_SCROLLS", 3),
        post_load_timeout=_getenv_int("POST_LOAD_TIMEOUT", 7),
    )
