"""Tests for Confluence write-response privacy contracts."""

import json
from datetime import datetime, timezone
from typing import Any

import pytest
from fastmcp import FastMCP

from mcp_atlassian_with_bitbucket_and_privacy.privacy import (
    ConfluenceIdentityAdapter,
    IdentityPolicy,
    IdentityPrivacyConfig,
    PrivacyMode,
    get_tool_response_policy,
    install_identity_privacy,
)

_NOW = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)
_CONTENT = "<p>Unstructured body may mention human01 and CANARY PERSON.</p>"


def _config() -> IdentityPrivacyConfig:
    return IdentityPrivacyConfig(
        mode=PrivacyMode.PSEUDONYMIZE,
        policy=IdentityPolicy.from_mapping(
            {
                "human_username_max_length": 8,
                "expose_service_display_name_and_login": True,
                "internal_logins": ["human01", "service-account"],
            }
        ),
        pseudonym_key=b"k" * 32,
        correlation_domain="test-deployment",
    )


def _adapter() -> ConfluenceIdentityAdapter:
    return ConfluenceIdentityAdapter(
        _config(),
        instance="https://confluence.example",
        clock=lambda: _NOW,
    )


def _human_user() -> dict[str, Any]:
    return {
        "account_id": "CANARY-CLOUD-ACCOUNT-ID",
        "username": "human01",
        "user_key": "CANARY-USER-KEY",
        "display_name": "CANARY PERSON",
        "email": "canary@example.test",
        "profile_picture": "/wiki/avatar/CANARY",
    }


def _transform(value: Any, tool_name: str) -> Any:
    return _adapter().transform(
        tool_name=tool_name,
        policy=get_tool_response_policy(tool_name),
        value=value,
        current_identity=None,
    )


def test_page_write_response_protects_metadata_and_preserves_content() -> None:
    result = _transform(
        {
            "message": "Page created successfully",
            "page": {
                "author": _human_user(),
                "version_author": _human_user(),
                "content": {"value": _CONTENT, "format": "storage"},
            },
        },
        "confluence_create_page",
    )

    author = result["page"]["author"]
    assert author["username"].startswith("pid:v1:")
    assert author["account_id"] == author["username"]
    assert author["user_key"] == author["username"]
    assert author["email"] is None
    assert author["profile_picture"] is None
    assert result["page"]["version_author"]["username"] == author["username"]
    assert result["page"]["content"] == {
        "value": _CONTENT,
        "format": "storage",
    }


def test_comment_write_response_preserves_comment_body() -> None:
    result = _transform(
        {
            "success": True,
            "comment": {
                "author": _human_user(),
                "body": _CONTENT,
            },
        },
        "confluence_add_comment",
    )

    assert result["comment"]["author"]["username"].startswith("pid:v1:")
    assert result["comment"]["body"] == _CONTENT


def test_restriction_write_distinguishes_account_ids_from_service_logins() -> None:
    result = _transform(
        {
            "restrictions": {
                "read": {
                    "users": [{"account_id": "CANARY-CLOUD-ACCOUNT-ID"}],
                    "groups": ["customers"],
                },
                "update": {
                    "users": [
                        {
                            "username": "service-account",
                            "display_name": "Technical Sync",
                            "account_id": "CANARY-LOCAL-ID",
                        }
                    ],
                    "groups": ["operators"],
                },
            }
        },
        "confluence_set_page_restrictions",
    )

    cloud_identity = result["restrictions"]["read"]["users"][0]
    assert cloud_identity["account_id"].startswith("pid:v1:")
    assert "CANARY" not in str(cloud_identity)

    service_identity = result["restrictions"]["update"]["users"][0]
    assert service_identity["username"] == "service-account"
    assert service_identity["display_name"] == "Technical Sync"
    assert service_identity["account_id"] is None
    assert result["restrictions"]["read"]["groups"] == ["customers"]
    assert result["restrictions"]["update"]["groups"] == ["operators"]


def test_attachment_write_response_protects_author_metadata() -> None:
    result = _transform(
        {
            "message": "Attachment uploaded successfully",
            "attachment": {
                "id": "att-1",
                "title": "report.pdf",
                "createdBy": _human_user(),
                "comment": _CONTENT,
            },
        },
        "confluence_upload_attachment",
    )

    assert result["attachment"]["createdBy"]["username"].startswith("pid:v1:")
    assert result["attachment"]["title"] == "report.pdf"
    assert result["attachment"]["comment"] == _CONTENT


def test_label_write_response_is_not_misclassified_as_user() -> None:
    value = [{"id": "label-1", "name": "reviewed"}]

    assert _transform(value, "confluence_add_label") == value


@pytest.mark.anyio
async def test_write_arguments_are_unchanged_and_both_outputs_are_protected() -> None:
    server = FastMCP("confluence-write-privacy")
    install_identity_privacy(server, config=_config())
    received: dict[str, Any] = {}

    @server.tool(name="confluence_create_page")
    async def create_page(content: str) -> str:
        received["content"] = content
        return json.dumps(
            {
                "page": {
                    "author": _human_user(),
                    "content": {"value": content, "format": "storage"},
                }
            }
        )

    result = await server.call_tool(
        "confluence_create_page",
        {"content": _CONTENT},
    )

    assert received["content"] == _CONTENT
    assert result.structured_content is not None
    structured_result = result.structured_content["result"]
    assert isinstance(structured_result, str)
    structured = json.loads(structured_result)
    content = json.loads(result.content[0].text)
    assert structured == content
    assert structured["page"]["author"]["username"].startswith("pid:v1:")
    assert structured["page"]["content"]["value"] == _CONTENT
