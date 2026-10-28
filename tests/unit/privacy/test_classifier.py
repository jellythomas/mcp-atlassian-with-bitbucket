"""Tests for two-axis identity classification."""

from mcp_atlassian_with_bitbucket_and_privacy.privacy import (
    ActorType,
    Affiliation,
    IdentityClass,
    IdentityClassifier,
    IdentityPolicy,
)


def test_secure_default_policy_keeps_both_axes_unknown() -> None:
    classifier = IdentityClassifier(IdentityPolicy())

    assert classifier.classify("example") == IdentityClass()
    assert classifier.classify(None) == IdentityClass()
    assert classifier.classify("   ") == IdentityClass()


def test_username_length_classifies_actor_type_at_boundary() -> None:
    classifier = IdentityClassifier(IdentityPolicy(human_username_max_length=8))

    assert classifier.classify("user0001").actor_type is ActorType.HUMAN
    assert classifier.classify("user00001").actor_type is ActorType.SERVICE


def test_exact_affiliation_rules_use_normalized_login() -> None:
    classifier = IdentityClassifier(
        IdentityPolicy(
            human_username_max_length=8,
            internal_logins=frozenset({"employee"}),
            external_logins=frozenset({"customer"}),
        )
    )

    assert classifier.classify(" EMPLOYEE ").affiliation is Affiliation.INTERNAL
    assert classifier.classify("Customer").affiliation is Affiliation.EXTERNAL
    assert classifier.classify("other").affiliation is Affiliation.UNKNOWN


def test_affiliation_patterns_are_applied_independently() -> None:
    policy = IdentityPolicy.from_mapping(
        {
            "internal_login_patterns": [r"^employee_"],
            "external_login_patterns": [r"^customer_"],
        }
    )
    classifier = IdentityClassifier(policy)

    assert classifier.classify("employee_1").affiliation is Affiliation.INTERNAL
    assert classifier.classify("customer_1").affiliation is Affiliation.EXTERNAL


def test_conflicting_affiliation_rules_result_in_unknown() -> None:
    policy = IdentityPolicy.from_mapping(
        {
            "internal_logins": ["shared"],
            "external_login_patterns": [r"^shared$"],
        }
    )

    assert (
        IdentityClassifier(policy).classify("shared").affiliation is Affiliation.UNKNOWN
    )


def test_service_cleartext_exception_requires_policy_and_service_class() -> None:
    classifier = IdentityClassifier(
        IdentityPolicy(
            human_username_max_length=8,
            expose_service_display_name_and_login=True,
        )
    )

    assert classifier.may_expose_service_display_name_and_login(
        classifier.classify("service01")
    )
    assert not classifier.may_expose_service_display_name_and_login(
        classifier.classify("human001")
    )
    assert not IdentityClassifier(
        IdentityPolicy(human_username_max_length=8)
    ).may_expose_service_display_name_and_login(
        IdentityClass(actor_type=ActorType.SERVICE)
    )
