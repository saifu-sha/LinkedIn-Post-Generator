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
