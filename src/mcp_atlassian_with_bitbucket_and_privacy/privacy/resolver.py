"""Canonical identity resolution for cross-tool pseudonym stability."""

from __future__ import annotations

from .policy import normalize_login
from .types import CanonicalIdentity, CorrelationScope, IdentitySource


def _normalize_context(value: str, field_name: str) -> str:
    normalized = value.strip().casefold().rstrip("/")
    if not normalized:
        message = f"Identity source {field_name} must not be empty"
        raise ValueError(message)
    return normalized


class CanonicalIdentityResolver:
    """Resolve shared logins or safe instance-local fallback identities."""

    def __init__(self, correlation_scope: CorrelationScope) -> None:
        self._correlation_scope = correlation_scope

    def resolve(self, source: IdentitySource) -> CanonicalIdentity | None:
        """Resolve an identity without name or email fallback.

        An exact normalized login is the only cross-system correlation key.
        Without a login, an opaque local ID is constrained to its connector
        instance. If neither value exists, no stable canonical identity can be
        produced.

        Args:
            source: Connector identity input.

        Returns:
            A sensitive canonical identity, or None when no stable ID exists.
        """
        entity_kind = _normalize_context(source.entity_kind, "entity_kind")
        normalized_login = normalize_login(source.login or "")
        if normalized_login:
            return self._from_login(
                normalized_login,
                source=source,
                entity_kind=entity_kind,
            )

        local_id = (source.local_id or "").strip()
        if not local_id:
            return None
        return CanonicalIdentity(
            scope=CorrelationScope.INSTANCE,
            entity_kind=entity_kind,
            subject_id=local_id,
            connector=_normalize_context(source.connector, "connector"),
            instance=_normalize_context(source.instance, "instance"),
        )

    def _from_login(
        self,
        normalized_login: str,
        *,
        source: IdentitySource,
        entity_kind: str,
    ) -> CanonicalIdentity:
        if self._correlation_scope is CorrelationScope.DEPLOYMENT:
            return CanonicalIdentity(
                scope=CorrelationScope.DEPLOYMENT,
                entity_kind=entity_kind,
                subject_id=normalized_login,
            )

        connector = _normalize_context(source.connector, "connector")
        if self._correlation_scope is CorrelationScope.CONNECTOR:
            return CanonicalIdentity(
                scope=CorrelationScope.CONNECTOR,
                entity_kind=entity_kind,
                subject_id=normalized_login,
                connector=connector,
            )

        return CanonicalIdentity(
            scope=CorrelationScope.INSTANCE,
            entity_kind=entity_kind,
            subject_id=normalized_login,
            connector=connector,
            instance=_normalize_context(source.instance, "instance"),
        )
