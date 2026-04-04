from linkedin_post_generator.quality import (
    get_low_quality_reason,
    normalize_post_text,
    sanitize_post_text,
)


def test_normalize_post_text_repairs_mojibake_and_invisible_characters():
    text = "I\u00e2\u20ac\u2122m\u200b building this"

    assert normalize_post_text(text) == "I’m building this"


def test_quality_helpers_filter_placeholders_but_keep_real_short_posts():
    assert (
        get_low_quality_reason("Activate to view larger image,\nactivate to view larger image,")
        == "image_placeholder"
    )
    assert get_low_quality_reason("Media player modal window") == "media_placeholder"
    assert sanitize_post_text(
        "Useful line\nActivate to view larger image,\nMore context"
    ) == "Useful line\nMore context"
    assert get_low_quality_reason("Short but real insight.") is None
