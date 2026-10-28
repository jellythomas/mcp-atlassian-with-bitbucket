"""Jira component leads and real assignees are login scalars and must be protected."""

from datetime import datetime, timezone

from mcp_atlassian_with_bitbucket_and_privacy.privacy import (
    IdentityPolicy,
    IdentityPrivacyConfig,
    JiraIdentityAdapter,
    PrivacyMode,
    ResponseCategory,
    ToolResponsePolicy,
    ToolService,
)

_NOW = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)


def _adapter() -> JiraIdentityAdapter:
    config = IdentityPrivacyConfig(
        mode=PrivacyMode.PSEUDONYMIZE,
        policy=IdentityPolicy.from_mapping(
            {"human_username_max_length": 8, "internal_logins": ["human01"]}
        ),
        pseudonym_key=b"k" * 32,
        correlation_domain="test-deployment",
    )
    return JiraIdentityAdapter(
        config,
        clock=lambda: _NOW,
    )


def test_component_lead_and_real_assignee_logins_are_pseudonymized() -> None:
    result = _adapter().transform(
        tool_name="jira_get_project_components",
        policy=ToolResponsePolicy(
            service=ToolService.JIRA,
            category=ResponseCategory.STRUCTURED,
        ),
        value={
            "name": "Andere",
            "leadUserName": "human01",
            "realAssignee": "human01",
        },
        current_identity=None,
    )

    assert result["leadUserName"].startswith("pid:v1:")
    assert result["realAssignee"].startswith("pid:v1:")
    assert "human01" not in str(result)
    assert result["name"] == "Andere"
