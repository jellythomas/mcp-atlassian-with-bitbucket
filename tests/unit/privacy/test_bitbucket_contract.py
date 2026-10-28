"""Complete Bitbucket privacy contracts at the FastMCP client boundary."""

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

_BITBUCKET_POLICIES = sorted(
    (
        (tool_name, policy)
        for tool_name, policy in TOOL_RESPONSE_POLICIES.items()
        if policy.service is ToolService.BITBUCKET
    ),
    key=lambda item: item[0],
)
_OPAQUE_SOURCE = '{"display_name":"CANARY OPAQUE SOURCE"}'


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
        "type": "user",
        "display_name": "CANARY CLOUD HUMAN",
        "nickname": "human01",
        "account_id": "CANARY-CLOUD-ACCOUNT-ID",
        "uuid": "{CANARY-CLOUD-UUID}",
        "links": {
            "self": {"href": "https://api.example/CANARY"},
            "avatar": {"href": "https://avatar.example/CANARY"},
        },
    }


def _dc_user() -> dict[str, Any]:
    return {
        "id": 42,
        "name": "human01",
        "slug": "human01",
        "displayName": "CANARY DC HUMAN",
        "emailAddress": "canary@example.test",
        "active": True,
        "links": {"self": [{"href": "https://bitbucket.example/users/CANARY"}]},
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool_name", "policy"),
    _BITBUCKET_POLICIES,
    ids=[tool_name for tool_name, _ in _BITBUCKET_POLICIES],
)
async def test_every_registered_bitbucket_tool_obeys_final_policy(
    tool_name: str,
    policy: ToolResponsePolicy,
) -> None:
    server = FastMCP(f"contract-{tool_name}")
    install_identity_privacy(server, config=_config())

    if policy.category is ResponseCategory.RAW or policy.opaque_string_result:

        @server.tool(name=tool_name)
        async def opaque_tool() -> str:
            return _OPAQUE_SOURCE

        result = await server.call_tool(tool_name, {})

        assert result.content[0].text == _OPAQUE_SOURCE
        assert result.structured_content == {"result": _OPAQUE_SOURCE}
        return

    @server.tool(name=tool_name)
    async def structured_tool() -> dict[str, Any]:
        return {
            "author": _dc_user(),
            "payload": "unchanged",
        }

    result = await server.call_tool(tool_name, {})

    assert result.structured_content is not None
    assert json.loads(result.content[0].text) == result.structured_content
    assert result.structured_content["author"]["name"].startswith("pid:v1:")
    assert result.structured_content["payload"] == "unchanged"
    assert "CANARY" not in json.dumps(result.structured_content)


def test_contract_covers_all_registered_bitbucket_tools() -> None:
    assert len(_BITBUCKET_POLICIES) == 64
    assert {policy.category for _, policy in _BITBUCKET_POLICIES} == set(
        ResponseCategory
    )


@pytest.mark.anyio
async def test_cloud_and_dc_identities_are_protected_at_client_boundary() -> None:
    server = FastMCP("bitbucket-cloud-dc-contract")
    install_identity_privacy(server, config=_config())

    @server.tool(name="bitbucket_get_pull_request")
    async def get_pull_request() -> dict[str, Any]:
        return {
            "author": _cloud_user(),
            "reviewers": [_dc_user()],
            "description": "Ordinary pull-request body",
        }

    result = await server.call_tool("bitbucket_get_pull_request", {})

    assert result.structured_content is not None
    assert json.loads(result.content[0].text) == result.structured_content
    assert result.structured_content["author"]["nickname"].startswith("pid:v1:")
    assert result.structured_content["reviewers"][0]["name"].startswith("pid:v1:")
    assert result.structured_content["description"] == "Ordinary pull-request body"
    assert "CANARY" not in json.dumps(result.structured_content)


@pytest.mark.anyio
async def test_mixed_structured_metadata_is_protected_but_source_is_opaque() -> None:
    server = FastMCP("bitbucket-mixed-contract")
    install_identity_privacy(server, config=_config())
    source = '{"displayName":"CANARY SOURCE LINE"}'

    @server.tool(name="bitbucket_get_file_blame")
    async def get_file_blame() -> dict[str, Any]:
        return {
            "blame": [
                {
                    "author": _dc_user(),
                    "lines": [{"lineNumber": 1, "text": source}],
                }
            ]
        }

    result = await server.call_tool("bitbucket_get_file_blame", {})

    assert result.structured_content is not None
    blame = result.structured_content["blame"][0]
    assert blame["author"]["name"].startswith("pid:v1:")
    assert blame["lines"][0]["text"] == source
