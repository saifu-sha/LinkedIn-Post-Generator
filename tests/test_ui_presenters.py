from linkedin_post_generator.models import GenerationOptions
from linkedin_post_generator.ui import (
    FAILED_GENERATION_STALE_RESULTS_NOTICE,
    HERO_COPY,
    STALE_RESULTS_NOTICE,
)
from linkedin_post_generator.ui_presenters import (
    build_brief_chips,
    build_variant_cards,
    format_hashtag_label,
    format_line_label,
)


def test_build_brief_chips_formats_selected_brief():
    chips = build_brief_chips(
        "AI",
        "Medium",
        "English",
        GenerationOptions(
            tone="Bold",
            audience="Founders",
            goal="Educate",
            voice="First Person",
            cta_strength="Soft",
            hashtag_count=2,
        ),
    )

    assert chips == [
        {"label": "Topic", "value": "AI"},
        {"label": "Format", "value": "Medium / English"},
        {"label": "Tone", "value": "Bold"},
        {"label": "Audience", "value": "Founders"},
        {"label": "Goal", "value": "Educate"},
        {"label": "Voice", "value": "First Person"},
        {"label": "Finish", "value": "CTA: Soft / 2 hashtags"},
    ]


def test_build_variant_cards_maps_angles_and_metadata():
    cards = build_variant_cards(
        [
            "Hook line\nUseful proof\n#AI #Careers",
            "Single line variant",
            "Action line\nNext line",
        ]
    )

    assert cards[0]["card_label"] == "Variant 1"
    assert cards[0]["angle_label"] == "Insight-led hook"
    assert cards[0]["estimated_lines"] == 3
    assert cards[0]["line_label"] == "3 lines"
    assert cards[0]["hashtag_count"] == 2
    assert cards[0]["hashtag_label"] == "2 hashtags"
    assert cards[0]["copy_label"] == "Copy"
    assert cards[0]["copy_feedback"] == "Copied"
    assert cards[1]["angle_label"] == "Story/problem-solution hook"
    assert cards[2]["angle_label"] == "Action/takeaway-led hook"


def test_build_variant_cards_recomputes_metadata_for_edited_text():
    cards = build_variant_cards(
        ["Updated intro\nUpdated proof\nUpdated takeaway\n#AI"],
        variant_angles=["Insight-led hook"],
    )

    assert cards == [
        {
            "index": 1,
            "angle_label": "Insight-led hook",
            "card_label": "Variant 1",
            "text": "Updated intro\nUpdated proof\nUpdated takeaway\n#AI",
            "estimated_lines": 4,
            "line_label": "4 lines",
            "hashtag_count": 1,
            "hashtag_label": "1 hashtag",
            "copy_label": "Copy",
            "copy_feedback": "Copied",
            "copy_target": "variant-1-insight-led-hook",
        }
    ]


def test_build_variant_cards_handles_empty_results_gracefully():
    assert build_variant_cards([]) == []


def test_build_variant_cards_estimate_lines_for_single_paragraph_text():
    cards = build_variant_cards(
        [
            "This is a long paragraph that explains one core idea. Then it adds another sentence so the readable layout should not be reported as only one line for the user."
        ],
        variant_angles=["Insight-led hook"],
    )

    assert cards[0]["estimated_lines"] == 2
    assert cards[0]["line_label"] == "2 lines"


def test_format_line_label_handles_singular_and_plural():
    assert format_line_label(1) == "1 line"
    assert format_line_label(3) == "3 lines"


def test_format_hashtag_label_handles_singular_and_plural():
    assert format_hashtag_label(1) == "1 hashtag"
    assert format_hashtag_label(3) == "3 hashtags"


def test_ui_copy_and_stale_result_messages_are_copy_first():
    assert "copy the strongest version" in HERO_COPY
    assert "export" not in HERO_COPY.lower()
    assert "download" not in HERO_COPY.lower()
    assert "last generation run" in STALE_RESULTS_NOTICE
    assert "last successful generation" in FAILED_GENERATION_STALE_RESULTS_NOTICE
