"""Request-local current identity state for self-identification."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, field

from .policy import normalize_login
from .registry import ToolService

_IdentityMap = dict[ToolService, "CurrentIdentity"]
_current_identities: ContextVar[_IdentityMap | None] = ContextVar(
    "mcp_atlassian_with_bitbucket_and_privacy_current_identities",
    default=None,
)


@dataclass(frozen=True, slots=True)
class CurrentIdentity:
    """Normalized identifiers belonging to the authenticated caller."""

    identifiers: frozenset[str] = field(repr=False)

    @classmethod
    def from_values(cls, *values: object) -> CurrentIdentity | None:
        """Create a current identity from non-empty string identifiers."""
        normalized = frozenset(
            normalize_login(value)
            for value in values
            if isinstance(value, str) and normalize_login(value)
        )
        return cls(normalized) if normalized else None

    def matches(self, *values: object) -> bool:
        """Return whether any candidate identifies the current caller."""
        return any(
            normalize_login(value) in self.identifiers
            for value in values
            if isinstance(value, str) and normalize_login(value)
        )


class CurrentIdentityResolver:
    """Read the current service identity from request-local context."""

    def resolve(self, service: ToolService) -> CurrentIdentity | None:
        """Return the current identity for a service, if it was resolved."""
        identities = _current_identities.get()
        return identities.get(service) if identities is not None else None


def begin_current_identity_scope() -> Token[_IdentityMap | None]:
    """Start an empty current-identity scope for one tool invocation."""
    return _current_identities.set({})


def reset_current_identity_scope(token: Token[_IdentityMap | None]) -> None:
    """Restore the preceding current-identity scope."""
    _current_identities.reset(token)


def record_current_identity(service: ToolService, *values: object) -> None:
    """Record service identifiers when a privacy scope is active."""
    identities = _current_identities.get()
    if identities is None:
        return

    candidate = CurrentIdentity.from_values(*values)
    if candidate is None:
        return

    updated = dict(identities)
    existing = updated.get(service)
    if existing is not None:
        candidate = CurrentIdentity(
            identifiers=existing.identifiers | candidate.identifiers
        )
    updated[service] = candidate
    _current_identities.set(updated)
