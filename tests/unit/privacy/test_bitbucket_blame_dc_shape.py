"""Blame responses in the Bitbucket Data Center shape: author and committer."""

import json
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

_NOW = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)


def _config() -> IdentityPrivacyConfig:
    return IdentityPrivacyConfig(
        mode=PrivacyMode.PSEUDONYMIZE,
        policy=IdentityPolicy.from_mapping(
            {"human_username_max_length": 8, "internal_logins": ["human01"]}
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


def _dc_person() -> dict[str, Any]:
    return {
        "active": True,
        "displayName": "CANARY PERSON",
        "emailAddress": "canary@example.test",
        "id": 42,
        "links": {"self": [{"href": "https://example/users/42"}]},
        "name": "human01",
        "slug": "human01",
        "type": "NORMAL",
    }


def _dc_blame_response() -> dict[str, Any]:
    return {
        "blame": [
            {
                "author": _dc_person(),
                "authorTimestamp": 1,
                "commitDisplayId": "abc1234",
                "commitHash": "a" * 40,
                "commitId": "a" * 40,
                "committer": _dc_person(),
                "committerTimestamp": 1,
                "displayCommitHash": "abc1234",
                "fileName": "docker-compose.yml",
                "lineNumber": 1,
                "spannedLines": 1,
            }
        ],
        "isLastPage": True,
        "lines": [{"text": "image: example"}],
        "limit": 500,
        "nextPageStart": None,
        "size": 1,
        "start": 0,
    }


def test_dc_blame_author_and_committer_are_pseudonymized() -> None:
    result = _adapter().transform(
        tool_name="bitbucket_get_file_blame",
        policy=ToolResponsePolicy(
            service=ToolService.BITBUCKET,
            category=ResponseCategory.MIXED,
            opaque_string_result=True,
        ),
        value=_dc_blame_response(),
        current_identity=None,
    )

    entry = result["blame"][0]
    assert entry["author"]["name"].startswith("pid:v1:")
    assert entry["committer"]["name"].startswith("pid:v1:")
    dumped = json.dumps(result)
    assert "CANARY PERSON" not in dumped
    assert "canary@example.test" not in dumped
    assert result["lines"][0]["text"] == "image: example"


@pytest.mark.anyio
async def test_dc_blame_passes_through_server_middleware() -> None:
    server = FastMCP("bitbucket-dc-blame-shape")
    install_identity_privacy(server, config=_config())

    @server.tool(name="bitbucket_get_file_blame")
    async def get_file_blame() -> dict[str, Any]:
        return _dc_blame_response()

    result = await server.call_tool("bitbucket_get_file_blame", {})

    assert result.structured_content is not None
    dumped = json.dumps(result.structured_content)
    assert "CANARY PERSON" not in dumped
    assert "canary@example.test" not in dumped
    assert result.structured_content["blame"][0]["author"]["name"].startswith("pid:v1:")


@pytest.mark.anyio
async def test_dc_blame_as_json_string_is_protected_like_the_live_tool() -> None:
    server = FastMCP("bitbucket-dc-blame-json-string")
    install_identity_privacy(server, config=_config())

    @server.tool(name="bitbucket_get_file_blame")
    async def get_file_blame() -> str:
        return json.dumps(_dc_blame_response(), indent=2, ensure_ascii=False)

    result = await server.call_tool("bitbucket_get_file_blame", {})

    dumped = json.dumps(result.structured_content or json.loads(result.content[0].text))
    assert "CANARY PERSON" not in dumped
    assert "canary@example.test" not in dumped
    assert "pid:v1:" in dumped
