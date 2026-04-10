"""Shared dataclasses for post and scraper data."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from .quality import normalize_post_text

SUPPORTED_LANGUAGES = {"English", "Hinglish"}
GENERATION_TONE_OPTIONS = ("Professional", "Conversational", "Bold")
GENERATION_AUDIENCE_OPTIONS = ("General", "Job Seekers", "Founders", "Developers")
GENERATION_GOAL_OPTIONS = ("Match examples", "Educate", "Inspire", "Announce")
GENERATION_VOICE_OPTIONS = ("Match examples", "First Person", "Brand/Company")
GENERATION_CTA_STRENGTH_OPTIONS = ("None", "Soft", "Strong")


def normalize_tags(value: Any) -> list[str]:
    """Normalize a tag value into a list of unique, non-empty strings."""

    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = [str(value)]

    tags: list[str] = []
    for item in items:
        tag = str(item).strip()
        if tag and tag not in tags:
            tags.append(tag)
    return tags


def coerce_int(value: Any, *, default: int = 0) -> int:
    """Convert a value to int and fall back to a default on failure."""

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True, slots=True)
class GenerationOptions:
    """Typed controls used to shape generation prompts."""

    tone: str = "Professional"
    audience: str = "General"
    goal: str = "Match examples"
    voice: str = "Match examples"
    cta_strength: str = "None"
    hashtag_count: int = 0

    def __post_init__(self) -> None:
        self._validate_choice("tone", self.tone, GENERATION_TONE_OPTIONS)
        self._validate_choice("audience", self.audience, GENERATION_AUDIENCE_OPTIONS)
        self._validate_choice("goal", self.goal, GENERATION_GOAL_OPTIONS)
        self._validate_choice("voice", self.voice, GENERATION_VOICE_OPTIONS)
        self._validate_choice(
            "cta_strength",
            self.cta_strength,
            GENERATION_CTA_STRENGTH_OPTIONS,
        )
        if not isinstance(self.hashtag_count, int) or not 0 <= self.hashtag_count <= 3:
            raise ValueError("hashtag_count must be an integer between 0 and 3.")

    @staticmethod
    def _validate_choice(name: str, value: str, options: tuple[str, ...]) -> None:
        if value not in options:
            raise ValueError(f"Unsupported {name} {value!r}.")


@dataclass(slots=True)
class PostRecord:
    """A raw LinkedIn post and its engagement count."""

    text: str
    engagement: int = 0

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], *, index: int | None = None) -> "PostRecord":
        """Create a raw post from a JSON record."""

        text = normalize_post_text(data.get("text", ""))
        if not text:
            location = f" at index {index}" if index is not None else ""
            raise ValueError(f"Missing post text{location}.")
        return cls(text=text, engagement=coerce_int(data.get("engagement", 0), default=0))

    def to_dict(self) -> dict[str, Any]:
        """Convert the post into a JSON-serializable dictionary."""

        return asdict(self)


@dataclass(slots=True)
class ProcessedPost:
    """A post enriched with metadata used for prompt examples."""

    text: str
    engagement: int = 0
    line_count: int = 0
    language: str = "English"
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_mapping(
        cls,
        data: Mapping[str, Any],
        *,
        index: int | None = None,
    ) -> "ProcessedPost":
        """Create a processed post from a JSON record."""

        raw_post = PostRecord.from_mapping(data, index=index)
        language = str(data.get("language", "English")).strip() or "English"
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language {language!r}.")
        return cls(
            text=raw_post.text,
            engagement=raw_post.engagement,
            line_count=coerce_int(data.get("line_count", 0), default=0),
            language=language,
            tags=normalize_tags(data.get("tags", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert the processed post into a JSON-serializable dictionary."""

        return asdict(self)
