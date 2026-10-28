"""End-to-end Jira privacy contracts at the FastMCP client boundary."""

import json
from copy import deepcopy
from typing import Any

import pytest
from fastmcp import FastMCP

from mcp_atlassian_with_bitbucket_and_privacy.privacy import (
    IdentityPolicy,
    IdentityPrivacyConfig,
    PrivacyMode,
    install_identity_privacy,
)


def _config() -> IdentityPrivacyConfig:
    return IdentityPrivacyConfig(
        mode=PrivacyMode.PSEUDONYMIZE,
        policy=IdentityPolicy.from_mapping(
            {
                "human_username_max_length": 8,
                "expose_service_display_name_and_login": True,
                "internal_logins": ["human01", "service-account"],
                "external_logins": ["customer"],
                "jira_identity_text_rules": [
                    {
                        "field_id": "customfield_10003",
                        "patterns": [r"owner=(?P<identity>[a-z0-9-]+)"],
                    }
                ],
            }
        ),
        pseudonym_key=b"k" * 32,
        correlation_domain="test-deployment",
    )


def _dc_human() -> dict[str, Any]:
    return {
        "name": "human01",
        "displayName": "CANARY DC HUMAN",
        "key": "CANARY-DC-KEY",
        "emailAddress": "canary.dc@example.test",
        "avatarUrls": {"48x48": "https://avatar.example/CANARY-DC"},
    }


def _external_human() -> dict[str, Any]:
    return {
        "name": "customer",
        "displayName": "CANARY EXTERNAL HUMAN",
        "key": "CANARY-EXTERNAL-KEY",
        "emailAddress": "canary.external@example.test",
    }


def _unknown_cloud_user() -> dict[str, Any]:
    return {
        "accountId": "CANARY-CLOUD-ACCOUNT-ID",
        "displayName": "CANARY CLOUD UNKNOWN",
        "emailAddress": "canary.cloud@example.test",
        "avatarUrls": {"48x48": "https://avatar.example/CANARY-CLOUD"},
    }


def _service_user() -> dict[str, Any]:
    return {
        "name": "service-account",
        "displayName": "Technical Sync Service",
        "key": "CANARY-SERVICE-KEY",
        "emailAddress": "service@example.test",
        "self": "https://jira.example/users/service-account",
    }


def _issue_payload() -> dict[str, Any]:
    return {
        "key": "TEST-1",
        "summary": "Identity contract",
        "assignee": _dc_human(),
        "reporter": _external_human(),
        "creator": _unknown_cloud_user(),
        "comments": [{"author": _dc_human(), "body": "Ordinary comment"}],
        "worklogs": [{"author": _external_human(), "time_spent": "1h"}],
        "watchers": [_service_user()],
        "customfield_10001": {
            "field_id": "customfield_10001",
            "name": "Reviewer",
            "value": _dc_human(),
            "_identity_schema": "user",
        },
        "customfield_10002": {
            "field_id": "customfield_10002",
            "name": "Approvers",
            "value": [_unknown_cloud_user(), "service-account"],
            "_identity_schema": "array:user",
        },
        "customfield_10003": {
            "field_id": "customfield_10003",
            "name": "Owner Login",
            "value": "owner=human01",
        },
        "changelogs": [
            {
                "items": [
                    {
                        "field": "assignee",
                        "from_id": "CANARY-OLD-ID",
                        "from_string": "CANARY OLD USER",
                        "to_id": "CANARY-NEW-ID",
                        "to_string": "CANARY NEW USER",
                    }
                ]
            }
        ],
    }


def _parse_wrapped_result(result: Any) -> dict[str, Any]:
    assert result.structured_content is not None
    wrapped = result.structured_content["result"]
    assert isinstance(wrapped, str)
    structured = json.loads(wrapped)
    assert json.loads(result.content[0].text) == structured
    return structured


@pytest.mark.anyio
async def test_combined_read_contract_blocks_human_and_unknown_canaries() -> None:
    server = FastMCP("jira-contract")
    install_identity_privacy(server, config=_config())

    @server.tool(name="jira_get_issue")
    async def get_issue() -> str:
        return json.dumps(_issue_payload())

    result = await server.call_tool("jira_get_issue", {})
    issue = _parse_wrapped_result(result)

    assert issue["assignee"]["name"].startswith("pid:v1:")
    assert issue["reporter"]["name"].startswith("pid:v1:")
    assert issue["creator"]["accountId"].startswith("pid:v1:")
    assert issue["creator"]["identity_class"] == {
        "affiliation": "unknown",
        "actor_type": "unknown",
    }
    assert issue["comments"][0]["author"]["name"].startswith("pid:v1:")
    assert issue["worklogs"][0]["author"]["name"].startswith("pid:v1:")

    service = issue["watchers"][0]
    assert service["name"] == "service-account"
    assert service["displayName"] == "Technical Sync Service"
    assert service["key"] is None
    assert service["emailAddress"] is None
    assert service["self"] is None

    reviewer = issue["customfield_10001"]["value"]
    approvers = issue["customfield_10002"]["value"]
    assert reviewer["name"].startswith("pid:v1:")
    assert approvers[0]["accountId"].startswith("pid:v1:")
    assert approvers[1] == "service-account"
    assert issue["customfield_10003"]["value"].startswith("owner=pid:v1:")
    assert "_identity_schema" not in str(issue)

    changelog = issue["changelogs"][0]["items"][0]
    assert changelog["from_id"] == changelog["from_string"]
    assert changelog["to_id"] == changelog["to_string"]
    assert "CANARY" not in json.dumps(issue)


@pytest.mark.anyio
async def test_write_contract_preserves_arguments_and_protects_response() -> None:
    server = FastMCP("jira-write-contract")
    install_identity_privacy(server, config=_config())
    received: dict[str, Any] = {}
    fields = {
        "description": "Write input remains unchanged",
        "customfield_10003": "owner=human01",
    }

    @server.tool(name="jira_update_issue")
    async def update_issue(
        assignee: str,
        update_fields: dict[str, Any],
    ) -> dict[str, Any]:
        received["assignee"] = assignee
        received["update_fields"] = deepcopy(update_fields)
        return {
            "success": True,
            "issue": {
                "assignee": _dc_human(),
                "reporter": _unknown_cloud_user(),
            },
        }

    result = await server.call_tool(
        "jira_update_issue",
        {
            "assignee": "human01",
            "update_fields": fields,
        },
    )

    assert received == {
        "assignee": "human01",
        "update_fields": fields,
    }
    assert result.structured_content is not None
    assert json.loads(result.content[0].text) == result.structured_content
    issue = result.structured_content["issue"]
    assert issue["assignee"]["name"].startswith("pid:v1:")
    assert issue["reporter"]["accountId"].startswith("pid:v1:")
    assert "CANARY" not in json.dumps(result.structured_content)
