"""Tests for deployment-specific identity policy parsing."""

import pytest

from mcp_atlassian_with_bitbucket_and_privacy.privacy import (
    IdentityPolicy,
    normalize_login,
)


def test_policy_defaults_are_safe() -> None:
    policy = IdentityPolicy()

    assert policy.human_username_max_length is None
    assert policy.expose_service_display_name_and_login is False
    assert policy.internal_logins == frozenset()
    assert policy.external_logins == frozenset()


def test_policy_parses_and_normalizes_values() -> None:
    policy = IdentityPolicy.from_mapping(
        {
            "human_username_max_length": 8,
            "expose_service_display_name_and_login": True,
            "internal_logins": ["  Alpha  "],
            "external_logins": ["BETA"],
            "internal_login_patterns": [r"^employee_[0-9]+$"],
            "external_login_patterns": [r"^customer_[0-9]+$"],
        }
    )

    assert policy.human_username_max_length == 8
    assert policy.expose_service_display_name_and_login is True
    assert policy.internal_logins == frozenset({"alpha"})
    assert policy.external_logins == frozenset({"beta"})
    assert policy.internal_login_patterns[0].fullmatch("EMPLOYEE_1")
    assert policy.external_login_patterns[0].fullmatch("customer_2")


def test_normalize_login_uses_strip_and_casefold() -> None:
    assert normalize_login("  USER-Name  ") == "user-name"


@pytest.mark.parametrize("value", [0, -1, True, "8"])
def test_policy_rejects_invalid_username_length(value: object) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        IdentityPolicy.from_mapping({"human_username_max_length": value})


def test_policy_rejects_non_boolean_cleartext_flag() -> None:
    with pytest.raises(ValueError, match="must be a boolean"):
        IdentityPolicy.from_mapping({"expose_service_display_name_and_login": "true"})


@pytest.mark.parametrize(
    "field,value",
    [
        ("internal_logins", "alpha"),
        ("external_logins", [1]),
        ("internal_login_patterns", "^alpha$"),
        ("external_login_patterns", [""]),
    ],
)
def test_policy_rejects_invalid_collection_values(
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValueError):
        IdentityPolicy.from_mapping({field: value})


def test_policy_rejects_invalid_regex() -> None:
    with pytest.raises(ValueError, match="invalid regex"):
        IdentityPolicy.from_mapping({"internal_login_patterns": ["["]})


def test_policy_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError, match="unknown fields"):
        IdentityPolicy.from_mapping({"unexpected": True})


def test_policy_rejects_conflicting_exact_affiliation() -> None:
    with pytest.raises(ValueError, match="internal and external"):
        IdentityPolicy.from_mapping(
            {
                "internal_logins": ["same"],
                "external_logins": ["SAME"],
            }
        )


def test_jira_text_rules_use_id_priority_and_preserve_order() -> None:
    policy = IdentityPolicy.from_mapping(
        {
            "jira_identity_text_rules": [
                {
                    "field_name_pattern": "^Username",
                    "patterns": [r"name=(?P<identity>[a-z0-9-]+)"],
                },
                {
                    "field_id": "customfield_12345",
                    "patterns": [
                        r"id=(?P<identity>[a-z0-9-]+)",
                        r"owner=(?P<identity>[a-z0-9-]+)",
                    ],
                },
            ]
        }
    )

    id_patterns = policy.jira_text_patterns_for(
        "customfield_12345",
        "Username for ERP",
    )
    name_patterns = policy.jira_text_patterns_for(
        "customfield_99999",
        "Username for ERP",
    )

    assert [pattern.pattern for pattern in id_patterns] == [
        r"id=(?P<identity>[a-z0-9-]+)",
        r"owner=(?P<identity>[a-z0-9-]+)",
    ]
    assert [pattern.pattern for pattern in name_patterns] == [
        r"name=(?P<identity>[a-z0-9-]+)"
    ]


@pytest.mark.parametrize(
    "rule,error",
    [
        (
            {
                "field_id": "customfield_1",
                "field_name_pattern": "name",
                "patterns": [r"(?P<identity>.+)"],
            },
            "exactly one",
        ),
        (
            {
                "field_id": "not-a-custom-field",
                "patterns": [r"(?P<identity>.+)"],
            },
            "customfield_<number>",
        ),
        (
            {
                "field_name_pattern": "[",
                "patterns": [r"(?P<identity>.+)"],
            },
            "field_name_pattern is invalid",
        ),
        (
            {
                "field_id": "customfield_1",
                "patterns": [r"no-named-group"],
            },
            "named 'identity' group",
        ),
        (
            {
                "field_id": "customfield_1",
                "patterns": [],
            },
            "non-empty JSON array",
        ),
    ],
)
def test_jira_text_rules_reject_invalid_config(
    rule: dict[str, object],
    error: str,
) -> None:
    with pytest.raises(ValueError, match=error):
        IdentityPolicy.from_mapping({"jira_identity_text_rules": [rule]})
