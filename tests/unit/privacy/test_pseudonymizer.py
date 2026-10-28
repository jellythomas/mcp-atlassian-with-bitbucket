"""Tests for stateless time-bounded identity pseudonyms."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from mcp_atlassian_with_bitbucket_and_privacy.privacy import (
    CanonicalIdentity,
    CanonicalIdentityResolver,
    CorrelationScope,
    IdentityPrivacyConfig,
    IdentitySource,
    PrivacyMode,
    Pseudonymizer,
)


class MutableClock:
    """Simple injected clock for rotation-boundary tests."""

    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current


def _config(
    *,
    key: bytes = b"k" * 32,
    domain: str = "test-deployment",
    rotation_hours: int = 24,
) -> IdentityPrivacyConfig:
    return IdentityPrivacyConfig(
        mode=PrivacyMode.PSEUDONYMIZE,
        pseudonym_key=key,
        correlation_domain=domain,
        rotation_hours=rotation_hours,
    )


def _resolved(
    connector: str,
    *,
    login: str | None = "shared-login",
    local_id: str | None = "local-id",
) -> CanonicalIdentity:
    identity = CanonicalIdentityResolver(CorrelationScope.DEPLOYMENT).resolve(
        IdentitySource(
            connector=connector,
            instance=f"https://{connector}.example",
            login=login,
            local_id=local_id,
        )
    )
    assert identity is not None
    return identity


def test_same_login_is_stable_across_connectors_and_tools() -> None:
    clock = MutableClock(datetime(2026, 10, 5, 12, tzinfo=timezone.utc))
    pseudonymizer = Pseudonymizer.from_config(_config(), clock=clock)

    aliases = {
        pseudonymizer.pseudonymize(_resolved("jira")),
        pseudonymizer.pseudonymize(_resolved("bitbucket")),
        pseudonymizer.pseudonymize(_resolved("confluence")),
    }

    assert len(aliases) == 1
    alias = aliases.pop()
    assert alias.startswith("pid:v1:")
    assert "shared-login" not in alias


def test_alias_rotates_exactly_at_utc_midnight_without_grace() -> None:
    boundary = datetime(2026, 10, 6, 0, 0, 0, tzinfo=timezone.utc)
    clock = MutableClock(boundary - timedelta(microseconds=1))
    pseudonymizer = Pseudonymizer.from_config(_config(), clock=clock)
    identity = _resolved("jira")

    before = pseudonymizer.pseudonymize(identity)
    clock.current = boundary
    on_boundary = pseudonymizer.pseudonymize(identity)
    clock.current = boundary + timedelta(microseconds=1)
    after = pseudonymizer.pseudonymize(identity)

    assert before != on_boundary
    assert on_boundary == after


def test_alias_is_stable_within_epoch() -> None:
    clock = MutableClock(datetime(2026, 10, 5, 0, 0, tzinfo=timezone.utc))
    pseudonymizer = Pseudonymizer.from_config(_config(), clock=clock)
    identity = _resolved("jira")

    first = pseudonymizer.pseudonymize(identity)
    clock.current += timedelta(hours=23, minutes=59)

    assert pseudonymizer.pseudonymize(identity) == first


def test_configurable_rotation_period_uses_unix_aligned_epochs() -> None:
    clock = MutableClock(datetime(2026, 10, 5, 11, 59, tzinfo=timezone.utc))
    pseudonymizer = Pseudonymizer.from_config(
        _config(rotation_hours=12),
        clock=clock,
    )
    identity = _resolved("jira")

    before = pseudonymizer.pseudonymize(identity)
    clock.current = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)

    assert pseudonymizer.pseudonymize(identity) != before


def test_instance_local_fallbacks_do_not_correlate_across_connectors() -> None:
    clock = MutableClock(datetime(2026, 10, 5, 12, tzinfo=timezone.utc))
    pseudonymizer = Pseudonymizer.from_config(_config(), clock=clock)

    jira = _resolved("jira", login=None, local_id="same-local-id")
    confluence = _resolved(
        "confluence",
        login=None,
        local_id="same-local-id",
    )

    assert pseudonymizer.pseudonymize(jira) != pseudonymizer.pseudonymize(confluence)


def test_different_domain_or_master_key_changes_alias() -> None:
    at = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)
    identity = _resolved("jira")

    first = Pseudonymizer.from_config(
        _config(),
        clock=lambda: at,
    ).pseudonymize(identity)
    different_domain = Pseudonymizer.from_config(
        _config(domain="other-deployment"),
        clock=lambda: at,
    ).pseudonymize(identity)
    different_key = Pseudonymizer.from_config(
        _config(key=b"x" * 32),
        clock=lambda: at,
    ).pseudonymize(identity)

    assert len({first, different_domain, different_key}) == 3


def test_independent_replicas_produce_same_alias() -> None:
    at = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)
    first = Pseudonymizer.from_config(_config(), clock=lambda: at)
    second = Pseudonymizer.from_config(_config(), clock=lambda: at)
    identity = _resolved("jira")

    assert first.pseudonymize(identity) == second.pseudonymize(identity)


def test_parallel_replicas_produce_same_alias() -> None:
    at = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)
    identity = _resolved("jira")

    def pseudonymize(_: int) -> str:
        replica = Pseudonymizer.from_config(_config(), clock=lambda: at)
        return replica.pseudonymize(identity)

    with ThreadPoolExecutor(max_workers=8) as executor:
        aliases = set(executor.map(pseudonymize, range(32)))

    assert len(aliases) == 1


@pytest.mark.parametrize(
    "config",
    [
        IdentityPrivacyConfig(),
        IdentityPrivacyConfig(mode=PrivacyMode.ANONYMIZE),
        IdentityPrivacyConfig(mode=PrivacyMode.PSEUDONYMIZE),
    ],
)
def test_from_config_rejects_non_pseudonym_configuration(
    config: IdentityPrivacyConfig,
) -> None:
    with pytest.raises(ValueError):
        Pseudonymizer.from_config(config)


def test_rejects_short_direct_master_key() -> None:
    with pytest.raises(ValueError, match="at least"):
        Pseudonymizer(
            master_key=b"short",
            correlation_domain="test",
            rotation_hours=24,
        )


def test_rejects_naive_clock() -> None:
    naive_time = datetime(
        2026,
        10,
        5,
        12,
        tzinfo=timezone.utc,
    ).replace(tzinfo=None)
    pseudonymizer = Pseudonymizer.from_config(
        _config(),
        clock=lambda: naive_time,
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        pseudonymizer.pseudonymize(_resolved("jira"))


def test_sensitive_master_key_is_not_in_repr() -> None:
    pseudonymizer = Pseudonymizer(
        master_key=b"sensitive-master-key-material-123",
        correlation_domain="test",
        rotation_hours=24,
    )

    assert "sensitive-master-key" not in repr(pseudonymizer)
