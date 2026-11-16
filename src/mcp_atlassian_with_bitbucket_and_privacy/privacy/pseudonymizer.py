"""Stateless, time-bounded pseudonyms for canonical identities."""

from __future__ import annotations

import base64
import hashlib
import hmac
from collections.abc import Callable, Iterable
from datetime import datetime, timezone

from .config import MINIMUM_PSEUDONYM_KEY_BYTES, IdentityPrivacyConfig
from .keyring import PseudonymKeyVersion
from .types import CanonicalIdentity, PrivacyMode

Clock = Callable[[], datetime]

_PERIOD_KEY_CONTEXT = "mcp-identity-period-v1"
_SUBJECT_CONTEXT = "mcp-identity-subject-v1"
_ALIAS_BYTES = 16


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _frame(parts: Iterable[str]) -> bytes:
    framed = bytearray()
    for part in parts:
        encoded = part.encode("utf-8")
        framed.extend(len(encoded).to_bytes(4, byteorder="big"))
        framed.extend(encoded)
    return bytes(framed)


class Pseudonymizer:
    """Derive deterministic aliases within UTC-aligned rotation epochs."""

    def __init__(
        self,
        *,
        master_key: bytes,
        correlation_domain: str,
        rotation_hours: int,
        clock: Clock | None = None,
        key_id: str | None = None,
        previous_keys: tuple[PseudonymKeyVersion, ...] = (),
    ) -> None:
        if len(master_key) < MINIMUM_PSEUDONYM_KEY_BYTES:
            message = (
                "Pseudonymizer master_key must contain at least "
                f"{MINIMUM_PSEUDONYM_KEY_BYTES} bytes"
            )
            raise ValueError(message)
        if rotation_hours < 1:
            raise ValueError("Pseudonymizer rotation_hours must be positive")

        self._active_key = PseudonymKeyVersion(
            key_id=key_id or "",
            key=bytes(master_key),
        )
        self._previous_keys = tuple(previous_keys)
        self._correlation_domain = correlation_domain.strip()
        self._rotation_seconds = rotation_hours * 60 * 60
        self._clock = clock or _utc_now

    @classmethod
    def from_config(
        cls,
        config: IdentityPrivacyConfig,
        *,
        clock: Clock | None = None,
    ) -> Pseudonymizer:
        """Create a pseudonymizer from validated pseudonymize configuration."""
        if config.mode is not PrivacyMode.PSEUDONYMIZE:
            raise ValueError("Pseudonymizer requires pseudonymize privacy mode")
        if config.pseudonym_key is None:
            raise ValueError("Pseudonymizer configuration is missing its key")

        keyring = config.pseudonym_keyring
        return cls(
            master_key=(
                keyring.active.key if keyring is not None else config.pseudonym_key
            ),
            correlation_domain=config.correlation_domain or "",
            rotation_hours=config.rotation_hours,
            clock=clock,
            key_id=keyring.active.key_id if keyring is not None else None,
            previous_keys=keyring.previous if keyring is not None else (),
        )

    def pseudonymize(self, identity: CanonicalIdentity) -> str:
        """Return the current epoch's opaque alias for a canonical identity."""
        return self._pseudonymize_with(self._active_key, identity)

    def pseudonymize_candidates(
        self,
        identity: CanonicalIdentity,
    ) -> tuple[str, ...]:
        """Return active and accepted predecessor aliases for roundtrip use."""
        return tuple(
            self._pseudonymize_with(key_version, identity)
            for key_version in (self._active_key, *self._previous_keys)
        )

    def _pseudonymize_with(
        self,
        key_version: PseudonymKeyVersion,
        identity: CanonicalIdentity,
    ) -> str:
        epoch = self.rotation_epoch()
        period_key = hmac.new(
            key_version.key,
            _frame(
                (
                    _PERIOD_KEY_CONTEXT,
                    key_version.key_id,
                    self._correlation_domain,
                    str(epoch),
                )
            ),
            hashlib.sha256,
        ).digest()
        digest = hmac.new(
            period_key,
            _frame(
                (
                    _SUBJECT_CONTEXT,
                    identity.scope.value,
                    identity.entity_kind,
                    identity.connector or "",
                    identity.instance or "",
                    identity.subject_id,
                )
            ),
            hashlib.sha256,
        ).digest()
        token = base64.urlsafe_b64encode(digest[:_ALIAS_BYTES]).decode("ascii")
        if key_version.key_id:
            return f"pid:v2:{key_version.key_id}:{token.rstrip('=')}"
        return f"pid:v1:{token.rstrip('=')}"

    def rotation_epoch(self, at: datetime | None = None) -> int:
        """Return the UTC-aligned epoch containing the supplied time."""
        current = self._clock() if at is None else at
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("Pseudonymizer clock must return a timezone-aware time")
        unix_seconds = int(current.astimezone(timezone.utc).timestamp())
        return unix_seconds // self._rotation_seconds
