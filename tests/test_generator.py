import json

import pytest

from linkedin_post_generator.generator import (
    build_prompt,
    build_variants_prompt,
    generate_post,
    generate_post_variants,
    get_length_str,
    get_prompt,
    get_variants_prompt,
)
from linkedin_post_generator.models import GenerationOptions
from linkedin_post_generator.repository import FewShotPosts


class StubRepository:
    def get_filtered_posts(self, length, language, tag):
        raise AssertionError("Prompt builders should use get_prompt_examples, not get_filtered_posts.")

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
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return StubResponse(self.responses.pop(0))


def test_generation_options_defaults_are_stable():
    options = GenerationOptions()

    assert options == GenerationOptions(
        tone="Professional",
        audience="General",
        goal="Match examples",
        voice="Match examples",
        cta_strength="None",
        hashtag_count=0,
    )


def test_get_length_str_rejects_unknown_values():
    try:
        get_length_str("Tiny")
    except ValueError as error:
        assert "Unsupported length" in str(error)
    else:
        raise AssertionError("Expected ValueError for unsupported length.")


def test_build_prompt_includes_style_controls_rules_and_only_five_examples():
    options = GenerationOptions(
        tone="Bold",
        audience="Developers",
        goal="Educate",
        voice="Brand/Company",
        cta_strength="Strong",
        hashtag_count=2,
    )

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
        options=options,
    )

    assert "4) Style Controls:" in prompt
    assert "- Tone: Bold" in prompt
    assert "- Audience: Developers" in prompt
    assert "- Goal: Educate" in prompt
    assert "- Voice: Brand/Company" in prompt
    assert "- CTA Strength: Strong" in prompt
    assert "- Hashtag Count: 2" in prompt
    assert "Use company or team voice and avoid first-person singular pronouns." in prompt
    assert "Close with a direct and specific call to action." in prompt
    assert "Include exactly 2 relevant hashtags on the final line only" in prompt
    assert "Example 5 (Global fallback)" in prompt
    assert "Example 6 text" not in prompt


def test_generate_post_uses_default_options_and_injected_dependencies():
    llm = StubLLM(["Generated post"])

    result = generate_post(
        "Medium",
        "Hinglish",
        "Career Growth",
        llm_client=llm,
        repository=StubRepository(),
    )

    assert result == "Generated post"
    assert "- Tone: Professional" in llm.prompts[0]
    assert "- Goal: Match examples" in llm.prompts[0]
    assert "Do not include hashtags." in llm.prompts[0]
    assert "Career Growth" in llm.prompts[0]
    assert "Hinglish" in llm.prompts[0]


def test_build_variants_prompt_requests_json_three_variants_and_locked_angles():
    prompt = build_variants_prompt(
        "Medium",
        "English",
        "AI",
        [{"text": "Example 1 text", "match_label": "Exact match"}],
        options=GenerationOptions(cta_strength="Soft", hashtag_count=1),
    )

    assert 'Return only a JSON object with exactly one key: "variants".' in prompt
    assert 'The "variants" value must be an array of exactly 3 non-empty strings.' in prompt
    assert "Use compact LinkedIn-ready line breaks so the post reads as about 6 to 10 visible lines." in prompt
    assert "do not add blank spacer lines between every sentence." in prompt
    assert "Keep one short idea per line, with no empty line between every sentence." in prompt
    assert "Do not use markdown bullets unless they genuinely improve readability." in prompt
    assert "Use 1-2 relevant professional emojis only when they feel natural" in prompt
    assert "do not use emojis on every line." in prompt
    assert 'encode those line breaks inside each string as "\\n"' in prompt
    assert "If hashtags are included, place them alone on the final line only." in prompt
    assert "Variant 1 must use an insight-led hook." in prompt
    assert "Variant 2 must use a story/problem-solution hook." in prompt
    assert "Variant 3 must use an action/takeaway-led hook." in prompt
    assert "Close with a light reflective or conversational call to action." in prompt
    assert "Include exactly 1 relevant hashtag on the final line only" in prompt


def test_generate_post_variants_parses_unfenced_json_response():
    llm = StubLLM(
        [
            json.dumps(
                {
                    "variants": [
                        "Variant one",
                        "Variant two",
                        "Variant three",
                    ]
                }
            )
        ]
    )

    variants = generate_post_variants(
        "Short",
        "English",
        "AI",
        llm_client=llm,
        repository=StubRepository(),
    )

    assert variants == ["Variant one", "Variant two", "Variant three"]


def test_generate_post_variants_parses_fenced_json_response():
    llm = StubLLM(
        [
            """```json
            {
              "variants": [
                "Variant one",
                "Variant two",
                "Variant three"
              ]
            }
            ```"""
        ]
    )

    variants = generate_post_variants(
        "Short",
        "English",
        "AI",
        llm_client=llm,
        repository=StubRepository(),
    )

    assert variants == ["Variant one", "Variant two", "Variant three"]


def test_generate_post_variants_parses_fenced_json_with_raw_string_newlines():
    llm = StubLLM(
        [
            """```json
            {
              "variants": [
                "Variant one first line.
Variant one second line.",
                "Variant two first line.
Variant two second line.",
                "Variant three first line.
Variant three second line."
              ]
            }
            ```"""
        ]
    )

    variants = generate_post_variants(
        "Short",
        "English",
        "AI",
        llm_client=llm,
        repository=StubRepository(),
    )

    assert variants == [
        "Variant one first line.\nVariant one second line.",
        "Variant two first line.\nVariant two second line.",
        "Variant three first line.\nVariant three second line.",
    ]


def test_generate_post_variants_parses_valid_json_with_escaped_newlines():
    llm = StubLLM(
        [
            json.dumps(
                {
                    "variants": [
                        "Variant one first line.\nVariant one second line.",
                        "Variant two first line.\nVariant two second line.",
                        "Variant three first line.\nVariant three second line.",
                    ]
                }
            )
        ]
    )

    variants = generate_post_variants(
        "Short",
        "English",
        "AI",
        llm_client=llm,
        repository=StubRepository(),
    )

    assert variants[0] == "Variant one first line.\nVariant one second line."
    assert variants[1] == "Variant two first line.\nVariant two second line."
    assert variants[2] == "Variant three first line.\nVariant three second line."


def test_generate_post_variants_normalizes_single_paragraph_output_into_lines():
    llm = StubLLM(
        [
            json.dumps(
                {
                    "variants": [
                        "First point explains the main lesson. Second point adds the proof. Final takeaway closes the post #AI #Career",
                        "Another variant with two sentences. It should also break into lines #AI",
                        "Already multiline\nkeeps its structure\n#AI",
                    ]
                }
            )
        ]
    )

    variants = generate_post_variants(
        "Medium",
        "English",
        "AI",
        llm_client=llm,
        repository=StubRepository(),
    )

    assert variants[0] == (
        "First point explains the main lesson.\n"
        "Second point adds the proof.\n"
        "Final takeaway closes the post\n"
        "#AI #Career"
    )
    assert variants[1] == (
        "Another variant with two sentences.\n"
        "It should also break into lines\n"
        "#AI"
    )
    assert variants[2] == "Already multiline\nkeeps its structure\n#AI"


def test_generate_post_variants_removes_blank_spacer_lines_for_linkedin_paste():
    llm = StubLLM(
        [
            json.dumps(
                {
                    "variants": [
                        "First idea.\n\nSecond idea.\n\nThird idea.\n\n#AI #Amazon",
                        "Compact first line.\nCompact second line.",
                        "Opening line.\n\nProof line.\n\nTakeaway line.",
                    ]
                }
            )
        ]
    )

    variants = generate_post_variants(
        "Medium",
        "English",
        "Amazon",
        llm_client=llm,
        repository=StubRepository(),
    )

    assert variants[0] == "First idea.\nSecond idea.\nThird idea.\n#AI #Amazon"
    assert variants[1] == "Compact first line.\nCompact second line."
    assert variants[2] == "Opening line.\nProof line.\nTakeaway line."


def test_generate_post_preserves_meaning_while_compacting_blank_lines():
    llm = StubLLM(["Hook line.\n\nProof line.\n\nFinal thought."])

    result = generate_post(
        "Short",
        "English",
        "AI",
        llm_client=llm,
        repository=StubRepository(),
    )

    assert result == "Hook line.\nProof line.\nFinal thought."


def test_generate_post_variants_rejects_malformed_json():
    llm = StubLLM(["not json"])

    with pytest.raises(ValueError):
        generate_post_variants(
            "Short",
            "English",
            "AI",
            llm_client=llm,
            repository=StubRepository(),
        )


def test_generate_post_variants_rejects_wrong_variant_count():
    llm = StubLLM([json.dumps({"variants": ["Only one", "Only two"]})])

    with pytest.raises(ValueError):
        generate_post_variants(
            "Short",
            "English",
            "AI",
            llm_client=llm,
            repository=StubRepository(),
        )


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

    prompt = get_prompt(
        "Short",
        "English",
        "AI",
        repository=FewShotPosts(dataset_path),
        options=GenerationOptions(tone="Conversational", hashtag_count=1),
    )

    assert "- Tone: Conversational" in prompt
    assert "Example 1 (Exact match)" in prompt
    assert "Example 2 (Same tag and language; length relaxed)" in prompt
    assert "Example 3 (Same tag; language and length relaxed)" in prompt
    assert "Example 4 (Global fallback)" in prompt
    assert "Example 5 (Global fallback)" in prompt
    assert "Third global fallback product example" not in prompt


def test_get_variants_prompt_handles_sparse_hinglish_requests_with_cross_language_fallback(tmp_path):
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

    prompt = get_variants_prompt(
        "Long",
        "Hinglish",
        "AI",
        repository=FewShotPosts(dataset_path),
        options=GenerationOptions(audience="Founders", voice="First Person"),
    )

    assert "- Audience: Founders" in prompt
    assert "Use first-person singular language such as I, me, and my." in prompt
    assert "Example 1 (Same tag; language and length relaxed)" in prompt
    assert "Example 4 (Global fallback)" in prompt
    assert "Exact match" not in prompt
