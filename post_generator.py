"""Compatibility wrapper for LinkedIn post generation helpers."""

from linkedin_post_generator.generator import (
    build_prompt,
    build_variants_prompt,
    generate_post,
    generate_post_variants,
    get_length_str,
    get_prompt,
    get_variants_prompt,
)
from linkedin_post_generator.models import GenerationOptions

__all__ = [
    "GenerationOptions",
    "build_prompt",
    "build_variants_prompt",
    "generate_post",
    "generate_post_variants",
    "get_length_str",
    "get_prompt",
    "get_variants_prompt",
]


if __name__ == "__main__":
    print(generate_post("Medium", "English", "IoT"))
