import json

from linkedin_post_generator.generator import build_prompt, generate_post, get_length_str, get_prompt
from linkedin_post_generator.repository import FewShotPosts


class StubRepository:
    def get_filtered_posts(self, length, language, tag):
        raise AssertionError("get_prompt should use get_prompt_examples, not get_filtered_posts.")

    def get_prompt_examples(self, length, language, tag, *, limit=5):
        return [
            {"text": "Example 1 text", "match_label": "Exact match"},
            {"text": "Example 2 text", "match_label": "Same tag and language; length relaxed"},
            {"text": "Example 3 text", "match_label": "Same tag; language and length relaxed"},
            {"text": "Example 4 text", "match_label": "Global fallback"},
            {"text": "Example 5 text", "match_label": "Global fallback"},
            {"text": "Example 6 text", "match_label": "Global fallback"},
        ][:limit]


class StubResponse:
    def __init__(self, content):
        self.content = content


class StubLLM:
    def __init__(self):
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return StubResponse("Generated post")


def test_get_length_str_rejects_unknown_values():
    try:
        get_length_str("Tiny")
    except ValueError as error:
        assert "Unsupported length" in str(error)
    else:
        raise AssertionError("Expected ValueError for unsupported length.")


def test_build_prompt_includes_only_five_examples_and_labels_provenance():
    prompt = build_prompt(
        "Medium",
        "English",
        "AI",
        [
            {"text": "Example 1 text", "match_label": "Exact match"},
            {"text": "Example 2 text", "match_label": "Same tag and language; length relaxed"},
            {"text": "Example 3 text", "match_label": "Same tag; language and length relaxed"},
            {"text": "Example 4 text", "match_label": "Global fallback"},
            {"text": "Example 5 text", "match_label": "Global fallback"},
            {"text": "Example 6 text", "match_label": "Global fallback"},
        ],
    )

    assert "6 to 10 lines" in prompt
    assert "Example 1 (Exact match)" in prompt
    assert "Example 2 (Same tag and language; length relaxed)" in prompt
    assert "Example 3 (Same tag; language and length relaxed)" in prompt
    assert "Example 5 (Global fallback)" in prompt
    assert "Example 6" not in prompt
    assert "Example 6 text" not in prompt


def test_generate_post_uses_injected_dependencies():
    llm = StubLLM()

    result = generate_post(
        "Medium",
        "Hinglish",
        "Career Growth",
        llm_client=llm,
        repository=StubRepository(),
    )

    assert result == "Generated post"
    assert "Career Growth" in llm.prompts[0]
    assert "Hinglish" in llm.prompts[0]
    assert "Example 1 (Exact match)" in llm.prompts[0]


def test_get_prompt_uses_top_five_ranked_examples_with_provenance(tmp_path):
    dataset_path = tmp_path / "processed_posts.json"
    dataset_path.write_text(
        json.dumps(
            [
                {
                    "text": (
                        "Exact AI example explains how builders gain trust through weekly shipping.\n"
                        "Show outcomes publicly.\n"
                        "Reflect on what changed.\n"
                        "Keep improving."
                    ),
                    "engagement": 60,
                    "line_count": 4,
                    "language": "English",
                    "tags": ["AI"],
                },
                {
                    "text": (
                        "English AI medium example shows how teams document experiments clearly.\n"
                        "Capture the baseline.\n"
                        "Test one change.\n"
                        "Measure the result.\n"
                        "Share the lesson.\n"
                        "Repeat weekly."
                    ),
                    "engagement": 55,
                    "line_count": 6,
                    "language": "English",
                    "tags": ["AI"],
                },
                {
                    "text": (
                        "Hinglish AI example batata hai ki public proof kaise trust build karta hai.\n"
                        "Projects ship karo.\n"
                        "Results share karo.\n"
                        "Feedback lo.\n"
                        "Phir improve karo."
                    ),
                    "engagement": 45,
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

    prompt = get_prompt("Short", "English", "AI", repository=FewShotPosts(dataset_path))

    assert "Example 1 (Exact match)" in prompt
    assert "Example 2 (Same tag and language; length relaxed)" in prompt
    assert "Example 3 (Same tag; language and length relaxed)" in prompt
    assert "Example 4 (Global fallback)" in prompt
    assert "Example 5 (Global fallback)" in prompt
    assert "Third global fallback product example" not in prompt


def test_get_prompt_handles_sparse_hinglish_requests_with_cross_language_fallback(tmp_path):
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

    prompt = get_prompt("Long", "Hinglish", "AI", repository=FewShotPosts(dataset_path))

    assert "Example 1 (Same tag; language and length relaxed)" in prompt
    assert "Example 2 (Same tag; language and length relaxed)" in prompt
    assert "Example 3 (Same tag; language and length relaxed)" in prompt
    assert "Example 4 (Global fallback)" in prompt
    assert "Example 5 (Global fallback)" in prompt
    assert "Exact match" not in prompt
