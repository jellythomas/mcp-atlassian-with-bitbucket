"""Complete Confluence privacy contracts at the FastMCP client boundary."""

import json
from typing import Any

import pytest
from fastmcp import FastMCP

from mcp_atlassian_with_bitbucket_and_privacy.privacy import (
    TOOL_RESPONSE_POLICIES,
    IdentityPolicy,
    IdentityPrivacyConfig,
    PrivacyMode,
    ResponseCategory,
    ToolResponsePolicy,
    ToolService,
    install_identity_privacy,
)

_CONFLUENCE_POLICIES = sorted(
    (
        (tool_name, policy)
        for tool_name, policy in TOOL_RESPONSE_POLICIES.items()
        if policy.service is ToolService.CONFLUENCE
    ),
    key=lambda item: item[0],
)
_CONTENT = "<p>Unstructured content may mention human01 and CANARY PERSON.</p>"


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


def _cloud_user() -> dict[str, Any]:
    return {
        "accountId": "CANARY-CLOUD-ACCOUNT-ID",
        "displayName": "CANARY CLOUD UNKNOWN",
        "email": "canary.cloud@example.test",
        "profilePicture": {"path": "/wiki/avatar/CANARY-CLOUD"},
    }


def _dc_user() -> dict[str, Any]:
    return {
        "name": "human01",
        "userKey": "CANARY-DC-USER-KEY",
        "displayName": "CANARY DC HUMAN",
        "email": "canary.dc@example.test",
        "profilePicture": {"path": "/wiki/avatar/CANARY-DC"},
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool_name", "policy"),
    _CONFLUENCE_POLICIES,
    ids=[tool_name for tool_name, _ in _CONFLUENCE_POLICIES],
)
async def test_every_registered_confluence_tool_obeys_final_policy(
    tool_name: str,
    policy: ToolResponsePolicy,
) -> None:
    server = FastMCP(f"contract-{tool_name}")
    install_identity_privacy(server, config=_config())

    if policy.category is ResponseCategory.RAW:

        @server.tool(name=tool_name)
        async def raw_tool() -> str:
            return _CONTENT

        result = await server.call_tool(tool_name, {})

        assert result.content[0].text == _CONTENT
        assert result.structured_content == {"result": _CONTENT}
        return

    @server.tool(name=tool_name)
    async def protected_tool() -> dict[str, Any]:
        return {
            "author": _dc_user(),
            "content": {"value": "Ordinary content", "format": "storage"},
        }

    result = await server.call_tool(tool_name, {})

    assert result.structured_content is not None
    assert json.loads(result.content[0].text) == result.structured_content
    assert result.structured_content["author"]["name"].startswith("pid:v1:")
    assert result.structured_content["content"] == {
        "value": "Ordinary content",
        "format": "storage",
    }
    assert "CANARY" not in json.dumps(result.structured_content)


def test_contract_covers_all_registered_confluence_tools() -> None:
    assert len(_CONFLUENCE_POLICIES) == 35
    assert {policy.category for _, policy in _CONFLUENCE_POLICIES} == set(
        ResponseCategory
    )


@pytest.mark.anyio
async def test_combined_cloud_dc_contract_preserves_content_bodies() -> None:
    server = FastMCP("confluence-cloud-dc-contract")
    install_identity_privacy(server, config=_config())

    @server.tool(name="confluence_get_page")
    async def get_page() -> str:
        return json.dumps(
            {
                "page": {
                    "author": _dc_user(),
                    "version": {"number": 2, "by": _cloud_user()},
                    "content": {"value": _CONTENT, "format": "storage"},
                },
                "comments": [{"author": _dc_user(), "body": _CONTENT}],
                "search_results": [
                    {
                        "entity_type": "user",
                        "title": "CANARY SEARCH TITLE",
                        "user": _dc_user(),
                        "url": "/people/CANARY",
                    }
                ],
                "restrictions": {
                    "read": {
                        "users": [{"account_id": "CANARY-CLOUD-ACCOUNT-ID"}],
                        "groups": ["customers"],
                    }
                },
                "attachments": [
                    {
                        "title": "report.pdf",
                        "author": {
                            "account_id": "CANARY-ATTACHMENT-ACCOUNT-ID",
                            "display_name": "CANARY ATTACHMENT AUTHOR",
                        },
                        "comment": _CONTENT,
                    }
                ],
            }
        )

    result = await server.call_tool("confluence_get_page", {})

    assert result.structured_content is not None
    wrapped = result.structured_content["result"]
    assert isinstance(wrapped, str)
    protected = json.loads(wrapped)
    assert json.loads(result.content[0].text) == protected

    page = protected["page"]
    assert page["author"]["name"].startswith("pid:v1:")
    assert page["version"]["by"]["accountId"].startswith("pid:v1:")
    assert page["version"]["by"]["identity_class"] == {
        "affiliation": "unknown",
        "actor_type": "unknown",
    }
    assert page["content"]["value"] == _CONTENT

    comment = protected["comments"][0]
    assert comment["author"]["name"].startswith("pid:v1:")
    assert comment["body"] == _CONTENT

    search = protected["search_results"][0]
    assert search["user"]["name"].startswith("pid:v1:")
    assert "CANARY" not in search["title"]
    assert search["url"] is None

    restriction = protected["restrictions"]["read"]["users"][0]
    assert restriction["account_id"].startswith("pid:v1:")
    assert "CANARY" not in json.dumps(restriction)

    attachment = protected["attachments"][0]
    assert attachment["author"]["account_id"].startswith("pid:v1:")
    assert attachment["comment"] == _CONTENT
