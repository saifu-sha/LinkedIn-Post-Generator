"""Helpers for creating and interacting with the Groq-backed LLM."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from .config import DEFAULT_GROQ_MODEL, load_environment


class LazyLLM:
    """Lazy compatibility wrapper that resolves the LLM on first use."""

    def __init__(self) -> None:
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = get_llm()
        return self._client

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        """Proxy invoke calls to the lazily-created client."""

        return self._get_client().invoke(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._get_client(), name)


@lru_cache(maxsize=1)
def get_llm(model: str = DEFAULT_GROQ_MODEL) -> Any:
    """Create the configured Groq chat model."""

    load_environment()
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set in the environment.")

    from langchain_groq import ChatGroq

    return ChatGroq(groq_api_key=api_key, model=model)


def extract_response_text(response: Any) -> str:
    """Normalize LLM responses into plain text."""

    for attr in ("content", "text"):
        value = getattr(response, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return str(response).strip()
