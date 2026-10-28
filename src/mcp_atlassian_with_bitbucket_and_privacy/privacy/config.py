"""Environment-driven configuration for structured identity privacy."""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TypeVar

from .keyring import PseudonymKeyring, PseudonymKeyVersion
from .policy import IdentityPolicy
from .types import CorrelationScope, PrivacyMode, UnstructuredContentPolicy

PRIVACY_MODE_ENV = "MCP_ATLASSIAN_IDENTITY_PRIVACY_MODE"
POLICY_FILE_ENV = "MCP_ATLASSIAN_IDENTITY_POLICY_FILE"
PSEUDONYM_KEY_ENV = "MCP_ATLASSIAN_PSEUDONYM_KEY"
PSEUDONYM_KEY_FILE_ENV = "MCP_ATLASSIAN_PSEUDONYM_KEY_FILE"
PSEUDONYM_KEYRING_FILE_ENV = "MCP_ATLASSIAN_PSEUDONYM_KEYRING_FILE"
CORRELATION_SCOPE_ENV = "MCP_ATLASSIAN_PSEUDONYM_CORRELATION_SCOPE"
CORRELATION_DOMAIN_ENV = "MCP_ATLASSIAN_PSEUDONYM_CORRELATION_DOMAIN"
ROTATION_HOURS_ENV = "MCP_ATLASSIAN_PSEUDONYM_ROTATION_HOURS"
SELF_IDENTIFICATION_ENV = "MCP_ATLASSIAN_IDENTITY_SELF_IDENTIFICATION_ENABLED"
UNSTRUCTURED_CONTENT_POLICY_ENV = "MCP_ATLASSIAN_UNSTRUCTURED_CONTENT_POLICY"
ALIAS_ROUNDTRIP_ENV = "MCP_ATLASSIAN_IDENTITY_ALIAS_ROUNDTRIP_ENABLED"

DEFAULT_ROTATION_HOURS = 24
MINIMUM_PSEUDONYM_KEY_BYTES = 32
MAXIMUM_ROTATION_HOURS = 24 * 365
MAXIMUM_PREVIOUS_PSEUDONYM_KEYS = 4
_KEY_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,32}$")

EnumT = TypeVar("EnumT", bound=Enum)


def _parse_enum(
    enum_type: type[EnumT],
    raw: str | None,
    *,
    default: EnumT,
    env_name: str,
) -> EnumT:
    value = raw.strip().lower() if raw is not None else default.value
    try:
        return enum_type(value)
    except ValueError as exc:
        choices = ", ".join(member.value for member in enum_type)
        message = f"{env_name} must be one of: {choices}"
        raise ValueError(message) from exc


def _parse_bool(raw: str | None, *, default: bool, env_name: str) -> bool:
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"true", "1", "yes", "y", "on"}:
        return True
    if normalized in {"false", "0", "no", "n", "off"}:
        return False
    message = f"{env_name} must be a boolean value"
    raise ValueError(message)


def _parse_rotation_hours(raw: str | None) -> int:
    if raw is None or not raw.strip():
        return DEFAULT_ROTATION_HOURS
    try:
        value = int(raw)
    except ValueError as exc:
        message = f"{ROTATION_HOURS_ENV} must be an integer"
        raise ValueError(message) from exc
    if value < 1 or value > MAXIMUM_ROTATION_HOURS:
        message = f"{ROTATION_HOURS_ENV} must be between 1 and {MAXIMUM_ROTATION_HOURS}"
        raise ValueError(message)
    return value


def _load_policy(raw_path: str | None) -> tuple[Path | None, IdentityPolicy]:
    if raw_path is None or not raw_path.strip():
        return None, IdentityPolicy()

    policy_path = Path(raw_path).expanduser()
    try:
        raw_policy = policy_path.read_text(encoding="utf-8")
    except OSError as exc:
        message = f"Unable to read identity policy file: {policy_path}"
        raise ValueError(message) from exc

    try:
        parsed = json.loads(raw_policy)
    except json.JSONDecodeError as exc:
        message = f"Identity policy file is not valid JSON: {exc}"
        raise ValueError(message) from exc
    if not isinstance(parsed, dict):
        raise ValueError("Identity policy file must contain a JSON object")
    return policy_path, IdentityPolicy.from_mapping(parsed)


def _decode_pseudonym_key(encoded: str, source_name: str) -> bytes:
    try:
        encoded_bytes = encoded.strip().encode("ascii")
    except UnicodeEncodeError as exc:
        message = f"{source_name} must contain a base64 value"
        raise ValueError(message) from exc

    try:
        key = base64.b64decode(
            encoded_bytes,
            altchars=b"-_",
            validate=True,
        )
    except (binascii.Error, ValueError) as exc:
        message = f"{source_name} must contain a valid base64 value"
        raise ValueError(message) from exc

    if len(key) < MINIMUM_PSEUDONYM_KEY_BYTES:
        message = (
            f"{source_name} must decode to at least {MINIMUM_PSEUDONYM_KEY_BYTES} bytes"
        )
        raise ValueError(message)
    return key


def _parse_keyring_entry(
    value: object,
    *,
    field_name: str,
) -> PseudonymKeyVersion:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a JSON object")
    unknown = set(value).difference({"id", "key"})
    if unknown:
        joined = ", ".join(sorted(unknown))
        raise ValueError(f"{field_name} contains unknown fields: {joined}")
    key_id = value.get("id")
    encoded_key = value.get("key")
    if not isinstance(key_id, str) or _KEY_ID_RE.fullmatch(key_id) is None:
        raise ValueError(f"{field_name}.id must match {_KEY_ID_RE.pattern}")
    if not isinstance(encoded_key, str):
        raise ValueError(f"{field_name}.key must be a Base64 string")
    return PseudonymKeyVersion(
        key_id=key_id,
        key=_decode_pseudonym_key(encoded_key, f"{field_name}.key"),
    )


def _load_pseudonym_keyring(path: Path) -> PseudonymKeyring:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Unable to read pseudonym keyring file: {path}") from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Pseudonym keyring file is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Pseudonym keyring file must contain a JSON object")
    unknown = set(parsed).difference({"version", "active", "previous"})
    if unknown:
        joined = ", ".join(sorted(unknown))
        raise ValueError(f"Pseudonym keyring contains unknown fields: {joined}")
    if parsed.get("version") != 1:
        raise ValueError("Pseudonym keyring version must be 1")

    active = _parse_keyring_entry(parsed.get("active"), field_name="active")
    raw_previous = parsed.get("previous", [])
    if not isinstance(raw_previous, list):
        raise ValueError("Pseudonym keyring previous must be a JSON array")
    if len(raw_previous) > MAXIMUM_PREVIOUS_PSEUDONYM_KEYS:
        raise ValueError(
            "Pseudonym keyring contains too many previous keys "
            f"(maximum {MAXIMUM_PREVIOUS_PSEUDONYM_KEYS})"
        )
    previous = tuple(
        _parse_keyring_entry(entry, field_name=f"previous[{index}]")
        for index, entry in enumerate(raw_previous)
    )
    ids = [active.key_id, *(entry.key_id for entry in previous)]
    if len(ids) != len(set(ids)):
        raise ValueError("Pseudonym keyring key IDs must be unique")
    return PseudonymKeyring(active=active, previous=previous)


def _load_pseudonym_keys(
    source: Mapping[str, str],
    mode: PrivacyMode,
) -> tuple[bytes | None, Path | None, PseudonymKeyring | None]:
    direct_key = source.get(PSEUDONYM_KEY_ENV)
    key_file = source.get(PSEUDONYM_KEY_FILE_ENV)
    keyring_file = source.get(PSEUDONYM_KEYRING_FILE_ENV)
    has_direct_key = bool(direct_key and direct_key.strip())
    has_key_file = bool(key_file and key_file.strip())
    has_keyring_file = bool(keyring_file and keyring_file.strip())

    configured_sources = sum((has_direct_key, has_key_file, has_keyring_file))
    if configured_sources > 1:
        raise ValueError(
            "Set only one of "
            f"{PSEUDONYM_KEY_ENV}, {PSEUDONYM_KEY_FILE_ENV}, and "
            f"{PSEUDONYM_KEYRING_FILE_ENV}"
        )
    if mode is not PrivacyMode.PSEUDONYMIZE:
        return None, None, None
    if configured_sources == 0:
        raise ValueError("Pseudonymize mode requires exactly one pseudonym key source")

    if has_direct_key:
        return (
            _decode_pseudonym_key(direct_key or "", PSEUDONYM_KEY_ENV),
            None,
            None,
        )

    if has_key_file:
        path = Path(key_file or "").expanduser()
        try:
            encoded = path.read_text(encoding="ascii")
        except (OSError, UnicodeError) as exc:
            message = f"Unable to read pseudonym key file: {path}"
            raise ValueError(message) from exc
        return _decode_pseudonym_key(encoded, PSEUDONYM_KEY_FILE_ENV), None, None

    path = Path(keyring_file or "").expanduser()
    keyring = _load_pseudonym_keyring(path)
    return keyring.active.key, path, keyring


@dataclass(frozen=True, slots=True)
class IdentityPrivacyConfig:
    """Validated identity privacy configuration."""

    mode: PrivacyMode = PrivacyMode.OFF
    policy_file: Path | None = None
    policy: IdentityPolicy = field(default_factory=IdentityPolicy, repr=False)
    pseudonym_key: bytes | None = field(default=None, repr=False)
    pseudonym_keyring_file: Path | None = None
    pseudonym_keyring: PseudonymKeyring | None = field(default=None, repr=False)
    correlation_scope: CorrelationScope = CorrelationScope.DEPLOYMENT
    correlation_domain: str | None = None
    rotation_hours: int = DEFAULT_ROTATION_HOURS
    self_identification_enabled: bool = True
    alias_roundtrip_enabled: bool = False
    unstructured_content_policy: UnstructuredContentPolicy = (
        UnstructuredContentPolicy.ALLOW
    )

    @property
    def enabled(self) -> bool:
        """Return whether identity privacy is active."""
        return self.mode is not PrivacyMode.OFF

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
    ) -> IdentityPrivacyConfig:
        """Build configuration from environment variables.

        Disabled mode intentionally ignores all dependent privacy settings so
        an inactive deployment remains backward compatible.

        Args:
            env: Optional environment mapping, primarily for tests.

        Returns:
            A validated immutable configuration.

        Raises:
            ValueError: If active privacy configuration is malformed.
        """
        source = os.environ if env is None else env
        mode = _parse_enum(
            PrivacyMode,
            source.get(PRIVACY_MODE_ENV),
            default=PrivacyMode.OFF,
            env_name=PRIVACY_MODE_ENV,
        )
        if mode is PrivacyMode.OFF:
            return cls()

        policy_file, policy = _load_policy(source.get(POLICY_FILE_ENV))
        correlation_scope = _parse_enum(
            CorrelationScope,
            source.get(CORRELATION_SCOPE_ENV),
            default=CorrelationScope.DEPLOYMENT,
            env_name=CORRELATION_SCOPE_ENV,
        )
        correlation_domain = source.get(CORRELATION_DOMAIN_ENV)
        if correlation_domain is not None:
            correlation_domain = correlation_domain.strip() or None
        if (
            mode is PrivacyMode.PSEUDONYMIZE
            and correlation_scope is CorrelationScope.DEPLOYMENT
            and correlation_domain is None
        ):
            message = (
                f"{CORRELATION_DOMAIN_ENV} is required for deployment-scoped pseudonyms"
            )
            raise ValueError(message)

        alias_roundtrip_enabled = _parse_bool(
            source.get(ALIAS_ROUNDTRIP_ENV),
            default=False,
            env_name=ALIAS_ROUNDTRIP_ENV,
        )
        if alias_roundtrip_enabled and mode is not PrivacyMode.PSEUDONYMIZE:
            raise ValueError(
                f"{ALIAS_ROUNDTRIP_ENV} requires pseudonymize privacy mode"
            )

        pseudonym_key, keyring_file, keyring = _load_pseudonym_keys(source, mode)

        return cls(
            mode=mode,
            policy_file=policy_file,
            policy=policy,
            pseudonym_key=pseudonym_key,
            pseudonym_keyring_file=keyring_file,
            pseudonym_keyring=keyring,
            correlation_scope=correlation_scope,
            correlation_domain=correlation_domain,
            rotation_hours=_parse_rotation_hours(source.get(ROTATION_HOURS_ENV)),
            self_identification_enabled=_parse_bool(
                source.get(SELF_IDENTIFICATION_ENV),
                default=True,
                env_name=SELF_IDENTIFICATION_ENV,
            ),
            alias_roundtrip_enabled=alias_roundtrip_enabled,
            unstructured_content_policy=_parse_enum(
                UnstructuredContentPolicy,
                source.get(UNSTRUCTURED_CONTENT_POLICY_ENV),
                default=UnstructuredContentPolicy.ALLOW,
                env_name=UNSTRUCTURED_CONTENT_POLICY_ENV,
            ),
        )
