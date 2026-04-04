import json

from linkedin_post_generator.repository import FewShotPosts, categorize_length, load_processed_posts


def test_load_processed_posts_normalizes_missing_fields(tmp_path):
    dataset_path = tmp_path / "processed_posts.json"
    dataset_path.write_text(
        json.dumps(
            [
                {
                    "text": "Short post",
                    "engagement": 4,
                    "language": "English",
                },
                {
                    "text": "Longer post",
                    "engagement": "8",
                    "line_count": "12",
                    "language": "Hinglish",
                    "tags": 42,
                },
            ]
        ),
        encoding="utf-8",
    )

    posts = load_processed_posts(dataset_path)

    assert posts[0].tags == []
    assert posts[0].line_count == 0
    assert posts[1].engagement == 8
    assert posts[1].tags == ["42"]


def test_repository_filters_posts_and_returns_sorted_tags(tmp_path):
    dataset_path = tmp_path / "processed_posts.json"
    dataset_path.write_text(
        json.dumps(
            [
                {
                    "text": "Post A shares useful AI career lessons with clear and practical next steps.",
                    "engagement": 1,
                    "line_count": 3,
                    "language": "English",
                    "tags": ["AI", "Career"],
                },
                {
                    "text": (
                        "Post B explains how AI projects become more credible over time.\n"
                        "Document your experiments.\n"
                        "Share outcomes with context.\n"
                        "Show what changed.\n"
                        "Ask for feedback.\n"
                        "Keep building proof."
                    ),
                    "engagement": 2,
                    "line_count": 9,
                    "language": "English",
                    "tags": ["AI"],
                },
                {
                    "text": (
                        "Post C mixes Hindi and English ideas to explain AI growth clearly.\n"
                        "Build projects consistently.\n"
                        "Share learnings every week.\n"
                        "Visible proof compounds over time.\n"
                        "Stay patient and keep shipping."
                    ),
                    "engagement": 3,
                    "line_count": 9,
                    "language": "Hinglish",
                    "tags": ["AI"],
                },
            ]
        ),
        encoding="utf-8",
    )

    repository = FewShotPosts(dataset_path)

    assert repository.get_tags() == ["AI", "Career"]
    assert repository.get_filtered_posts("Medium", "English", "AI") == [
        {
            "text": (
                "Post B explains how AI projects become more credible over time.\n"
                "Document your experiments.\n"
                "Share outcomes with context.\n"
                "Show what changed.\n"
                "Ask for feedback.\n"
                "Keep building proof."
            ),
            "engagement": 2,
            "line_count": 9,
            "language": "English",
            "tags": ["AI"],
        }
    ]


def test_repository_handles_empty_dataset(tmp_path):
    dataset_path = tmp_path / "processed_posts.json"
    dataset_path.write_text("[]", encoding="utf-8")

    repository = FewShotPosts(dataset_path)

    assert repository.get_tags() == []
    assert repository.get_filtered_posts("Short", "English", "AI") == []
    assert repository.get_prompt_examples("Short", "English", "AI") == []


def test_categorize_length_is_stable():
    assert categorize_length(0) == "Short"
    assert categorize_length(5) == "Medium"
    assert categorize_length(11) == "Long"


def test_repository_ranks_richer_examples_above_short_viral_titles(tmp_path):
    rich_text = (
        "Actionable AI career advice\n"
        "Build projects that solve real problems\n"
        "Share the outcome publicly\n"
        "Keep iterating on feedback"
    )
    dataset_path = tmp_path / "processed_posts.json"
    dataset_path.write_text(
        json.dumps(
            [
                {
                    "text": "AI jobs",
                    "engagement": 100000,
                    "line_count": 1,
                    "language": "English",
                    "tags": ["AI"],
                },
                {
                    "text": rich_text,
                    "engagement": 50,
                    "line_count": 4,
                    "language": "English",
                    "tags": ["AI"],
                },
                {
                    "text": rich_text,
                    "engagement": 5,
                    "line_count": 4,
                    "language": "English",
                    "tags": ["AI"],
                },
                {
                    "text": "Activate to view larger image,",
                    "engagement": 500,
                    "line_count": 1,
                    "language": "English",
                    "tags": ["Noise"],
                },
            ]
        ),
        encoding="utf-8",
    )

    repository = FewShotPosts(dataset_path)
    ranked_posts = repository.get_filtered_posts("Short", "English", "AI")

    assert repository.get_tags() == ["AI"]
    assert ranked_posts == [
        {
            "text": rich_text,
            "engagement": 50,
            "line_count": 4,
            "language": "English",
            "tags": ["AI"],
        },
    ]


def test_repository_get_prompt_examples_uses_tiered_fallback_and_limit(tmp_path):
    dataset_path = tmp_path / "processed_posts.json"
    exact_text = (
        "Exact AI example explains how builders gain trust through weekly shipping.\n"
        "Show outcomes publicly.\n"
        "Reflect on what changed.\n"
        "Keep improving."
    )
    dataset_path.write_text(
        json.dumps(
            [
                {
                    "text": exact_text,
                    "engagement": 70,
                    "line_count": 4,
                    "language": "English",
                    "tags": ["AI"],
                },
                {
                    "text": (
                        "Same language AI example explains how teams document experiments clearly.\n"
                        "Capture the baseline.\n"
                        "Run one test.\n"
                        "Measure the result.\n"
                        "Share the lesson.\n"
                        "Repeat weekly."
                    ),
                    "engagement": 60,
                    "line_count": 6,
                    "language": "English",
                    "tags": ["AI"],
                },
                {
                    "text": exact_text,
                    "engagement": 90,
                    "line_count": 4,
                    "language": "Hinglish",
                    "tags": ["AI"],
                },
                {
                    "text": (
                        "Cross language AI example batata hai ki public proof kaise trust build karta hai.\n"
                        "Projects ship karo.\n"
                        "Results share karo.\n"
                        "Feedback lo.\n"
                        "Phir improve karo."
                    ),
                    "engagement": 50,
                    "line_count": 5,
                    "language": "Hinglish",
                    "tags": ["AI"],
                },
                {
                    "text": (
                        "Global fallback career example explains why consistent proof compounds over time.\n"
                        "Write what you tried.\n"
                        "Show what happened.\n"
                        "Keep the evidence visible."
                    ),
                    "engagement": 40,
                    "line_count": 4,
                    "language": "English",
                    "tags": ["Career"],
                },
                {
                    "text": (
                        "Second global fallback leadership example explains how clarity improves execution.\n"
                        "State the goal.\n"
                        "Set one metric.\n"
                        "Review progress weekly."
                    ),
                    "engagement": 38,
                    "line_count": 4,
                    "language": "English",
                    "tags": ["Leadership"],
                },
                {
                    "text": (
                        "Third global fallback product example shows how feedback sharpens product direction.\n"
                        "Observe usage.\n"
                        "Fix one bottleneck.\n"
                        "Communicate the change."
                    ),
                    "engagement": 20,
                    "line_count": 4,
                    "language": "English",
                    "tags": ["Product"],
                },
            ]
        ),
        encoding="utf-8",
    )

    repository = FewShotPosts(dataset_path)
    prompt_examples = repository.get_prompt_examples("Short", "English", "AI", limit=5)

    assert len(prompt_examples) == 5
    assert [example["match_tier"] for example in prompt_examples] == [
        "exact_match",
        "same_tag_same_language",
        "same_tag_any_language",
        "global_best",
        "global_best",
    ]
    assert [example["match_label"] for example in prompt_examples] == [
        "Exact match",
        "Same tag and language; length relaxed",
        "Same tag; language and length relaxed",
        "Global fallback",
        "Global fallback",
    ]
    assert [example["text"] for example in prompt_examples].count(exact_text) == 1
    assert all("Third global fallback" not in example["text"] for example in prompt_examples)


def test_repository_get_prompt_examples_uses_global_best_only_after_same_tag_tiers(tmp_path):
    dataset_path = tmp_path / "processed_posts.json"
    dataset_path.write_text(
        json.dumps(
            [
                {
                    "text": (
                        "English AI example one explains how weekly proof builds professional trust.\n"
                        "Publish what changed.\n"
                        "Show the result.\n"
                        "Keep going."
                    ),
                    "engagement": 50,
                    "line_count": 4,
                    "language": "English",
                    "tags": ["AI"],
                },
                {
                    "text": (
                        "English AI example two explains how teams learn faster from visible experiments.\n"
                        "Set a baseline.\n"
                        "Run one test.\n"
                        "Share the lesson."
                    ),
                    "engagement": 48,
                    "line_count": 4,
                    "language": "English",
                    "tags": ["AI"],
                },
                {
                    "text": (
                        "English AI example three explains how consistent shipping improves credibility.\n"
                        "Build a small proof.\n"
                        "Post the outcome.\n"
                        "Repeat weekly."
                    ),
                    "engagement": 46,
                    "line_count": 4,
                    "language": "English",
                    "tags": ["AI"],
                },
                {
                    "text": (
                        "Fallback career example explains why clear writing helps ideas travel further.\n"
                        "Name the lesson.\n"
                        "Give one proof.\n"
                        "End with a takeaway."
                    ),
                    "engagement": 35,
                    "line_count": 4,
                    "language": "English",
                    "tags": ["Career"],
                },
                {
                    "text": (
                        "Fallback leadership example explains how focus keeps execution aligned.\n"
                        "Pick one priority.\n"
                        "Communicate it well.\n"
                        "Review weekly."
                    ),
                    "engagement": 30,
                    "line_count": 4,
                    "language": "English",
                    "tags": ["Leadership"],
                },
            ]
        ),
        encoding="utf-8",
    )

    repository = FewShotPosts(dataset_path)
    prompt_examples = repository.get_prompt_examples("Long", "Hinglish", "AI", limit=5)

    assert [example["match_tier"] for example in prompt_examples] == [
        "same_tag_any_language",
        "same_tag_any_language",
        "same_tag_any_language",
        "global_best",
        "global_best",
    ]
