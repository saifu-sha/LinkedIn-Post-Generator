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
        return StubResponse(self.responses.pop(0))


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
