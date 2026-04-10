"""Streamlit user interface for the LinkedIn post generator."""

from __future__ import annotations

import json
from html import escape

import streamlit as st
import streamlit.components.v1 as components

from .config import get_paths
from .generator import (
    AUDIENCE_OPTIONS,
    CTA_STRENGTH_OPTIONS,
    DEFAULT_VARIANT_COUNT,
    GOAL_OPTIONS,
    HASHTAG_COUNT_OPTIONS,
    LANGUAGE_OPTIONS,
    LENGTH_OPTIONS,
    TONE_OPTIONS,
    generate_post_variants,
    VOICE_OPTIONS,
)
from .models import GenerationOptions
from .repository import FewShotPosts
from .ui_presenters import build_brief_chips, build_brief_signature, build_variant_cards

GENERATED_VARIANTS_KEY = "ui_generated_variants"
GENERATED_BRIEF_KEY = "ui_generated_brief"
EDITOR_KEY_PREFIX = "ui_variant_editor_"
HERO_COPY = (
    "Shape the brief quickly, compare all three drafts side by side, and copy the strongest version "
    "without digging through tabs or hidden preview panels."
)
STALE_RESULTS_NOTICE = (
    "These results are from the last generation run. Click Generate 3 Variants to refresh them for the current brief."
)
FAILED_GENERATION_STALE_RESULTS_NOTICE = (
    "The board below still shows your last successful generation. Fix the error above and generate again "
    "to replace those drafts."
)


@st.cache_resource(show_spinner=False)
def load_repository(file_path: str) -> FewShotPosts:
    """Cache and return the processed-post repository for the UI."""

    return FewShotPosts(file_path)


def _configure_page() -> None:
    """Apply page-level layout and premium SaaS styling."""

    st.set_page_config(
        page_title="LinkedIn Post Generator",
        page_icon=":memo:",
        layout="wide",
    )
    st.markdown(
        """
        <style>
            :root {
                --saas-bg: #f4f7fb;
                --saas-surface: rgba(255, 255, 255, 0.92);
                --saas-surface-strong: #ffffff;
                --saas-line: #d9e2ef;
                --saas-line-strong: #bfd0e5;
                --saas-text: #0f172a;
                --saas-muted: #5b667a;
                --saas-accent: #2563eb;
                --saas-accent-strong: #1747c8;
                --saas-accent-soft: rgba(37, 99, 235, 0.09);
                --saas-shadow: 0 16px 40px rgba(15, 23, 42, 0.08);
                --saas-radius-lg: 24px;
                --saas-radius-md: 18px;
                --saas-radius-sm: 14px;
            }

            [data-testid="stAppViewContainer"] {
                background:
                    radial-gradient(circle at top right, rgba(37, 99, 235, 0.10), transparent 30%),
                    radial-gradient(circle at top left, rgba(56, 189, 248, 0.08), transparent 28%),
                    linear-gradient(180deg, #f8fbff 0%, var(--saas-bg) 100%);
                color: var(--saas-text);
            }

            .block-container {
                max-width: 1180px;
                padding-top: 2rem;
                padding-bottom: 4rem;
            }

            h1, h2, h3 {
                color: var(--saas-text);
                letter-spacing: -0.03em;
            }

            .eyebrow {
                color: var(--saas-accent);
                font-size: 0.78rem;
                font-weight: 800;
                letter-spacing: 0.16em;
                margin: 0 0 0.75rem 0;
                text-transform: uppercase;
            }

            .hero-shell {
                background:
                    linear-gradient(135deg, rgba(255, 255, 255, 0.95), rgba(240, 246, 255, 0.92));
                border: 1px solid rgba(37, 99, 235, 0.12);
                border-radius: var(--saas-radius-lg);
                box-shadow: var(--saas-shadow);
                margin-bottom: 1rem;
                padding: 2rem 2.1rem;
            }

            .hero-title {
                font-size: clamp(2rem, 4vw, 3.15rem);
                line-height: 1.02;
                margin: 0;
            }

            .hero-copy,
            .section-copy,
            .muted-copy {
                color: var(--saas-muted);
                font-size: 1rem;
                line-height: 1.65;
                margin: 0.55rem 0 0 0;
            }

            .hero-copy {
                max-width: 760px;
            }

            .metrics-card {
                background: var(--saas-surface);
                border: 1px solid var(--saas-line);
                border-radius: var(--saas-radius-md);
                min-height: 106px;
                padding: 1rem 1.05rem;
            }

            .metrics-label {
                color: var(--saas-muted);
                font-size: 0.76rem;
                font-weight: 800;
                letter-spacing: 0.10em;
                margin: 0;
                text-transform: uppercase;
            }

            .metrics-value {
                color: var(--saas-text);
                font-size: 1.9rem;
                font-weight: 800;
                line-height: 1.12;
                margin: 0.45rem 0 0.2rem 0;
            }

            .metrics-copy {
                color: var(--saas-muted);
                font-size: 0.93rem;
                line-height: 1.45;
                margin: 0;
            }

            .section-title {
                font-size: 1.55rem;
                line-height: 1.1;
                margin: 0;
            }

            .brief-chip-row {
                display: flex;
                flex-wrap: wrap;
                gap: 0.7rem;
                margin: 1.15rem 0 0.1rem 0;
            }

            .brief-chip {
                background: var(--saas-accent-soft);
                border: 1px solid rgba(37, 99, 235, 0.12);
                border-radius: 999px;
                padding: 0.55rem 0.85rem;
            }

            .brief-chip span {
                color: var(--saas-muted);
                display: block;
                font-size: 0.68rem;
                font-weight: 800;
                letter-spacing: 0.08em;
                margin-bottom: 0.18rem;
                text-transform: uppercase;
            }

            .brief-chip strong {
                color: var(--saas-text);
                display: block;
                font-size: 0.92rem;
                font-weight: 700;
                line-height: 1.25;
            }

            .result-header {
                margin-top: 1.4rem;
            }

            .results-notice {
                margin-bottom: 0.95rem;
            }

            .variant-heading {
                margin-bottom: 0.6rem;
            }

            .variant-kicker {
                color: var(--saas-accent);
                font-size: 0.76rem;
                font-weight: 800;
                letter-spacing: 0.08em;
                margin: 0 0 0.35rem 0;
                text-transform: uppercase;
            }

            .variant-title {
                color: var(--saas-text);
                font-size: 1.12rem;
                font-weight: 750;
                line-height: 1.25;
                margin: 0;
            }

            .meta-row {
                display: flex;
                flex-wrap: wrap;
                gap: 0.5rem;
                margin: 0.55rem 0 0.9rem 0;
            }

            .meta-pill {
                background: var(--saas-accent-soft);
                border: 1px solid rgba(37, 99, 235, 0.12);
                border-radius: 999px;
                color: var(--saas-accent-strong);
                display: inline-flex;
                font-size: 0.82rem;
                font-weight: 700;
                padding: 0.3rem 0.72rem;
            }

            div[data-baseweb="select"] > div,
            div[data-baseweb="input"] > div,
            div[data-testid="stTextArea"] textarea {
                background: rgba(255, 255, 255, 0.96) !important;
                border-color: var(--saas-line-strong) !important;
                border-radius: var(--saas-radius-sm) !important;
            }

            div[data-testid="stTextArea"] textarea {
                box-shadow: none !important;
                line-height: 1.55 !important;
            }

            div[data-testid="stSegmentedControl"] {
                margin-top: 0.25rem;
            }

            div[data-testid="stPopover"] button {
                border-radius: 999px !important;
                font-weight: 700 !important;
            }

            div.stButton > button[kind="primary"] {
                background: linear-gradient(135deg, var(--saas-accent) 0%, var(--saas-accent-strong) 100%);
                border: none;
                border-radius: 999px;
                box-shadow: 0 14px 28px rgba(37, 99, 235, 0.25);
                color: white;
                font-size: 1rem;
                font-weight: 800;
                min-height: 3.15rem;
            }

            div.stButton > button[kind="primary"]:hover {
                filter: brightness(1.02);
            }

            @media (max-width: 980px) {
                .hero-shell {
                    padding: 1.55rem;
                }

                div[data-testid="stVerticalBlock"]:has(.results-board-anchor)
                > div[data-testid="stHorizontalBlock"] {
                    flex-direction: column;
                }

                div[data-testid="stVerticalBlock"]:has(.results-board-anchor)
                > div[data-testid="stHorizontalBlock"]
                > div[data-testid="column"] {
                    min-width: 100% !important;
                    width: 100% !important;
                }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_hero(repository: FewShotPosts, available_tags: list[str]) -> None:
    """Render the page hero and dataset metrics."""

    languages = sorted({post.language for post in repository.posts})
    language_text = ", ".join(languages) if languages else "No languages"
    st.markdown(
        f"""
        <div class="hero-shell">
            <p class="eyebrow">Premium AI Writing Studio</p>
            <h1 class="hero-title">Generate client-ready LinkedIn variants in one screen.</h1>
            <p class="hero-copy">{escape(HERO_COPY)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    metric_columns = st.columns(3, gap="small")
    metric_cards = [
        ("Processed Posts", str(len(repository.posts)), "Examples available to guide generation quality."),
        ("Topics", str(len(available_tags)), "Usable topics extracted from your processed dataset."),
        ("Languages", language_text, "Current language coverage inside the prompt library."),
    ]
    for column, (label, value, copy) in zip(metric_columns, metric_cards, strict=True):
        with column:
            st.markdown(
                f"""
                <div class="metrics-card">
                    <p class="metrics-label">{escape(label)}</p>
                    <p class="metrics-value">{escape(value)}</p>
                    <p class="metrics-copy">{escape(copy)}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _render_section_header(title: str, description: str) -> None:
    """Render a shared section heading."""

    st.markdown(
        f"""
        <p class="eyebrow">Workspace</p>
        <h2 class="section-title">{escape(title)}</h2>
        <p class="section-copy">{escape(description)}</p>
        """,
        unsafe_allow_html=True,
    )


def _resolve_segmented_value(value: str | None, default: str) -> str:
    """Return a segmented-control value with a stable fallback."""

    return value if isinstance(value, str) and value else default


def _build_generation_options() -> GenerationOptions:
    """Render prompt-control widgets and return the selected options."""

    defaults = GenerationOptions()
    tone = st.selectbox(
        "Tone",
        options=TONE_OPTIONS,
        index=TONE_OPTIONS.index(defaults.tone),
        help="Set the overall writing energy for the generated drafts.",
    )
    audience = st.selectbox(
        "Audience",
        options=AUDIENCE_OPTIONS,
        index=AUDIENCE_OPTIONS.index(defaults.audience),
        help="Tell the model who the post should feel most relevant to.",
    )
    goal = st.selectbox(
        "Goal",
        options=GOAL_OPTIONS,
        index=GOAL_OPTIONS.index(defaults.goal),
        help="Set the main job the post should do for the reader.",
    )

    with st.popover("Advanced settings", use_container_width=False):
        voice = st.selectbox(
            "Voice",
            options=VOICE_OPTIONS,
            index=VOICE_OPTIONS.index(defaults.voice),
        )
        cta_strength = st.selectbox(
            "CTA Strength",
            options=CTA_STRENGTH_OPTIONS,
            index=CTA_STRENGTH_OPTIONS.index(defaults.cta_strength),
        )
        hashtag_count = st.select_slider(
            "Hashtag Count",
            options=HASHTAG_COUNT_OPTIONS,
            value=defaults.hashtag_count,
            help="Apply hashtags only on the final line of the generated post.",
        )

    return GenerationOptions(
        tone=tone,
        audience=audience,
        goal=goal,
        voice=voice,
        cta_strength=cta_strength,
        hashtag_count=hashtag_count,
    )


def _render_brief_bar(
    topic: str,
    length: str,
    language: str,
    options: GenerationOptions,
) -> None:
    """Render the compact brief chip row."""

    chips = build_brief_chips(topic, length, language, options)
    markup = "".join(
        (
            f"<div class='brief-chip'><span>{escape(chip['label'])}</span>"
            f"<strong>{escape(chip['value'])}</strong></div>"
        )
        for chip in chips
    )
    st.markdown(f"<div class='brief-chip-row'>{markup}</div>", unsafe_allow_html=True)


def _render_copy_button(card_index: int, text: str, *, copy_target: str) -> None:
    """Render a lightweight copy-to-clipboard control for a variant card."""

    encoded_text = json.dumps(text).replace("</", "<\\/")
    button_id = f"copy-button-{copy_target}-{card_index}"
    status_id = f"copy-status-{copy_target}-{card_index}"
    components.html(
        f"""
        <div style="display:flex;align-items:center;gap:10px;margin:0.2rem 0 0.1rem 0;">
            <button
                id="{button_id}"
                type="button"
                style="
                    background: linear-gradient(135deg, #2563eb 0%, #1747c8 100%);
                    border: none;
                    border-radius: 999px;
                    color: white;
                    cursor: pointer;
                    font-family: sans-serif;
                    font-size: 0.93rem;
                    font-weight: 700;
                    min-height: 2.45rem;
                    padding: 0.55rem 1rem;
                "
            >
                Copy
            </button>
            <span
                id="{status_id}"
                style="
                    color: #5b667a;
                    font-family: sans-serif;
                    font-size: 0.86rem;
                    font-weight: 600;
                "
            ></span>
        </div>
        <script>
            const textToCopy = {encoded_text};
            const button = document.getElementById("{button_id}");
            const status = document.getElementById("{status_id}");

            async function copyVariant() {{
                try {{
                    await navigator.clipboard.writeText(textToCopy);
                    button.textContent = "Copied";
                    status.textContent = "Ready to paste";
                }} catch (clipboardError) {{
                    const helper = document.createElement("textarea");
                    helper.value = textToCopy;
                    helper.setAttribute("readonly", "");
                    helper.style.position = "absolute";
                    helper.style.left = "-9999px";
                    document.body.appendChild(helper);
                    helper.select();
                    helper.setSelectionRange(0, helper.value.length);
                    try {{
                        const copied = document.execCommand("copy");
                        button.textContent = copied ? "Copied" : "Copy";
                        status.textContent = copied ? "Ready to paste" : "Press Ctrl+C in the editor";
                    }} catch (fallbackError) {{
                        status.textContent = "Press Ctrl+C in the editor";
                    }}
                    document.body.removeChild(helper);
                }}

                window.setTimeout(() => {{
                    button.textContent = "Copy";
                    status.textContent = "";
                }}, 1800);
            }}

            button.addEventListener("click", copyVariant);
        </script>
        """,
        height=54,
    )


def _store_generated_variants(
    variants: list[str],
    brief_signature: tuple[str, str, str, str, str, str, str, str, int],
) -> None:
    """Persist generated variants and their editable state in session storage."""

    st.session_state[GENERATED_VARIANTS_KEY] = list(variants)
    st.session_state[GENERATED_BRIEF_KEY] = brief_signature
    for card in build_variant_cards(variants):
        st.session_state[f"{EDITOR_KEY_PREFIX}{card['index']}"] = str(card["text"])


def _render_results_board(
    current_brief_signature: tuple[str, str, str, str, str, str, str, str, int],
) -> None:
    """Render the side-by-side results board from session state."""

    stored_variants = st.session_state.get(GENERATED_VARIANTS_KEY, [])
    if not stored_variants:
        return

    st.markdown("---")
    st.markdown(
        """
        <div class="result-header">
            <p class="eyebrow">Results</p>
            <h2 class="section-title">Compare all three variants at once.</h2>
            <p class="section-copy">
                Review the alternatives side by side, make edits directly in place, and copy whichever version wins.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.session_state.get(GENERATED_BRIEF_KEY) != current_brief_signature:
        st.info(STALE_RESULTS_NOTICE)

    st.markdown("<div class='results-board-anchor'></div>", unsafe_allow_html=True)
    columns = st.columns(DEFAULT_VARIANT_COUNT, gap="large", vertical_alignment="top")
    for card, column in zip(build_variant_cards(stored_variants), columns, strict=True):
        with column:
            st.markdown(
                f"""
                <div class="variant-heading">
                    <p class="variant-kicker">{escape(str(card['card_label']))}</p>
                    <p class="variant-title">{escape(str(card['angle_label']))}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            editor_key = f"{EDITOR_KEY_PREFIX}{card['index']}"
            current_text = st.text_area(
                label=f"Variant {card['index']}",
                key=editor_key,
                height=360,
                label_visibility="collapsed",
            )
            current_card = build_variant_cards(
                [current_text],
                variant_angles=[str(card["angle_label"])],
            )[0]
            result_pills = "".join(
                f"<span class='meta-pill'>{escape(value)}</span>"
                for value in [
                    str(current_card["line_label"]),
                    str(current_card["hashtag_label"]),
                ]
            )
            st.markdown(
                f"<div class='meta-row'>{result_pills}</div>",
                unsafe_allow_html=True,
            )
            _render_copy_button(
                int(card["index"]),
                current_text,
                copy_target=str(current_card["copy_target"]),
            )


def _render_missing_dataset_state() -> None:
    """Render the missing-dataset state."""

    st.error(
        "Processed posts were not found. Run the preprocessing step before opening the writing studio."
    )
    st.code("python preprocess.py", language="bash")


def _render_invalid_dataset_state(error: ValueError) -> None:
    """Render the invalid-dataset state."""

    st.error(f"Processed posts could not be loaded: {error}")
    st.caption(
        "Regenerate the processed dataset if the file was manually edited or partially written."
    )


def _render_empty_dataset_state() -> None:
    """Render the no-tags-available state."""

    st.warning("The processed dataset loaded, but it does not contain usable topics yet.")
    st.caption(
        "Re-run scraping and preprocessing, then review the processed dataset and failures report."
    )


def main() -> None:
    """Render the Streamlit application."""

    _configure_page()
    processed_posts_path = str(get_paths().processed_posts_path)

    try:
        repository = load_repository(processed_posts_path)
    except FileNotFoundError:
        _render_missing_dataset_state()
        return
    except ValueError as error:
        _render_invalid_dataset_state(error)
        return

    available_tags = repository.get_tags()
    if not available_tags:
        _render_empty_dataset_state()
        return

    _render_hero(repository, available_tags)

    with st.container(border=True):
        _render_section_header(
            "Compose your brief",
            "Pick the topic, format, and writing controls once, then generate three polished options side by side.",
        )
        selected_tag = st.selectbox(
            "Topic",
            options=available_tags,
            help="Search and select the topic the post should revolve around.",
        )
        selected_length = _resolve_segmented_value(
            st.segmented_control(
                "Length",
                options=LENGTH_OPTIONS,
                default=LENGTH_OPTIONS[0],
                selection_mode="single",
                width="stretch",
            ),
            LENGTH_OPTIONS[0],
        )
        selected_language = _resolve_segmented_value(
            st.segmented_control(
                "Language",
                options=LANGUAGE_OPTIONS,
                default=LANGUAGE_OPTIONS[0],
                selection_mode="single",
                width="stretch",
            ),
            LANGUAGE_OPTIONS[0],
        )
        selected_options = _build_generation_options()
        _render_brief_bar(
            selected_tag,
            selected_length,
            selected_language,
            selected_options,
        )

        current_brief_signature = build_brief_signature(
            selected_tag,
            selected_length,
            selected_language,
            selected_options,
        )

        st.markdown(
            '<p class="muted-copy">The generator will use the current brief to create three distinct variants with the same strategic intent.</p>',
            unsafe_allow_html=True,
        )
        if st.button(
            f"Generate {DEFAULT_VARIANT_COUNT} Variants",
            type="primary",
            use_container_width=True,
        ):
            with st.spinner("Generating post variants..."):
                try:
                    variants = generate_post_variants(
                        selected_length,
                        selected_language,
                        selected_tag,
                        options=selected_options,
                        repository=repository,
                        variant_count=DEFAULT_VARIANT_COUNT,
                    )
                except (RuntimeError, ValueError) as error:
                    st.error(f"Post generation failed: {error}")
                    if st.session_state.get(GENERATED_VARIANTS_KEY):
                        st.info(FAILED_GENERATION_STALE_RESULTS_NOTICE)
                else:
                    _store_generated_variants(variants, current_brief_signature)

    _render_results_board(current_brief_signature)
