"""Tests for schema-aware Jira custom identity fields."""

from datetime import datetime, timezone
from typing import Any

import pytest

from mcp_atlassian_with_bitbucket_and_privacy.models.jira.issue import JiraIssue
from mcp_atlassian_with_bitbucket_and_privacy.models.jira.search import JiraSearchResult
from mcp_atlassian_with_bitbucket_and_privacy.privacy import (
    IdentityPolicy,
    IdentityPrivacyConfig,
    JiraIdentityAdapter,
    PrivacyMode,
    PrivacyTransformationError,
    ResponseCategory,
    ToolResponsePolicy,
    ToolService,
    begin_identity_privacy_runtime,
    reset_identity_privacy_runtime,
)

_NOW = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)


def _policy(
    text_rules: list[dict[str, object]] | None = None,
) -> IdentityPolicy:
    return IdentityPolicy.from_mapping(
        {
            "human_username_max_length": 8,
            "expose_service_display_name_and_login": True,
            "internal_logins": ["human01", "service-account"],
            "jira_identity_text_rules": text_rules or [],
        }
    )


def _adapter(
    text_rules: list[dict[str, object]] | None = None,
) -> JiraIdentityAdapter:
    config = IdentityPrivacyConfig(
        mode=PrivacyMode.PSEUDONYMIZE,
        policy=_policy(text_rules),
        pseudonym_key=b"k" * 32,
        correlation_domain="test-deployment",
    )
    return JiraIdentityAdapter(
        config,
        instance="https://jira.example",
        clock=lambda: _NOW,
    )


def _transform(
    value: Any,
    *,
    text_rules: list[dict[str, object]] | None = None,
) -> Any:
    return _adapter(text_rules).transform(
        tool_name="jira_get_issue",
        policy=ToolResponsePolicy(
            service=ToolService.JIRA,
            category=ResponseCategory.MIXED,
        ),
        value=value,
        current_identity=None,
    )


def _raw_issue() -> dict[str, Any]:
    return {
        "id": "1",
        "key": "TEST-1",
        "fields": {
            "summary": "Custom identities",
            "customfield_10001": {
                "name": "human01",
                "displayName": "CANARY HUMAN",
                "key": "JIRAUSER1",
                "emailAddress": "human@example.test",
                "self": "https://jira.example/user/human01",
            },
            "customfield_10002": [
                {
                    "name": "human01",
                    "displayName": "CANARY HUMAN",
                    "key": "JIRAUSER1",
                    "self": "https://jira.example/user/human01",
                },
                "service-account",
            ],
            "customfield_10003": "owner=human01 and sync=service-account",
            "customfield_10004": "ordinary free text human01",
        },
        "names": {
            "customfield_10001": "Reviewer",
            "customfield_10002": "Approvers",
            "customfield_10003": "Username for ERP",
            "customfield_10004": "Notes",
        },
        "schema": {
            "customfield_10001": {
                "type": "user",
                "custom": "userpicker",
            },
            "customfield_10002": {
                "type": "array",
                "items": "user",
                "custom": "multiuserpicker",
            },
            "customfield_10003": {"type": "string"},
            "customfield_10004": {"type": "string"},
        },
    }


def _privacy_output(
    issue: JiraIssue,
    *,
    display_names: bool = False,
) -> dict[str, Any]:
    token = begin_identity_privacy_runtime()
    try:
        if display_names:
            return issue.to_display_name_dict()
        return issue.to_simplified_dict()
    finally:
        reset_identity_privacy_runtime(token)


def test_off_mode_custom_field_output_remains_unchanged() -> None:
    issue = JiraIssue.from_api_response(
        _raw_issue(),
        requested_fields="*all",
    )

    output = issue.to_simplified_dict()

    assert output["customfield_10001"] == {
        "value": "human01",
        "name": "Reviewer",
    }
    assert "_identity_schema" not in str(output)


def test_privacy_runtime_preserves_schema_and_raw_user_values() -> None:
    issue = JiraIssue.from_api_response(
        _raw_issue(),
        requested_fields="*all",
    )

    output = _privacy_output(issue)

    assert output["customfield_10001"]["_identity_schema"] == "user"
    assert output["customfield_10001"]["value"]["name"] == "human01"
    assert output["customfield_10002"]["_identity_schema"] == "array:user"
    assert output["customfield_10002"]["value"][1] == "service-account"


def test_adapter_protects_user_and_multi_user_custom_fields() -> None:
    issue = JiraIssue.from_api_response(
        _raw_issue(),
        requested_fields="*all",
    )

    result = _transform(_privacy_output(issue))

    reviewer = result["customfield_10001"]
    approvers = result["customfield_10002"]
    assert "_identity_schema" not in reviewer
    assert reviewer["value"]["name"].startswith("pid:v1:")
    assert reviewer["value"]["emailAddress"] is None
    assert approvers["value"][0]["name"].startswith("pid:v1:")
    assert approvers["value"][1] == "service-account"
    assert "CANARY" not in str(result)


def test_display_name_output_retains_field_id_for_adapter() -> None:
    issue = JiraIssue.from_api_response(
        _raw_issue(),
        requested_fields="*all",
    )

    result = _transform(_privacy_output(issue, display_names=True))

    assert result["Reviewer"]["field_id"] == "customfield_10001"
    assert result["Reviewer"]["value"]["name"].startswith("pid:v1:")
    assert "_identity_schema" not in result["Reviewer"]


def test_id_rule_has_priority_and_replaces_only_identity_group() -> None:
    rules = [
        {
            "field_name_pattern": "^Username for ERP$",
            "patterns": [r"owner=(?P<identity>[a-z0-9-]+)"],
        },
        {
            "field_id": "customfield_10003",
            "patterns": [r"sync=(?P<identity>[a-z0-9-]+)"],
        },
    ]
    issue = JiraIssue.from_api_response(
        _raw_issue(),
        requested_fields="*all",
    )

    result = _transform(_privacy_output(issue), text_rules=rules)
    text = result["customfield_10003"]["value"]

    assert text.startswith("owner=human01 and sync=")
    assert text.endswith("service-account")


def test_all_matching_name_rules_are_applied_in_order() -> None:
    rules = [
        {
            "field_name_pattern": "^Username",
            "patterns": [r"owner=(?P<identity>[a-z0-9-]+)"],
        },
        {
            "field_name_pattern": "ERP$",
            "patterns": [r"sync=(?P<identity>[a-z0-9-]+)"],
        },
    ]
    issue = JiraIssue.from_api_response(
        _raw_issue(),
        requested_fields="*all",
    )

    text = _transform(
        _privacy_output(issue),
        text_rules=rules,
    )["customfield_10003"]["value"]

    assert "human01" not in text
    assert "service-account" in text
    assert text.startswith("owner=pid:v1:")


def test_nonconfigured_text_field_remains_unchanged() -> None:
    issue = JiraIssue.from_api_response(
        _raw_issue(),
        requested_fields="*all",
    )

    result = _transform(
        _privacy_output(issue),
        text_rules=[
            {
                "field_id": "customfield_10003",
                "patterns": [r"owner=(?P<identity>[a-z0-9-]+)"],
            }
        ],
    )

    assert result["customfield_10004"]["value"] == "ordinary free text human01"


def test_overlapping_identity_matches_fail_closed() -> None:
    issue = JiraIssue.from_api_response(
        _raw_issue(),
        requested_fields="*all",
    )
    rules = [
        {
            "field_id": "customfield_10003",
            "patterns": [
                r"owner=(?P<identity>human01)",
                r"(?P<identity>human01 and sync)",
            ],
        }
    ]

    with pytest.raises(PrivacyTransformationError, match="overlapping"):
        _transform(_privacy_output(issue), text_rules=rules)


def test_search_result_propagates_top_level_schema() -> None:
    raw_issue = _raw_issue()
    raw_issue.pop("names")
    raw_issue.pop("schema")
    result = JiraSearchResult.from_api_response(
        {
            "issues": [raw_issue],
            "names": _raw_issue()["names"],
            "schema": _raw_issue()["schema"],
        },
        requested_fields="*all",
    )

    output = _privacy_output(result.issues[0])

    assert output["customfield_10001"]["_identity_schema"] == "user"
