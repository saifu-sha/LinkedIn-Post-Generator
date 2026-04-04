from linkedin_post_generator.generator import build_prompt, generate_post, get_length_str


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
