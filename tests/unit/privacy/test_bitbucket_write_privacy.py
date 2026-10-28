"""Tests for Bitbucket write responses and identity-bearing metadata."""

from datetime import datetime, timezone
from typing import Any

import pytest
from fastmcp import FastMCP

from mcp_atlassian_with_bitbucket_and_privacy.privacy import (
    BitbucketIdentityAdapter,
    IdentityPolicy,
    IdentityPrivacyConfig,
    PrivacyMode,
    ResponseCategory,
    ToolResponsePolicy,
    ToolService,
    install_identity_privacy,
)

_NOW = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)


def _config() -> IdentityPrivacyConfig:
    return IdentityPrivacyConfig(
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


def _adapter() -> BitbucketIdentityAdapter:
    return BitbucketIdentityAdapter(
        _config(),
        instance="https://bitbucket.example",
        clock=lambda: _NOW,
    )


def _user() -> dict[str, Any]:
    return {
        "name": "human01",
        "displayName": "CANARY PERSON",
        "id": 42,
        "emailAddress": "canary@example.test",
        "links": {"self": [{"href": "https://example/users/human01"}]},
    }


def _transform(value: Any, tool_name: str) -> Any:
    return _adapter().transform(
        tool_name=tool_name,
        policy=ToolResponsePolicy(
            service=ToolService.BITBUCKET,
            category=ResponseCategory.STRUCTURED,
        ),
        value=value,
        current_identity=None,
    )


def test_write_response_user_is_protected() -> None:
    result = _transform(
        {
            "id": 42,
            "title": "Created PR",
            "author": _user(),
            "reviewers": [{"user": _user(), "role": "REVIEWER"}],
        },
        "bitbucket_create_pull_request",
    )

    assert result["author"]["name"].startswith("pid:v1:")
    assert result["reviewers"][0]["user"]["name"].startswith("pid:v1:")
    assert result["reviewers"][0]["role"] == "REVIEWER"
    assert "CANARY" not in str(result)


def test_personal_repository_paths_use_protected_owner_identifier() -> None:
    result = _transform(
        {
            "name": "repo",
            "slug": "repo",
            "full_name": "human01/repo",
            "key": "~human01",
            "owner": _user(),
            "links": {
                "html": {"href": "https://bitbucket.example/human01/repo"},
                "clone": [{"href": "ssh://git@bitbucket.example/human01/repo.git"}],
            },
        },
        "bitbucket_get_repository",
    )

    protected = result["owner"]["name"]
    assert protected.startswith("pid:v1:")
    assert result["full_name"] == f"{protected}/repo"
    assert result["key"] == f"~{protected}"
    assert "human01" not in str(result["links"])
    assert protected in str(result["links"])


@pytest.mark.parametrize(
    "path,expected_name",
    [
        (
            r"C:\Users\CANARY\AppData\Local\Temp\bitbucket-diff.patch",
            "bitbucket-diff.patch",
        ),
        ("/tmp/CANARY/bitbucket-diff.patch", "bitbucket-diff.patch"),
    ],
)
def test_server_local_artifact_path_is_redacted(
    path: str,
    expected_name: str,
) -> None:
    result = _transform(
        {
            "saved_to_file": True,
            "file_path": path,
            "message": f"Diff saved to {path}",
            "line_count": 12,
        },
        "bitbucket_get_pull_request_diff",
    )

    assert result["file_path"] is None
    assert result["file_name"] == expected_name
    assert "CANARY" not in result["message"]
    assert "<server-local-path-redacted>" in result["message"]
    assert result["line_count"] == 12


@pytest.mark.anyio
async def test_write_arguments_are_unchanged_and_response_is_protected() -> None:
    server = FastMCP("bitbucket-write-privacy")
    install_identity_privacy(server, config=_config())
    received: dict[str, Any] = {}

    @server.tool(name="bitbucket_create_pull_request")
    async def create_pull_request(reviewers: list[str]) -> dict[str, Any]:
        received["reviewers"] = reviewers
        return {
            "title": "Created PR",
            "author": _user(),
            "reviewers": [{"user": _user()}],
        }

    result = await server.call_tool(
        "bitbucket_create_pull_request",
        {"reviewers": ["human01"]},
    )

    assert received["reviewers"] == ["human01"]
    assert result.structured_content is not None
    assert result.structured_content["author"]["name"].startswith("pid:v1:")
    assert "CANARY" not in str(result.structured_content)


def test_source_file_path_is_not_treated_as_server_artifact() -> None:
    value = {
        "file": {"path": "src/users/CANARY.py"},
        "repository": {"slug": "repo"},
    }

    assert _transform(value, "bitbucket_search_code") == value
