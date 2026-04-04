"""Compatibility wrapper exposing a lazy `llm` object."""

from linkedin_post_generator.llm import LazyLLM, get_llm

llm = LazyLLM()

__all__ = ["LazyLLM", "get_llm", "llm"]
