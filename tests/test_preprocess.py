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


def test_extract_metadata_parses_valid_json():
    llm = StubLLM(
        [
            json.dumps(
                {
                    "line_count": 4,
                    "language": "English",
                    "tags": ["Career", "AI"],
                }
            )
        ]
    )

    metadata = extract_metadata("A sample post", llm_client=llm)

    assert metadata == {
        "line_count": 4,
        "language": "English",
        "tags": ["Career", "AI"],
    }


def test_extract_metadata_parses_fenced_json():
    llm = StubLLM(
        [
            """```json
            {
              "line_count": 1,
              "language": "English",
              "tags": ["electricity", "bill gates"]
            }
            ```"""
        ]
    )

    metadata = extract_metadata("A fenced response", llm_client=llm)

    assert metadata == {
        "line_count": 1,
        "language": "English",
        "tags": ["electricity", "bill gates"],
    }


def test_extract_metadata_rejects_invalid_json():
    llm = StubLLM(["not json"])

    with pytest.raises(LLMResponseError):
        extract_metadata("Broken post", llm_client=llm)


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
                {"text": "Post one", "engagement": 5},
                {"text": "Post two", "engagement": 7},
            ]
        ),
        encoding="utf-8",
    )

    llm = StubLLM(
        [
            json.dumps({"line_count": 3, "language": "English", "tags": ["Job Hunting"]}),
            json.dumps({"line_count": 8, "language": "Hinglish", "tags": ["Jobseekers"]}),
            json.dumps({"Job Hunting": "Job Search", "Jobseekers": "Job Search"}),
        ]
    )

    processed_posts = process_posts(raw_path, processed_path, llm_client=llm)

    assert processed_posts == [
        {
            "text": "Post one",
            "engagement": 5,
            "line_count": 3,
            "language": "English",
            "tags": ["Job Search"],
        },
        {
            "text": "Post two",
            "engagement": 7,
            "line_count": 8,
            "language": "Hinglish",
            "tags": ["Job Search"],
        },
    ]
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
        json.dumps([{"text": "Career advice\nBuild proof", "engagement": 9}]),
        encoding="utf-8",
    )

    llm = StubLLM(
        [
            RuntimeError("temporary timeout"),
            json.dumps({"line_count": 2, "language": "English", "tags": ["Career"]}),
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
            "text": "Career advice\nBuild proof",
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
    raw_path.write_text(
        json.dumps([{"text": "Checkpointed post", "engagement": 3}]),
        encoding="utf-8",
    )
    checkpoint_path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "index": 0,
                        "post": {
                            "text": "Checkpointed post",
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
            "text": "Checkpointed post",
            "engagement": 3,
            "line_count": 1,
            "language": "English",
            "tags": ["Career Growth"],
        }
    ]
    assert llm.prompts == [llm.prompts[0]]
    assert "I will give you a list of tags." in llm.prompts[0]


def test_process_posts_reports_low_quality_and_retry_exhaustion(tmp_path):
    raw_path = tmp_path / "raw_posts.json"
    processed_path = tmp_path / "processed_posts.json"
    raw_path.write_text(
        json.dumps(
            [
                {"text": "Career insight\nBuild proof", "engagement": 5},
                {
                    "text": "Activate to view larger image,\nactivate to view larger image,",
                    "engagement": 0,
                },
                {"text": "Broken output post", "engagement": 1},
            ]
        ),
        encoding="utf-8",
    )

    llm = StubLLM(
        [
            json.dumps({"line_count": 2, "language": "English", "tags": ["Career"]}),
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
            "text": "Career insight\nBuild proof",
            "engagement": 5,
            "line_count": 2,
            "language": "English",
            "tags": ["Career Growth"],
        }
    ]
    assert {failure["reason"] for failure in failures} == {
        "filtered_low_quality",
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
