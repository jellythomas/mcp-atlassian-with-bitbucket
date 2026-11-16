"""Tests for identity privacy domain types."""

from mcp_atlassian_with_bitbucket_and_privacy.privacy import (
    ActorType,
    Affiliation,
    CorrelationScope,
    IdentityClass,
    PrivacyMode,
    UnstructuredContentPolicy,
)


def test_enum_wire_values() -> None:
    assert [mode.value for mode in PrivacyMode] == [
        "off",
        "anonymize",
        "pseudonymize",
    ]
    assert Affiliation.UNKNOWN.value == "unknown"
    assert ActorType.SERVICE.value == "service"
    assert CorrelationScope.DEPLOYMENT.value == "deployment"
    assert UnstructuredContentPolicy.ALLOW.value == "allow"


def test_identity_class_defaults_to_unknown() -> None:
    identity_class = IdentityClass()

    assert identity_class.affiliation is Affiliation.UNKNOWN
    assert identity_class.actor_type is ActorType.UNKNOWN
    assert identity_class.to_dict() == {
        "affiliation": "unknown",
        "actor_type": "unknown",
    }


def test_identity_class_serializes_selected_values() -> None:
    identity_class = IdentityClass(
        affiliation=Affiliation.EXTERNAL,
        actor_type=ActorType.HUMAN,
    )

    assert identity_class.to_dict() == {
        "affiliation": "external",
        "actor_type": "human",
    }
