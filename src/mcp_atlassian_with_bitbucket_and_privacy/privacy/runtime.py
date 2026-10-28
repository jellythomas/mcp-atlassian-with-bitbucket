"""Request-local helpers for privacy-safe runtime diagnostics."""

from __future__ import annotations

import os
from collections.abc import Callable
from contextvars import ContextVar, Token

_privacy_runtime_active: ContextVar[bool] = ContextVar(
    "mcp_atlassian_with_bitbucket_and_privacy_identity_privacy_active",
    default=False,
)


_mention_alias_resolver: ContextVar[Callable[[str], str | None] | None] = ContextVar(
    "mcp_atlassian_with_bitbucket_and_privacy_mention_alias_resolver",
    default=None,
)


def begin_mention_alias_resolver(
    resolver: Callable[[str], str | None],
) -> Token[Callable[[str], str | None] | None]:
    """Expose login-to-alias resolution to preprocessing for this tool call."""
    return _mention_alias_resolver.set(resolver)


def reset_mention_alias_resolver(
    token: Token[Callable[[str], str | None] | None],
) -> None:
    """Restore the preceding mention alias resolver."""
    _mention_alias_resolver.reset(token)


def resolve_mention_alias(login: str) -> str | None:
    """Return the pseudonymous alias for a login, or None when unavailable."""
    resolver = _mention_alias_resolver.get()
    return resolver(login) if resolver is not None else None


def begin_identity_privacy_runtime() -> Token[bool]:
    """Mark the current tool invocation as privacy protected."""
    return _privacy_runtime_active.set(True)


def reset_identity_privacy_runtime(token: Token[bool]) -> None:
    """Restore the preceding privacy runtime state."""
    _privacy_runtime_active.reset(token)


def is_identity_privacy_runtime_active() -> bool:
    """Return whether the current execution is inside an enabled privacy guard."""
    return _privacy_runtime_active.get()


def error_details_redacted() -> bool:
    """Return whether error texts must be reduced to the exception type.

    Response data is always pseudonymized while privacy mode is active. Error
    texts are returned and logged completely by default, because log access is
    restricted to the operator and truncated errors are not diagnosable. Set
    ``IDENTITY_PRIVACY_REDACT_ERRORS=true`` to restore the redacted behaviour.
    """
    if not is_identity_privacy_runtime_active():
        return False
    return os.getenv("IDENTITY_PRIVACY_REDACT_ERRORS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def privacy_safe_value(value: object) -> str:
    """Return a redacted diagnostic value while privacy mode is active."""
    return "<redacted>" if is_identity_privacy_runtime_active() else str(value)


def privacy_safe_exception_detail(error: BaseException) -> str:
    """Return only the exception type while error redaction is active."""
    if error_details_redacted():
        return type(error).__name__
    return str(error).strip() or type(error).__name__
