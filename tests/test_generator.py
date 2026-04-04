import json

from linkedin_post_generator.generator import build_prompt, generate_post, get_length_str, get_prompt
from linkedin_post_generator.repository import FewShotPosts


class StubRepository:
    def get_filtered_posts(self, length, language, tag):
        return [
            {"text": "Example 1"},
            {"text": "Example 2"},
            {"text": "Example 3"},
            {"text": "Example 4"},
        ]


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


def test_build_prompt_includes_only_three_examples():
    prompt = build_prompt(
        "Medium",
        "English",
        "AI",
        [
            {"text": "Example 1"},
            {"text": "Example 2"},
            {"text": "Example 3"},
            {"text": "Example 4"},
        ],
    )

    assert "6 to 10 lines" in prompt
    assert "Example 1" in prompt
    assert "Example 2" in prompt
    assert "Example 3" in prompt
    assert "Example 4" not in prompt


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


def test_get_prompt_uses_top_three_ranked_examples(tmp_path):
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
                    "text": "Actionable AI career advice\nBuild projects\nShare outcomes\nStay consistent",
                    "engagement": 30,
                    "line_count": 4,
                    "language": "English",
                    "tags": ["AI"],
                },
                {
                    "text": "Use AI to learn faster\nDocument experiments\nReflect weekly\nApply insights",
                    "engagement": 20,
                    "line_count": 4,
                    "language": "English",
                    "tags": ["AI"],
                },
                {
                    "text": "Solve real problems\nShow your work\nAsk for feedback\nKeep improving",
                    "engagement": 15,
                    "line_count": 4,
                    "language": "English",
                    "tags": ["AI"],
                },
            ]
        ),
        encoding="utf-8",
    )

    prompt = get_prompt("Short", "English", "AI", repository=FewShotPosts(dataset_path))

    assert "Actionable AI career advice" in prompt
    assert "Use AI to learn faster" in prompt
    assert "Solve real problems" in prompt
    assert "AI jobs" not in prompt
