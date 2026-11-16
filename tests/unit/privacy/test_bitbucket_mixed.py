"""Tests for Bitbucket mixed/raw response content preservation."""

from datetime import datetime, timezone
from typing import Any

from mcp_atlassian_with_bitbucket_and_privacy.privacy import (
    BitbucketIdentityAdapter,
    IdentityPolicy,
    IdentityPrivacyConfig,
    PrivacyMode,
    ResponseCategory,
    ToolResponsePolicy,
    ToolService,
)

_NOW = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)


def _adapter() -> BitbucketIdentityAdapter:
    config = IdentityPrivacyConfig(
        mode=PrivacyMode.PSEUDONYMIZE,
        policy=IdentityPolicy.from_mapping(
            {
                "human_username_max_length": 8,
                "internal_logins": ["human01"],
            }
        ),
        pseudonym_key=b"k" * 32,
        correlation_domain="test-deployment",
    )
    return BitbucketIdentityAdapter(
        config,
        instance="https://bitbucket.example",
        clock=lambda: _NOW,
    )


def _user() -> dict[str, Any]:
    return {
        "name": "human01",
        "displayName": "CANARY PERSON",
        "id": 42,
        "emailAddress": "canary@example.test",
        "links": {"self": [{"href": "https://example/users/42"}]},
    }


def _transform(tool_name: str, value: Any) -> Any:
    return _adapter().transform(
        tool_name=tool_name,
        policy=ToolResponsePolicy(
            service=ToolService.BITBUCKET,
            category=ResponseCategory.MIXED,
            opaque_string_result=True,
        ),
        value=value,
        current_identity=None,
    )


def test_diff_metadata_is_protected_but_lines_are_unchanged() -> None:
    source_line = '{"display_name":"CANARY CODE VALUE"}'
    result = _transform(
        "bitbucket_get_pull_request_diff",
        {
            "author": _user(),
            "diffs": [
                {
                    "hunks": [
                        {
                            "segments": [
                                {
                                    "lines": [
                                        {
                                            "line": source_line,
                                            "type": "CONTEXT",
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ],
        },
    )

    assert result["author"]["name"].startswith("pid:v1:")
    assert (
        result["diffs"][0]["hunks"][0]["segments"][0]["lines"][0]["line"] == source_line
    )


def test_code_search_snippet_is_opaque_while_repository_owner_is_protected() -> None:
    snippet = "const author = { display_name: 'CANARY' };"
    result = _transform(
        "bitbucket_search_code",
        [
            {
                "file": {"path": "src/app.ts"},
                "content_match": {"lines": [{"line": snippet}]},
                "repository": {"slug": "repo", "owner": _user()},
            }
        ],
    )

    assert result[0]["content_match"]["lines"][0]["line"] == snippet
    assert result[0]["repository"]["owner"]["name"].startswith("pid:v1:")


def test_blame_source_lines_remain_opaque_and_author_is_protected() -> None:
    source = "user = {'displayName': 'CANARY'}"
    result = _transform(
        "bitbucket_get_file_blame",
        {
            "blame": [
                {
                    "author": _user(),
                    "lines": [{"text": source, "lineNumber": 1}],
                }
            ]
        },
    )

    assert result["blame"][0]["author"]["name"].startswith("pid:v1:")
    assert result["blame"][0]["lines"][0]["text"] == source


def test_compare_commit_messages_remain_unchanged() -> None:
    message = "CANARY Person changed display_name parsing"
    result = _transform(
        "bitbucket_compare_commits",
        {
            "commits": [{"author": _user(), "message": message}],
            "values": [{"path": "a.json", "content": '{"user":"CANARY"}'}],
        },
    )

    assert result["commits"][0]["author"]["name"].startswith("pid:v1:")
    assert result["commits"][0]["message"] == message
    assert result["values"][0]["content"] == '{"user":"CANARY"}'
