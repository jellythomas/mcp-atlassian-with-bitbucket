"""Tests for versioned pseudonym master-key rotation."""

import base64
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mcp_atlassian_with_bitbucket_and_privacy.privacy import (
    AliasResolutionError,
    AliasRoundtripRegistry,
    CanonicalIdentity,
    IdentityPolicy,
    IdentityPrivacyConfig,
    JiraIdentityAdapter,
    PrivacyMode,
    Pseudonymizer,
    PseudonymKeyring,
    PseudonymKeyVersion,
    ResponseCategory,
    ToolResponsePolicy,
    ToolService,
    begin_alias_caller_scope,
    begin_alias_roundtrip_registry_scope,
    record_alias_caller,
    reset_alias_caller_scope,
    reset_alias_roundtrip_registry_scope,
    resolve_identity_alias,
)
from mcp_atlassian_with_bitbucket_and_privacy.privacy.config import (
    CORRELATION_DOMAIN_ENV,
    PRIVACY_MODE_ENV,
    PSEUDONYM_KEY_ENV,
    PSEUDONYM_KEYRING_FILE_ENV,
)
from mcp_atlassian_with_bitbucket_and_privacy.privacy.resolver import (
    CanonicalIdentityResolver,
)
from mcp_atlassian_with_bitbucket_and_privacy.privacy.types import (
    CorrelationScope,
    IdentitySource,
)

_NOW = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)


class MutableClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current


def _encoded(byte: bytes) -> str:
    return base64.b64encode(byte * 32).decode("ascii")


def _write_keyring(
    path: Path,
    *,
    active_id: str = "2026-10",
    previous: list[tuple[str, bytes]] | None = None,
) -> None:
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "active": {"id": active_id, "key": _encoded(b"a")},
                "previous": [
                    {"id": key_id, "key": _encoded(byte)}
                    for key_id, byte in (previous or [("2026-09", b"b")])
                ],
            }
        ),
        encoding="utf-8",
    )


def _env(path: Path) -> dict[str, str]:
    return {
        PRIVACY_MODE_ENV: "pseudonymize",
        PSEUDONYM_KEYRING_FILE_ENV: str(path),
        CORRELATION_DOMAIN_ENV: "test-deployment",
    }


def _identity() -> CanonicalIdentity:
    identity = CanonicalIdentityResolver(CorrelationScope.DEPLOYMENT).resolve(
        IdentitySource(
            connector="jira",
            instance="https://jira.example",
            login="target01",
            local_id="target-id",
        )
    )
    assert identity is not None
    return identity


def test_keyring_file_loads_active_and_previous_versions(tmp_path: Path) -> None:
    path = tmp_path / "keyring.json"
    _write_keyring(path)

    config = IdentityPrivacyConfig.from_env(_env(path))

    assert config.pseudonym_key == b"a" * 32
    assert config.pseudonym_keyring_file == path
    assert config.pseudonym_keyring is not None
    assert config.pseudonym_keyring.active.key_id == "2026-10"
    assert [entry.key_id for entry in config.pseudonym_keyring.previous] == ["2026-09"]
    assert "aaaaaaaa" not in repr(config)
    assert "bbbbbbbb" not in repr(config)


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        (
            {
                "version": 2,
                "active": {"id": "active", "key": _encoded(b"a")},
                "previous": [],
            },
            "version",
        ),
        (
            {
                "version": 1,
                "active": {"id": "bad id", "key": _encoded(b"a")},
                "previous": [],
            },
            "id",
        ),
        (
            {
                "version": 1,
                "active": {"id": "same", "key": _encoded(b"a")},
                "previous": [{"id": "same", "key": _encoded(b"b")}],
            },
            "unique",
        ),
        (
            {
                "version": 1,
                "active": {"id": "active", "key": _encoded(b"a")},
                "previous": [
                    {"id": f"old-{index}", "key": _encoded(bytes([65 + index]))}
                    for index in range(5)
                ],
            },
            "too many",
        ),
    ],
)
def test_invalid_keyring_files_fail_startup(
    tmp_path: Path,
    payload: dict[str, object],
    error: str,
) -> None:
    path = tmp_path / "keyring.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=error):
        IdentityPrivacyConfig.from_env(_env(path))


def test_keyring_is_mutually_exclusive_with_direct_key(tmp_path: Path) -> None:
    path = tmp_path / "keyring.json"
    _write_keyring(path)
    env = _env(path)
    env[PSEUDONYM_KEY_ENV] = _encoded(b"x")

    with pytest.raises(ValueError, match="Set only one"):
        IdentityPrivacyConfig.from_env(env)


def test_active_alias_is_versioned_and_previous_candidates_are_available(
    tmp_path: Path,
) -> None:
    path = tmp_path / "keyring.json"
    _write_keyring(path)
    config = IdentityPrivacyConfig.from_env(_env(path))
    clock = MutableClock(_NOW)
    pseudonymizer = Pseudonymizer.from_config(config, clock=clock)

    aliases = pseudonymizer.pseudonymize_candidates(_identity())

    assert aliases[0].startswith("pid:v2:2026-10:")
    assert aliases[1].startswith("pid:v2:2026-09:")
    assert aliases[0] != aliases[1]
    clock.current += timedelta(days=1)
    assert pseudonymizer.pseudonymize(_identity()).startswith("pid:v2:2026-10:")
    assert pseudonymizer.pseudonymize(_identity()) != aliases[0]


def _keyring_config(
    *,
    previous: tuple[PseudonymKeyVersion, ...],
) -> IdentityPrivacyConfig:
    active = PseudonymKeyVersion("active", b"a" * 32)
    return IdentityPrivacyConfig(
        mode=PrivacyMode.PSEUDONYMIZE,
        policy=IdentityPolicy(human_username_max_length=8),
        pseudonym_key=active.key,
        pseudonym_keyring=PseudonymKeyring(active=active, previous=previous),
        correlation_domain="test-deployment",
        alias_roundtrip_enabled=True,
    )


def test_previous_alias_resolves_until_key_is_retired() -> None:
    previous = PseudonymKeyVersion("previous", b"b" * 32)
    config = _keyring_config(previous=(previous,))
    registry = AliasRoundtripRegistry(config)
    adapter = JiraIdentityAdapter(
        config,
        instance="https://jira.example",
        clock=lambda: _NOW,
        alias_roundtrip_registry=registry,
    )
    caller_scope = begin_alias_caller_scope()
    registry_scope = begin_alias_roundtrip_registry_scope(registry)
    try:
        record_alias_caller(
            ToolService.JIRA,
            "https://jira.example",
            "caller-token",
        )
        adapter.transform(
            tool_name="jira_get_user_profile",
            policy=ToolResponsePolicy(
                service=ToolService.JIRA,
                category=ResponseCategory.STRUCTURED,
            ),
            value={"name": "target01", "displayName": "Target User"},
            current_identity=None,
        )
        old_alias = Pseudonymizer(
            master_key=previous.key,
            key_id=previous.key_id,
            correlation_domain="test-deployment",
            rotation_hours=24,
            clock=lambda: _NOW,
        ).pseudonymize(_identity())
        assert (
            resolve_identity_alias(
                old_alias,
                service=ToolService.JIRA,
                instance="https://jira.example",
                prefer_local_id=False,
            )
            == "target01"
        )
    finally:
        reset_alias_roundtrip_registry_scope(registry_scope)
        reset_alias_caller_scope(caller_scope)

    retired_config = _keyring_config(previous=())
    retired_registry = AliasRoundtripRegistry(retired_config)
    retired_adapter = JiraIdentityAdapter(
        retired_config,
        instance="https://jira.example",
        clock=lambda: _NOW,
        alias_roundtrip_registry=retired_registry,
    )
    caller_scope = begin_alias_caller_scope()
    registry_scope = begin_alias_roundtrip_registry_scope(retired_registry)
    try:
        record_alias_caller(
            ToolService.JIRA,
            "https://jira.example",
            "caller-token",
        )
        retired_adapter.transform(
            tool_name="jira_get_user_profile",
            policy=ToolResponsePolicy(
                service=ToolService.JIRA,
                category=ResponseCategory.STRUCTURED,
            ),
            value={"name": "target01", "displayName": "Target User"},
            current_identity=None,
        )
        with pytest.raises(AliasResolutionError, match="unknown"):
            resolve_identity_alias(
                old_alias,
                service=ToolService.JIRA,
                instance="https://jira.example",
                prefer_local_id=False,
            )
    finally:
        reset_alias_roundtrip_registry_scope(registry_scope)
        reset_alias_caller_scope(caller_scope)
