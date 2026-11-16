"""Tests for identity privacy configuration."""

import base64
import json
from pathlib import Path

import pytest

from mcp_atlassian_with_bitbucket_and_privacy.privacy import (
    CorrelationScope,
    IdentityPrivacyConfig,
    PrivacyMode,
    UnstructuredContentPolicy,
)
from mcp_atlassian_with_bitbucket_and_privacy.privacy.config import (
    ALIAS_ROUNDTRIP_ENV,
    CORRELATION_DOMAIN_ENV,
    CORRELATION_SCOPE_ENV,
    POLICY_FILE_ENV,
    PRIVACY_MODE_ENV,
    PSEUDONYM_KEY_ENV,
    PSEUDONYM_KEY_FILE_ENV,
    ROTATION_HOURS_ENV,
    SELF_IDENTIFICATION_ENV,
    UNSTRUCTURED_CONTENT_POLICY_ENV,
)


def _encoded_key(byte: bytes = b"k") -> str:
    return base64.b64encode(byte * 32).decode("ascii")


def _pseudonym_env() -> dict[str, str]:
    return {
        PRIVACY_MODE_ENV: "pseudonymize",
        PSEUDONYM_KEY_ENV: _encoded_key(),
        CORRELATION_DOMAIN_ENV: "test-deployment",
    }


def test_default_configuration_is_disabled_and_safe() -> None:
    config = IdentityPrivacyConfig.from_env({})

    assert config.mode is PrivacyMode.OFF
    assert config.enabled is False
    assert config.policy.human_username_max_length is None
    assert config.policy.expose_service_display_name_and_login is False
    assert config.pseudonym_key is None
    assert config.self_identification_enabled is True
    assert config.alias_roundtrip_enabled is False
    assert config.unstructured_content_policy is UnstructuredContentPolicy.ALLOW


def test_disabled_mode_ignores_dependent_invalid_settings() -> None:
    config = IdentityPrivacyConfig.from_env(
        {
            PRIVACY_MODE_ENV: "off",
            ROTATION_HOURS_ENV: "invalid",
            SELF_IDENTIFICATION_ENV: "invalid",
            POLICY_FILE_ENV: "missing.json",
        }
    )

    assert config == IdentityPrivacyConfig()


def test_invalid_mode_always_fails() -> None:
    with pytest.raises(ValueError, match=PRIVACY_MODE_ENV):
        IdentityPrivacyConfig.from_env({PRIVACY_MODE_ENV: "enabled"})


def test_anonymize_mode_needs_no_key_or_domain() -> None:
    config = IdentityPrivacyConfig.from_env(
        {
            PRIVACY_MODE_ENV: "anonymize",
            SELF_IDENTIFICATION_ENV: "false",
            UNSTRUCTURED_CONTENT_POLICY_ENV: "deny",
        }
    )

    assert config.enabled is True
    assert config.mode is PrivacyMode.ANONYMIZE
    assert config.pseudonym_key is None
    assert config.self_identification_enabled is False
    assert config.unstructured_content_policy is UnstructuredContentPolicy.DENY


def test_pseudonymize_mode_loads_direct_key() -> None:
    config = IdentityPrivacyConfig.from_env(_pseudonym_env())

    assert config.mode is PrivacyMode.PSEUDONYMIZE
    assert config.pseudonym_key == b"k" * 32
    assert config.correlation_scope is CorrelationScope.DEPLOYMENT
    assert config.correlation_domain == "test-deployment"
    assert config.rotation_hours == 24
    assert "kkkk" not in repr(config)


def test_pseudonymize_mode_loads_key_file(tmp_path: Path) -> None:
    key_file = tmp_path / "privacy.key"
    key_file.write_text(_encoded_key(b"x"), encoding="ascii")
    config = IdentityPrivacyConfig.from_env(
        {
            PRIVACY_MODE_ENV: "pseudonymize",
            PSEUDONYM_KEY_FILE_ENV: str(key_file),
            CORRELATION_SCOPE_ENV: "connector",
        }
    )

    assert config.pseudonym_key == b"x" * 32
    assert config.correlation_scope is CorrelationScope.CONNECTOR
    assert config.correlation_domain is None


def test_pseudonymize_mode_requires_key() -> None:
    with pytest.raises(ValueError, match="requires exactly one"):
        IdentityPrivacyConfig.from_env(
            {
                PRIVACY_MODE_ENV: "pseudonymize",
                CORRELATION_DOMAIN_ENV: "test-deployment",
            }
        )


def test_pseudonymize_mode_rejects_two_key_sources(tmp_path: Path) -> None:
    key_file = tmp_path / "privacy.key"
    key_file.write_text(_encoded_key(), encoding="ascii")
    env = _pseudonym_env()
    env[PSEUDONYM_KEY_FILE_ENV] = str(key_file)

    with pytest.raises(ValueError, match="Set only one"):
        IdentityPrivacyConfig.from_env(env)


@pytest.mark.parametrize("encoded", ["not-base64", _encoded_key()[:-8]])
def test_pseudonymize_mode_rejects_invalid_key(encoded: str) -> None:
    env = _pseudonym_env()
    env[PSEUDONYM_KEY_ENV] = encoded

    with pytest.raises(ValueError, match="base64|at least"):
        IdentityPrivacyConfig.from_env(env)


def test_deployment_scope_requires_domain() -> None:
    env = _pseudonym_env()
    del env[CORRELATION_DOMAIN_ENV]

    with pytest.raises(ValueError, match=CORRELATION_DOMAIN_ENV):
        IdentityPrivacyConfig.from_env(env)


@pytest.mark.parametrize("value", ["0", "-1", "8761", "invalid"])
def test_rotation_hours_are_strictly_validated(value: str) -> None:
    env = _pseudonym_env()
    env[ROTATION_HOURS_ENV] = value

    with pytest.raises(ValueError, match=ROTATION_HOURS_ENV):
        IdentityPrivacyConfig.from_env(env)


def test_active_mode_rejects_invalid_boolean() -> None:
    with pytest.raises(ValueError, match=SELF_IDENTIFICATION_ENV):
        IdentityPrivacyConfig.from_env(
            {
                PRIVACY_MODE_ENV: "anonymize",
                SELF_IDENTIFICATION_ENV: "sometimes",
            }
        )


def test_active_mode_rejects_invalid_enum() -> None:
    with pytest.raises(ValueError, match=UNSTRUCTURED_CONTENT_POLICY_ENV):
        IdentityPrivacyConfig.from_env(
            {
                PRIVACY_MODE_ENV: "anonymize",
                UNSTRUCTURED_CONTENT_POLICY_ENV: "scan",
            }
        )


def test_alias_roundtrip_can_be_enabled_only_for_pseudonymize_mode() -> None:
    env = _pseudonym_env()
    env[ALIAS_ROUNDTRIP_ENV] = "true"

    config = IdentityPrivacyConfig.from_env(env)

    assert config.alias_roundtrip_enabled is True

    with pytest.raises(ValueError, match="pseudonymize"):
        IdentityPrivacyConfig.from_env(
            {
                PRIVACY_MODE_ENV: "anonymize",
                ALIAS_ROUNDTRIP_ENV: "true",
            }
        )


def test_policy_file_is_loaded(tmp_path: Path) -> None:
    policy_file = tmp_path / "identity-policy.json"
    policy_file.write_text(
        json.dumps(
            {
                "human_username_max_length": 8,
                "expose_service_display_name_and_login": True,
                "internal_logins": ["internal"],
                "external_login_patterns": [r"^external_"],
            }
        ),
        encoding="utf-8",
    )
    config = IdentityPrivacyConfig.from_env(
        {
            PRIVACY_MODE_ENV: "anonymize",
            POLICY_FILE_ENV: str(policy_file),
        }
    )

    assert config.policy_file == policy_file
    assert config.policy.human_username_max_length == 8
    assert config.policy.expose_service_display_name_and_login is True
    assert config.policy.internal_logins == frozenset({"internal"})
    assert config.policy.external_login_patterns[0].match("EXTERNAL_USER")
    assert "internal" not in repr(config)
    assert "external_" not in repr(config)


@pytest.mark.parametrize(
    "content,error",
    [
        ("not-json", "not valid JSON"),
        ("[]", "JSON object"),
        ('{"unexpected": true}', "unknown fields"),
    ],
)
def test_invalid_policy_file_fails(
    tmp_path: Path,
    content: str,
    error: str,
) -> None:
    policy_file = tmp_path / "identity-policy.json"
    policy_file.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match=error):
        IdentityPrivacyConfig.from_env(
            {
                PRIVACY_MODE_ENV: "anonymize",
                POLICY_FILE_ENV: str(policy_file),
            }
        )


def test_missing_policy_file_fails(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unable to read"):
        IdentityPrivacyConfig.from_env(
            {
                PRIVACY_MODE_ENV: "anonymize",
                POLICY_FILE_ENV: str(tmp_path / "missing.json"),
            }
        )


def test_missing_pseudonym_key_file_fails(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unable to read pseudonym key file"):
        IdentityPrivacyConfig.from_env(
            {
                PRIVACY_MODE_ENV: "pseudonymize",
                PSEUDONYM_KEY_FILE_ENV: str(tmp_path / "missing.key"),
                CORRELATION_SCOPE_ENV: "connector",
            }
        )
