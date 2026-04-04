"""Streamlit user interface for the LinkedIn post generator."""

from __future__ import annotations

import streamlit as st

from .config import get_paths
from .generator import LANGUAGE_OPTIONS, LENGTH_OPTIONS, generate_post
from .repository import FewShotPosts


@st.cache_resource(show_spinner=False)
def load_repository(file_path: str) -> FewShotPosts:
    """Cache and return the processed-post repository for the UI."""

    return FewShotPosts(file_path)


def main() -> None:
    """Render the Streamlit application."""

    st.title("LinkedIn Post Generator")
    processed_posts_path = str(get_paths().processed_posts_path)

    try:
        repository = load_repository(processed_posts_path)
    except FileNotFoundError:
        st.error(
            "Processed posts file was not found. Run the preprocessing step before generating posts."
        )
        return
    except ValueError as error:
        st.error(f"Processed posts could not be loaded: {error}")
        return

    available_tags = repository.get_tags()
    if not available_tags:
        st.warning("No tags are available in the processed posts dataset.")
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        selected_tag = st.selectbox("Title", options=available_tags)
    with col2:
        selected_length = st.selectbox("Length", options=LENGTH_OPTIONS)
    with col3:
        selected_language = st.selectbox("Language", options=LANGUAGE_OPTIONS)

    if st.button("Generate"):
        with st.spinner("Generating post..."):
            try:
                post = generate_post(
                    selected_length,
                    selected_language,
                    selected_tag,
                    repository=repository,
                )
            except (RuntimeError, ValueError) as error:
                st.error(f"Post generation failed: {error}")
                return

        st.write(post)
