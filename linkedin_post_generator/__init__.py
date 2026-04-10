"""Core package for the LinkedIn post generator project."""

from .generator import (
    build_variants_prompt,
    generate_post,
    generate_post_variants,
    get_length_str,
    get_prompt,
    get_variants_prompt,
)
from .models import GenerationOptions
from .repository import FewShotPosts

__all__ = [
    "FewShotPosts",
    "GenerationOptions",
    "build_variants_prompt",
    "generate_post",
    "generate_post_variants",
    "get_length_str",
    "get_prompt",
    "get_variants_prompt",
]
