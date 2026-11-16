"""Tests for nested Jira identity-bearing response structures."""

from datetime import datetime, timezone
from typing import Any

from mcp_atlassian_with_bitbucket_and_privacy.privacy import (
    IdentityPolicy,
    IdentityPrivacyConfig,
    JiraIdentityAdapter,
    PrivacyMode,
    ResponseCategory,
    ToolResponsePolicy,
    ToolService,
)

_NOW = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)


def _adapter() -> JiraIdentityAdapter:
    config = IdentityPrivacyConfig(
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
    return JiraIdentityAdapter(
        config,
        instance="https://jira.example",
        clock=lambda: _NOW,
    )


def _transform(value: Any) -> Any:
    return _adapter().transform(
        tool_name="jira_get_issue",
        policy=ToolResponsePolicy(
            service=ToolService.JIRA,
            category=ResponseCategory.MIXED,
        ),
        value=value,
        current_identity=None,
    )


def _human_user(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "displayName": f"CANARY {name}",
        "key": f"KEY-{name}",
        "emailAddress": f"{name}@example.test",
        "avatarUrls": {"48x48": f"https://avatar.example/{name}"},
    }


def test_nested_comments_worklogs_watchers_attachments_and_lead() -> None:
    result = _transform(
        {
            "comments": [{"author": _human_user("human01")}],
            "worklogs": [{"author": _human_user("human01")}],
            "watchers": [_human_user("human01")],
            "attachments": [{"author": _human_user("human01")}],
            "project": {"lead": _human_user("human01")},
        }
    )

    users = [
        result["comments"][0]["author"],
        result["worklogs"][0]["author"],
        result["watchers"][0],
        result["attachments"][0]["author"],
        result["project"]["lead"],
    ]
    assert all(user["name"].startswith("pid:v1:") for user in users)
    assert all(user["emailAddress"] is None for user in users)
    assert "CANARY" not in str(result)


def test_service_desk_participants_and_on_behalf_user() -> None:
    result = _transform(
        {
            "on_behalf_user": "human01",
            "request_participants": ["human01", "service-account"],
            "requestParticipants": [_human_user("human01")],
        }
    )

    assert result["on_behalf_user"].startswith("pid:v1:")
    assert result["request_participants"][0].startswith("pid:v1:")
    assert result["request_participants"][1] == "service-account"
    assert result["requestParticipants"][0]["name"].startswith("pid:v1:")


def test_development_authors_reviewers_and_approved_by() -> None:
    result = _transform(
        {
            "pullRequests": [
                {
                    "author": "CANARY AUTHOR",
                    "reviewers": ["human01", "service-account"],
                    "approved_by": ["human01"],
                }
            ],
            "commits": [{"author": "CANARY COMMIT AUTHOR"}],
        }
    )

    pull_request = result["pullRequests"][0]
    assert pull_request["author"].startswith("pid:v1:")
    assert pull_request["reviewers"][0].startswith("pid:v1:")
    assert pull_request["reviewers"][1] == "service-account"
    assert pull_request["approved_by"][0].startswith("pid:v1:")
    assert result["commits"][0]["author"].startswith("pid:v1:")
    assert "CANARY" not in str(result)


def test_transitioned_by_metric_is_protected() -> None:
    result = _transform(
        {
            "status_transitions": [
                {
                    "from_status": "Open",
                    "to_status": "Done",
                    "transitioned_by": "CANARY PERSON",
                }
            ]
        }
    )

    assert result["status_transitions"][0]["transitioned_by"].startswith("pid:v1:")
    assert "CANARY PERSON" not in str(result)


def test_assignee_changelog_pairs_share_one_alias() -> None:
    result = _transform(
        {
            "changelogs": [
                {
                    "items": [
                        {
                            "field": "assignee",
                            "from_id": "CANARY-ID-1",
                            "from_string": "CANARY PERSON 1",
                            "to_id": "CANARY-ID-2",
                            "to_string": "CANARY PERSON 2",
                        }
                    ]
                }
            ]
        }
    )

    item = result["changelogs"][0]["items"][0]
    assert item["from_id"] == item["from_string"]
    assert item["to_id"] == item["to_string"]
    assert item["from_id"].startswith("pid:v1:")
    assert item["to_id"].startswith("pid:v1:")
    assert item["from_id"] != item["to_id"]
    assert "CANARY" not in str(item)


def test_raw_camel_case_changelog_is_protected() -> None:
    result = _transform(
        {
            "field": "reporter",
            "from": "CANARY-OLD-ID",
            "fromString": "CANARY OLD",
            "to": "CANARY-NEW-ID",
            "toString": "CANARY NEW",
        }
    )

    assert result["from"] == result["fromString"]
    assert result["to"] == result["toString"]
    assert "CANARY" not in str(result)


def test_non_identity_changelog_remains_unchanged() -> None:
    value = {
        "field": "status",
        "from": "1",
        "fromString": "Open",
        "to": "2",
        "toString": "Done",
    }

    assert _transform(value) == value
