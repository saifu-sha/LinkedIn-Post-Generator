"""Core package for the LinkedIn post generator project."""

from .generator import generate_post, get_length_str, get_prompt
from .repository import FewShotPosts

__all__ = ["FewShotPosts", "generate_post", "get_length_str", "get_prompt"]
