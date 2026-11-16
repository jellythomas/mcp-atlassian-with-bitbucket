"""Caller- and tenant-isolated identity alias roundtrip support."""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from collections.abc import Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

from .config import IdentityPrivacyConfig
from .current_user import CurrentIdentityResolver
from .registry import ToolService
from .types import PrivacyMode

_ALIAS_PREFIXES = ("pid:v1:", "pid:v2:")
_DEFAULT_MAX_ENTRIES = 10_000


class AliasResolutionError(ValueError):
    """Raised when an identity alias is unknown, expired, or unauthorized."""


@dataclass(frozen=True, slots=True)
class AliasCallerBinding:
    """Hashed request caller and tenant binding."""

    digest: str = field(repr=False)
    instance: str


@dataclass(frozen=True, slots=True)
class _AliasRecord:
    login: str | None = field(default=None, repr=False)
    local_id: str | None = field(default=None, repr=False)
    expires_at: float = 0.0


_AliasCallerMap = dict[ToolService, AliasCallerBinding]
_current_alias_callers: ContextVar[_AliasCallerMap | None] = ContextVar(
    "mcp_atlassian_with_bitbucket_and_privacy_identity_alias_callers",
    default=None,
)


def begin_alias_caller_scope() -> Token[_AliasCallerMap | None]:
    """Start an empty caller-binding scope for one tool invocation."""
    return _current_alias_callers.set({})


def reset_alias_caller_scope(token: Token[_AliasCallerMap | None]) -> None:
    """Restore the preceding caller-binding scope."""
    _current_alias_callers.reset(token)


def _frame(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return len(encoded).to_bytes(4, "big") + encoded


def _normalize_instance(instance: str) -> str:
    stripped = instance.strip().rstrip("/")
    if not stripped:
        return ""
    parsed = urlsplit(stripped)
    if not parsed.scheme or not parsed.netloc:
        return stripped.casefold()
    normalized_netloc = parsed.hostname.casefold() if parsed.hostname else ""
    if parsed.port is not None:
        normalized_netloc = f"{normalized_netloc}:{parsed.port}"
    return urlunsplit(
        (
            parsed.scheme.casefold(),
            normalized_netloc,
            parsed.path.rstrip("/"),
            parsed.query,
            "",
        )
    )


def record_alias_caller(
    service: ToolService,
    instance: str,
    *credential_parts: object,
) -> None:
    """Record a one-way caller fingerprint while an alias scope is active."""
    callers = _current_alias_callers.get()
    if callers is None:
        return
    material = tuple(
        part.strip()
        for part in credential_parts
        if isinstance(part, str) and part.strip()
    )
    if not material:
        return

    normalized_instance = _normalize_instance(instance)
    digest = hashlib.sha256(
        b"mcp-alias-caller-v1"
        + _frame(service.value)
        + _frame(normalized_instance)
        + b"".join(_frame(part) for part in material)
    ).hexdigest()
    updated = dict(callers)
    updated[service] = AliasCallerBinding(
        digest=digest,
        instance=normalized_instance,
    )
    _current_alias_callers.set(updated)


def _current_caller_binding(
    service: ToolService,
    instance: str,
) -> AliasCallerBinding | None:
    callers = _current_alias_callers.get()
    if callers is not None and service in callers:
        return callers[service]

    current_identity = CurrentIdentityResolver().resolve(service)
    if current_identity is None:
        return None
    normalized_instance = _normalize_instance(instance)
    digest = hashlib.sha256(
        b"mcp-alias-current-identity-v1"
        + _frame(service.value)
        + _frame(normalized_instance)
        + b"".join(_frame(value) for value in sorted(current_identity.identifiers))
    ).hexdigest()
    return AliasCallerBinding(
        digest=digest,
        instance=normalized_instance,
    )


def is_identity_alias(value: object) -> bool:
    """Return whether a value uses the pseudonym alias wire format."""
    return isinstance(value, str) and value.startswith(_ALIAS_PREFIXES)


class AliasRoundtripRegistry:
    """Store short-lived raw identifiers behind caller-bound aliases."""

    def __init__(
        self,
        config: IdentityPrivacyConfig,
        *,
        clock: Callable[[], datetime] | None = None,
        max_entries: int = _DEFAULT_MAX_ENTRIES,
    ) -> None:
        if (
            config.alias_roundtrip_enabled
            and config.mode is not PrivacyMode.PSEUDONYMIZE
        ):
            raise ValueError("Alias roundtrip requires pseudonymize mode")
        if max_entries < 1:
            raise ValueError("Alias roundtrip max_entries must be positive")
        self._enabled = config.alias_roundtrip_enabled
        self._rotation_seconds = config.rotation_hours * 60 * 60
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._max_entries = max_entries
        self._records: OrderedDict[
            tuple[str, str, str, str],
            _AliasRecord,
        ] = OrderedDict()
        self._lock = threading.RLock()

    @property
    def enabled(self) -> bool:
        """Return whether roundtrip registration and resolution are active."""
        return self._enabled

    def register(
        self,
        *,
        service: ToolService,
        instance: str,
        alias: str,
        login: str | None,
        local_id: str | None,
    ) -> None:
        """Register an alias only within the active caller and tenant scope."""
        if not self._enabled or not is_identity_alias(alias) or not (login or local_id):
            return
        caller = _current_caller_binding(service, instance)
        if caller is None:
            return
        now = self._timestamp()
        record = _AliasRecord(
            login=login,
            local_id=local_id,
            expires_at=self._next_epoch_boundary(now),
        )
        key = (service.value, caller.instance, caller.digest, alias)
        with self._lock:
            self._remove_expired(now)
            self._records.pop(key, None)
            while len(self._records) >= self._max_entries:
                self._records.popitem(last=False)
            self._records[key] = record

    def resolve(
        self,
        *,
        service: ToolService,
        instance: str,
        alias: str,
        prefer_local_id: bool,
    ) -> str:
        """Resolve an alias or reject it without exposing mapping details."""
        if not self._enabled or not is_identity_alias(alias):
            return alias
        caller = _current_caller_binding(service, instance)
        if caller is None:
            raise AliasResolutionError("Identity alias is unknown or unauthorized")

        now = self._timestamp()
        key = (service.value, caller.instance, caller.digest, alias)
        with self._lock:
            self._remove_expired(now)
            record = self._records.get(key)
            if record is None:
                raise AliasResolutionError(
                    "Identity alias is unknown, expired, or unauthorized"
                )
            self._records.move_to_end(key)

        resolved = (
            record.local_id or record.login
            if prefer_local_id
            else record.login or record.local_id
        )
        if not resolved:
            raise AliasResolutionError("Identity alias has no writable identifier")
        return resolved

    def _timestamp(self) -> float:
        current = self._clock()
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("Alias roundtrip clock must be timezone-aware")
        return current.timestamp()

    def _next_epoch_boundary(self, timestamp: float) -> float:
        epoch = int(timestamp // self._rotation_seconds)
        return float((epoch + 1) * self._rotation_seconds)

    def _remove_expired(self, now: float) -> None:
        expired = [
            key for key, record in self._records.items() if record.expires_at <= now
        ]
        for key in expired:
            self._records.pop(key, None)


_active_registry: ContextVar[AliasRoundtripRegistry | None] = ContextVar(
    "mcp_atlassian_with_bitbucket_and_privacy_active_alias_roundtrip_registry",
    default=None,
)


def begin_alias_roundtrip_registry_scope(
    registry: AliasRoundtripRegistry | None,
) -> Token[AliasRoundtripRegistry | None]:
    """Bind one server's alias registry to the current tool invocation."""
    return _active_registry.set(registry)


def reset_alias_roundtrip_registry_scope(
    token: Token[AliasRoundtripRegistry | None],
) -> None:
    """Restore the preceding request-local alias registry."""
    _active_registry.reset(token)


def resolve_identity_alias(
    value: str,
    *,
    service: ToolService,
    instance: str,
    prefer_local_id: bool,
) -> str:
    """Resolve one write argument through the active registry when needed."""
    registry = _active_registry.get()
    if registry is None:
        return value
    return registry.resolve(
        service=service,
        instance=instance,
        alias=value,
        prefer_local_id=prefer_local_id,
    )
