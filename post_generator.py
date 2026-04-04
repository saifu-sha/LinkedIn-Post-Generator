"""Compatibility wrapper for LinkedIn post generation helpers."""

from linkedin_post_generator.generator import (
    build_prompt,
    generate_post,
    get_length_str,
    get_prompt,
)

__all__ = ["build_prompt", "generate_post", "get_length_str", "get_prompt"]


if __name__ == "__main__":
    print(generate_post("Medium", "English", "IoT"))
