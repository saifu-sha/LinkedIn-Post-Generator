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
                    "text": "Post A",
                    "engagement": 1,
                    "line_count": 3,
                    "language": "English",
                    "tags": ["AI", "Career"],
                },
                {
                    "text": "Post B",
                    "engagement": 2,
                    "line_count": 9,
                    "language": "English",
                    "tags": ["AI"],
                },
                {
                    "text": "Post C",
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
            "text": "Post B",
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
