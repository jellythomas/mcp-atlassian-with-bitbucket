"""Tests for standard Jira identity transformation."""

from datetime import datetime, timezone
from typing import Any

from fastmcp import FastMCP

from mcp_atlassian_with_bitbucket_and_privacy.privacy import (
    CurrentIdentity,
    IdentityPolicy,
    IdentityPrivacyConfig,
    IdentityResponseTransformer,
    JiraIdentityAdapter,
    PrivacyMode,
    ResponseCategory,
    ToolResponsePolicy,
    ToolService,
    install_identity_privacy,
)

_NOW = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)


def _policy() -> IdentityPolicy:
    return IdentityPolicy.from_mapping(
        {
            "human_username_max_length": 8,
            "expose_service_display_name_and_login": True,
            "internal_logins": ["human01", "service-account"],
            "external_logins": ["customer"],
        }
    )


def _config(mode: PrivacyMode = PrivacyMode.PSEUDONYMIZE) -> IdentityPrivacyConfig:
    return IdentityPrivacyConfig(
        mode=mode,
        policy=_policy(),
        pseudonym_key=b"k" * 32 if mode is PrivacyMode.PSEUDONYMIZE else None,
        correlation_domain="test-deployment",
        rotation_hours=24,
    )


def _adapter(mode: PrivacyMode = PrivacyMode.PSEUDONYMIZE) -> JiraIdentityAdapter:
    return JiraIdentityAdapter(
        _config(mode),
        instance="https://jira.example",
        clock=lambda: _NOW,
    )


def _transform(
    value: Any,
    *,
    adapter: JiraIdentityAdapter | None = None,
    current_identity: CurrentIdentity | None = None,
) -> Any:
    return (adapter or _adapter()).transform(
        tool_name="jira_get_user_profile",
        policy=ToolResponsePolicy(
            service=ToolService.JIRA,
            category=ResponseCategory.STRUCTURED,
        ),
        value=value,
        current_identity=current_identity,
    )


def test_pseudonymizes_simplified_dc_user() -> None:
    result = _transform(
        {
            "account_id": None,
            "display_name": "Sensitive Person",
            "name": "human01",
            "email": "sensitive@example.test",
            "avatar_url": "https://jira.example/avatar/human01",
            "key": "JIRAUSER1",
            "active": True,
        }
    )

    assert result["display_name"].startswith("Internal human H-")
    assert result["name"].startswith("pid:v1:")
    assert result["key"] == result["name"]
    assert result["email"] is None
    assert result["avatar_url"] is None
    assert result["active"] is True
    assert result["identity_class"] == {
        "affiliation": "internal",
        "actor_type": "human",
    }
    assert "Sensitive" not in str(result)


def test_cloud_display_name_is_not_mistaken_for_login() -> None:
    result = _transform(
        {
            "accountId": "cloud-account-id",
            "displayName": "Long Human Customer Name",
            "emailAddress": "customer@example.test",
            "avatarUrls": {"48x48": "https://avatar.example"},
        }
    )

    assert result["accountId"].startswith("pid:v1:")
    assert result["displayName"].startswith("Unknown unknown U-")
    assert result["emailAddress"] is None
    assert result["avatarUrls"] is None
    assert result["identity_class"]["actor_type"] == "unknown"


def test_service_cleartext_keeps_only_display_and_login() -> None:
    result = _transform(
        {
            "name": "service-account",
            "displayName": "Technical Sync Service",
            "key": "JIRAUSER-SERVICE",
            "emailAddress": "service@example.test",
            "avatarUrls": {"48x48": "https://avatar.example/service"},
            "self": "https://jira.example/user/service-account",
            "active": True,
        }
    )

    assert result["name"] == "service-account"
    assert result["displayName"] == "Technical Sync Service"
    assert result["key"] is None
    assert result["emailAddress"] is None
    assert result["avatarUrls"] is None
    assert result["self"] is None
    assert result["active"] is True
    assert result["identity_class"] == {
        "affiliation": "internal",
        "actor_type": "service",
    }


def test_marks_current_human_without_unmasking() -> None:
    result = _transform(
        {
            "name": "human01",
            "displayName": "Sensitive Person",
            "key": "JIRAUSER1",
        },
        current_identity=CurrentIdentity.from_values("human01"),
    )

    assert result["is_current_user"] is True
    assert result["displayName"] == "You"
    assert result["name"].startswith("pid:v1:")
    assert "Sensitive Person" not in str(result)


def test_anonymize_mode_uses_category_token() -> None:
    result = _transform(
        {
            "name": "customer",
            "displayName": "Customer Person",
            "emailAddress": "customer@example.test",
        },
        adapter=_adapter(PrivacyMode.ANONYMIZE),
    )

    assert result["name"] == "anon:jira:user:external:human"
    assert result["displayName"] == "External human"
    assert result["emailAddress"] is None


def test_transforms_standard_issue_fields_and_direct_author() -> None:
    result = _transform(
        {
            "key": "TEST-1",
            "assignee": {
                "name": "human01",
                "displayName": "Assignee Person",
                "key": "JIRAUSER1",
            },
            "reporter": {
                "name": "customer",
                "displayName": "Reporter Person",
                "key": "JIRAUSER2",
            },
            "creator": "human01",
            "author": "Author Display Name",
        }
    )

    assert result["key"] == "TEST-1"
    assert result["assignee"]["name"].startswith("pid:v1:")
    assert result["reporter"]["name"].startswith("pid:v1:")
    assert result["creator"].startswith("pid:v1:")
    assert result["author"].startswith("pid:v1:")
    assert "Person" not in str(result)
    assert "Author Display Name" not in str(result)


def test_unrelated_jira_objects_are_not_modified() -> None:
    value = {
        "status": {"id": "1", "name": "In Progress", "self": "https://jira/status/1"},
        "project": {"id": "2", "key": "TEST", "name": "Test Project"},
        "assignee": {"display_name": "Unassigned"},
    }

    assert _transform(value) == value


def test_same_login_has_same_alias_across_jira_tools() -> None:
    first = _adapter().transform(
        tool_name="jira_get_issue",
        policy=ToolResponsePolicy(
            service=ToolService.JIRA,
            category=ResponseCategory.MIXED,
        ),
        value={"assignee": {"name": "human01", "displayName": "First"}},
        current_identity=None,
    )
    second = _adapter().transform(
        tool_name="jira_search",
        policy=ToolResponsePolicy(
            service=ToolService.JIRA,
            category=ResponseCategory.MIXED,
        ),
        value={"reporter": {"name": "HUMAN01", "displayName": "Second"}},
        current_identity=None,
    )

    assert first["assignee"]["name"] == second["reporter"]["name"]


def test_default_transformer_registers_jira_adapter() -> None:
    transformer = IdentityResponseTransformer.from_config(
        _config(),
        clock=lambda: _NOW,
    )
    result = transformer.transform(
        tool_name="jira_get_user_profile",
        policy=ToolResponsePolicy(
            service=ToolService.JIRA,
            category=ResponseCategory.STRUCTURED,
        ),
        value={"name": "human01", "displayName": "Sensitive Person"},
        current_identity=None,
    )

    assert result["name"].startswith("pid:v1:")


def test_installation_without_explicit_transformer_protects_jira() -> None:
    server = FastMCP("jira-privacy-default-adapter")
    install_identity_privacy(
        server,
        config=_config(),
    )

    @server.tool(name="jira_get_user_profile")
    async def profile() -> dict[str, str]:
        return {"name": "human01", "displayName": "Sensitive Person"}

    import asyncio

    result = asyncio.run(server.call_tool("jira_get_user_profile", {}))
    assert result.structured_content is not None
    assert result.structured_content["name"].startswith("pid:v1:")
    assert "Sensitive Person" not in str(result.structured_content)
