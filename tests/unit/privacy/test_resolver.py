"""Tests for canonical identity resolution."""

import pytest

from mcp_atlassian_with_bitbucket_and_privacy.privacy import (
    CanonicalIdentity,
    CanonicalIdentityResolver,
    CorrelationScope,
    IdentitySource,
)


def _source(
    connector: str,
    *,
    login: str | None = "shared",
    instance: str = "https://atlassian.example",
    local_id: str | None = "local-1",
) -> IdentitySource:
    return IdentitySource(
        connector=connector,
        instance=instance,
        login=login,
        local_id=local_id,
    )


def test_deployment_scope_correlates_exact_normalized_login() -> None:
    resolver = CanonicalIdentityResolver(CorrelationScope.DEPLOYMENT)

    jira = resolver.resolve(_source("jira", login=" Shared "))
    bitbucket = resolver.resolve(_source("bitbucket", login="SHARED"))
    confluence = resolver.resolve(_source("confluence", login="shared"))

    assert jira == bitbucket == confluence
    assert jira is not None
    assert jira.scope is CorrelationScope.DEPLOYMENT


def test_connector_scope_separates_connectors() -> None:
    resolver = CanonicalIdentityResolver(CorrelationScope.CONNECTOR)

    jira = resolver.resolve(_source("jira"))
    another_jira = resolver.resolve(_source("JIRA", instance="https://other.example/"))
    confluence = resolver.resolve(_source("confluence"))

    assert jira == another_jira
    assert jira != confluence
    assert jira is not None
    assert jira.connector == "jira"
    assert jira.instance is None


def test_instance_scope_separates_instances() -> None:
    resolver = CanonicalIdentityResolver(CorrelationScope.INSTANCE)

    first = resolver.resolve(_source("jira", instance="https://one.example/"))
    same = resolver.resolve(_source("JIRA", instance="HTTPS://ONE.EXAMPLE"))
    second = resolver.resolve(_source("jira", instance="https://two.example"))

    assert first == same
    assert first != second


def test_missing_login_uses_instance_local_id() -> None:
    resolver = CanonicalIdentityResolver(CorrelationScope.DEPLOYMENT)

    jira = resolver.resolve(_source("jira", login=None, local_id="opaque"))
    confluence = resolver.resolve(_source("confluence", login=" ", local_id="opaque"))

    assert jira is not None
    assert jira.scope is CorrelationScope.INSTANCE
    assert jira.connector == "jira"
    assert jira.subject_id == "opaque"
    assert jira != confluence


def test_missing_login_and_local_id_returns_none() -> None:
    resolver = CanonicalIdentityResolver(CorrelationScope.DEPLOYMENT)

    assert resolver.resolve(_source("jira", login=None, local_id=None)) is None


@pytest.mark.parametrize(
    "source,error",
    [
        (
            IdentitySource(
                connector="",
                instance="https://example",
                login=None,
                local_id="opaque",
            ),
            "connector",
        ),
        (
            IdentitySource(
                connector="jira",
                instance="",
                login=None,
                local_id="opaque",
            ),
            "instance",
        ),
    ],
)
def test_local_fallback_requires_context(
    source: IdentitySource,
    error: str,
) -> None:
    with pytest.raises(ValueError, match=error):
        CanonicalIdentityResolver(CorrelationScope.DEPLOYMENT).resolve(source)


def test_sensitive_identity_values_are_hidden_from_repr() -> None:
    source = _source("jira", login="private-login", local_id="private-id")
    resolved = CanonicalIdentityResolver(CorrelationScope.DEPLOYMENT).resolve(source)

    assert "private-login" not in repr(source)
    assert "private-id" not in repr(source)
    assert resolved is not None
    assert "private-login" not in repr(resolved)


def test_canonical_identity_validates_scope_context() -> None:
    with pytest.raises(ValueError, match="requires connector"):
        CanonicalIdentity(
            scope=CorrelationScope.CONNECTOR,
            entity_kind="user",
            subject_id="opaque",
        )
    with pytest.raises(ValueError, match="requires instance"):
        CanonicalIdentity(
            scope=CorrelationScope.INSTANCE,
            entity_kind="user",
            subject_id="opaque",
            connector="jira",
        )
