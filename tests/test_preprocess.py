import json

import pytest

from linkedin_post_generator.preprocess import (
    LLMResponseError,
    extract_metadata,
    get_unified_tags,
    process_posts,
)


class StubResponse:
    def __init__(self, content):
        self.content = content


class StubLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return StubResponse(response)


def test_extract_metadata_parses_valid_json_and_counts_lines():
    llm = StubLLM(
        [
            json.dumps(
                {
                    "language": "English",
                    "tags": ["Career", "AI"],
                }
            )
        ]
    )

    metadata = extract_metadata(
        "A sample post with enough detail to stay useful for readers today.\n"
        "A second line adds one more concrete takeaway for them.",
        llm_client=llm,
    )

    assert metadata == {
        "line_count": 2,
        "language": "English",
        "tags": ["Career", "AI"],
    }


def test_extract_metadata_parses_fenced_json():
    llm = StubLLM(
        [
            """```json
            {
              "language": "English",
              "tags": ["electricity", "bill gates"]
            }
            ```"""
        ]
    )

    metadata = extract_metadata(
        "A fenced response with enough context for readers.\n"
        "Another line keeps the line count deterministic.",
        llm_client=llm,
    )

    assert metadata == {
        "line_count": 2,
        "language": "English",
        "tags": ["electricity", "bill gates"],
    }


def test_extract_metadata_rejects_invalid_json():
    llm = StubLLM(["not json"])

    with pytest.raises(LLMResponseError):
        extract_metadata("Broken post with enough detail to be valid input.", llm_client=llm)


def test_get_unified_tags_returns_mapping():
    llm = StubLLM([json.dumps({"Job Hunting": "Job Search", "Jobseekers": "Job Search"})])

    mapping = get_unified_tags(
        [
            {"tags": ["Job Hunting"]},
            {"tags": ["Jobseekers"]},
        ],
        llm_client=llm,
    )

    assert mapping == {"Job Hunting": "Job Search", "Jobseekers": "Job Search"}


def test_process_posts_enriches_and_writes_output(tmp_path):
    raw_path = tmp_path / "raw_posts.json"
    processed_path = tmp_path / "processed_posts.json"
    raw_path.write_text(
        json.dumps(
            [
                {
                    "text": "Post one explains a useful career lesson with clear next steps today.",
                    "engagement": 5,
                },
                {
                    "text": (
                        "Post two mixes Hindi and English ideas for growth in practical ways.\n"
                        "Yeh advice beginners ko visible proof build karne mein help karta hai."
                    ),
                    "engagement": 7,
                },
            ]
        ),
        encoding="utf-8",
    )

    llm = StubLLM(
        [
            json.dumps({"language": "English", "tags": ["Job Hunting"]}),
            json.dumps({"language": "Hinglish", "tags": ["Jobseekers"]}),
            json.dumps({"Job Hunting": "Job Search", "Jobseekers": "Job Search"}),
        ]
    )

    processed_posts = process_posts(raw_path, processed_path, llm_client=llm)

    assert processed_posts == [
        {
            "text": "Post one explains a useful career lesson with clear next steps today.",
            "engagement": 5,
            "line_count": 1,
            "language": "English",
            "tags": ["Job Search"],
        },
        {
            "text": (
                "Post two mixes Hindi and English ideas for growth in practical ways.\n"
                "Yeh advice beginners ko visible proof build karne mein help karta hai."
            ),
            "engagement": 7,
            "line_count": 2,
            "language": "Hinglish",
            "tags": ["Job Search"],
        },
    ]
    assert set(processed_posts[0]) == {"text", "engagement", "line_count", "language", "tags"}
    assert json.loads(processed_path.read_text(encoding="utf-8")) == processed_posts


def test_process_posts_rejects_missing_text(tmp_path):
    raw_path = tmp_path / "raw_posts.json"
    raw_path.write_text(json.dumps([{"engagement": 1}]), encoding="utf-8")

    with pytest.raises(ValueError):
        process_posts(raw_path, tmp_path / "processed_posts.json", llm_client=StubLLM([]))


def test_process_posts_retries_transient_failures_and_writes_checkpoint(tmp_path):
    raw_path = tmp_path / "raw_posts.json"
    processed_path = tmp_path / "processed_posts.json"
    raw_path.write_text(
        json.dumps(
            [
                {
                    "text": (
                        "Career advice becomes stronger when you build proof through projects.\n"
                        "Share outcomes weekly so recruiters can see visible momentum."
                    ),
                    "engagement": 9,
                }
            ]
        ),
        encoding="utf-8",
    )

    llm = StubLLM(
        [
            RuntimeError("temporary timeout"),
            json.dumps({"language": "English", "tags": ["Career"]}),
            json.dumps({"Career": "Career Growth"}),
        ]
    )

    processed_posts = process_posts(
        raw_path,
        processed_path,
        llm_client=llm,
        max_retries=1,
    )

    checkpoint_path = tmp_path / "processed_posts.checkpoint.json"
    failures_path = tmp_path / "processed_posts.failures.json"

    assert processed_posts == [
        {
            "text": (
                "Career advice becomes stronger when you build proof through projects.\n"
                "Share outcomes weekly so recruiters can see visible momentum."
            ),
            "engagement": 9,
            "line_count": 2,
            "language": "English",
            "tags": ["Career Growth"],
        }
    ]
    assert len(json.loads(checkpoint_path.read_text(encoding="utf-8"))["records"]) == 1
    assert json.loads(failures_path.read_text(encoding="utf-8")) == []
    assert len(llm.prompts) == 3


def test_process_posts_resumes_from_checkpoint_without_repeating_metadata(tmp_path):
    raw_path = tmp_path / "raw_posts.json"
    processed_path = tmp_path / "processed_posts.json"
    checkpoint_path = tmp_path / "processed_posts.checkpoint.json"
    checkpoint_text = (
        "Checkpointed advice shows how building public proof improves career momentum."
    )
    raw_path.write_text(
        json.dumps([{"text": checkpoint_text, "engagement": 3}]),
        encoding="utf-8",
    )
    checkpoint_path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "index": 0,
                        "post": {
                            "text": checkpoint_text,
                            "engagement": 3,
                            "line_count": 1,
                            "language": "English",
                            "tags": ["Career"],
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    llm = StubLLM([json.dumps({"Career": "Career Growth"})])

    processed_posts = process_posts(
        raw_path,
        processed_path,
        llm_client=llm,
        max_retries=1,
    )

    assert processed_posts == [
        {
            "text": checkpoint_text,
            "engagement": 3,
            "line_count": 1,
            "language": "English",
            "tags": ["Career Growth"],
        }
    ]
    assert llm.prompts == [llm.prompts[0]]
    assert "I will give you a list of tags." in llm.prompts[0]


def test_process_posts_reports_quality_and_retry_exhaustion(tmp_path):
    raw_path = tmp_path / "raw_posts.json"
    processed_path = tmp_path / "processed_posts.json"
    raw_path.write_text(
        json.dumps(
            [
                {
                    "text": (
                        "Career insight becomes clearer when you document proof every week.\n"
                        "Build in public so the right opportunities can find you faster."
                    ),
                    "engagement": 5,
                },
                {
                    "text": "Activate to view larger image,\nactivate to view larger image,",
                    "engagement": 0,
                },
                {
                    "text": (
                        "Broken output post still has enough detail to reach metadata extraction.\n"
                        "It should fail only because the model returns invalid JSON twice."
                    ),
                    "engagement": 1,
                },
            ]
        ),
        encoding="utf-8",
    )

    llm = StubLLM(
        [
            json.dumps({"language": "English", "tags": ["Career"]}),
            "not json",
            "still not json",
            json.dumps({"Career": "Career Growth"}),
        ]
    )

    processed_posts = process_posts(
        raw_path,
        processed_path,
        llm_client=llm,
        max_retries=1,
    )

    failures_path = tmp_path / "processed_posts.failures.json"
    failures = json.loads(failures_path.read_text(encoding="utf-8"))

    assert processed_posts == [
        {
            "text": (
                "Career insight becomes clearer when you document proof every week.\n"
                "Build in public so the right opportunities can find you faster."
            ),
            "engagement": 5,
            "line_count": 2,
            "language": "English",
            "tags": ["Career Growth"],
        }
    ]
    assert {failure["reason"] for failure in failures} == {
        "image_placeholder",
        "retry_exhausted",
    }
    assert {failure["stage"] for failure in failures} == {
        "quality_filter",
        "metadata_extraction",
    }
    assert any(
        failure["text_preview"].startswith("Activate to view larger image")
        for failure in failures
    )
    assert "Career" in llm.prompts[-1]
    assert "Broken output post" not in llm.prompts[-1]


def test_process_posts_filters_title_only_and_cta_trimmed_posts(tmp_path):
    raw_path = tmp_path / "raw_posts.json"
    processed_path = tmp_path / "processed_posts.json"
    raw_path.write_text(
        json.dumps(
            [
                {"text": "Why NVIDIA built nemotron", "engagement": 0},
                {
                    "text": "Enjoyed sharing this at ces. Hope you take a moment to watch.",
                    "engagement": 8,
                },
            ]
        ),
        encoding="utf-8",
    )

    llm = StubLLM([])

    processed_posts = process_posts(raw_path, processed_path, llm_client=llm)
    failures_path = tmp_path / "processed_posts.failures.json"
    failures = json.loads(failures_path.read_text(encoding="utf-8"))

    assert processed_posts == []
    assert {failure["reason"] for failure in failures} == {"thin_post"}
    assert {failure["stage"] for failure in failures} == {"quality_filter"}
    assert llm.prompts == []


def test_process_posts_deduplicates_near_matches_and_keeps_stronger_variant(tmp_path):
    raw_path = tmp_path / "raw_posts.json"
    processed_path = tmp_path / "processed_posts.json"
    first_text = (
        "From rockets to AI, teams learn faster when they publish experiments every week.\n"
        "Sharing results publicly builds trust and momentum across the company."
    )
    second_text = (
        "From rockets to AI, teams learn faster when they publish experiments each week.\n"
        "Sharing results publicly builds trust and momentum across the company."
    )
    raw_path.write_text(
        json.dumps(
            [
                {"text": first_text, "engagement": 5},
                {"text": second_text, "engagement": 20},
            ]
        ),
        encoding="utf-8",
    )

    llm = StubLLM(
        [
            json.dumps({"language": "English", "tags": ["AI"]}),
            json.dumps({"language": "English", "tags": ["AI"]}),
            json.dumps({"AI": "AI"}),
        ]
    )

    processed_posts = process_posts(raw_path, processed_path, llm_client=llm)
    failures_path = tmp_path / "processed_posts.failures.json"
    failures = json.loads(failures_path.read_text(encoding="utf-8"))

    assert processed_posts == [
        {
            "text": second_text,
            "engagement": 20,
            "line_count": 2,
            "language": "English",
            "tags": ["AI"],
        }
    ]
    assert [failure["reason"] for failure in failures] == ["near_duplicate"]
    assert failures[0]["stage"] == "final_deduplication"
    assert failures[0]["text_preview"].startswith("From rockets to AI, teams learn faster")


def test_process_posts_recomputes_line_count_after_trimming_cta_tail(tmp_path):
    raw_path = tmp_path / "raw_posts.json"
    processed_path = tmp_path / "processed_posts.json"
    raw_path.write_text(
        json.dumps(
            [
                {
                    "text": (
                        "Useful career advice helps new graduates stand out in crowded markets.\n"
                        "Build proof by sharing weekly project updates with concrete outcomes.\n"
                        "Read more:"
                    ),
                    "engagement": 11,
                }
            ]
        ),
        encoding="utf-8",
    )

    llm = StubLLM(
        [
            json.dumps({"language": "English", "tags": ["Career"]}),
            json.dumps({"Career": "Career"}),
        ]
    )

    processed_posts = process_posts(raw_path, processed_path, llm_client=llm)

    assert processed_posts == [
        {
            "text": (
                "Useful career advice helps new graduates stand out in crowded markets.\n"
                "Build proof by sharing weekly project updates with concrete outcomes."
            ),
            "engagement": 11,
            "line_count": 2,
            "language": "English",
            "tags": ["Career"],
        }
    ]
