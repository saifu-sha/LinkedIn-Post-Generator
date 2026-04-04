from linkedin_post_generator.scraper.cleaning import (
    clean_post_text,
    convert_abbreviated_to_number,
    extract_likes_from_text_blob,
    extract_number_from_text,
    fingerprint_text,
)


def test_convert_abbreviated_to_number_handles_suffixes():
    assert convert_abbreviated_to_number("42") == 42
    assert convert_abbreviated_to_number("1.5K") == 1500
    assert convert_abbreviated_to_number("2 M") == 2_000_000


def test_extract_number_from_text_ignores_unmatched_suffix_noise():
    assert extract_number_from_text("It happened at 2 AM") == 2
    assert extract_number_from_text("We booked a 1:1 session") == 1


def test_extract_likes_from_text_blob_requires_social_context():
    assert extract_likes_from_text_blob("42 likes") == 42
    assert extract_likes_from_text_blob("likes 1.2K") == 1200
    assert extract_likes_from_text_blob("It happened at 2 AM") == 0
    assert extract_likes_from_text_blob("A 1:1 mentoring session") == 0


def test_clean_post_text_and_fingerprint_normalize_noise():
    cleaned = clean_post_text("Hello   world!!!\n\nhashtag #Python")

    assert cleaned == "Hello world! #python"
    assert fingerprint_text(cleaned) == "hello world #python"
