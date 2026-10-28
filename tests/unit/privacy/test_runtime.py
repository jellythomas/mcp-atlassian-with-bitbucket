"""Tests for privacy-safe runtime diagnostic helpers."""

import asyncio

import pytest

from mcp_atlassian_with_bitbucket_and_privacy.privacy import (
    begin_identity_privacy_runtime,
    is_identity_privacy_runtime_active,
    privacy_safe_exception_detail,
    privacy_safe_value,
    reset_identity_privacy_runtime,
)
from mcp_atlassian_with_bitbucket_and_privacy.privacy.runtime import (
    error_details_redacted,
)


def test_runtime_scope_redacts_values_and_exception_details() -> None:
    assert is_identity_privacy_runtime_active() is False


def test_runtime_scope_is_isolated_between_concurrent_tasks() -> None:
    async def protected_worker(started: asyncio.Event) -> bool:
        token = begin_identity_privacy_runtime()
        try:
            started.set()
            await asyncio.sleep(0)
            return is_identity_privacy_runtime_active()
        finally:
            reset_identity_privacy_runtime(token)

    async def unprotected_worker(started: asyncio.Event) -> bool:
        await started.wait()
        return is_identity_privacy_runtime_active()

    async def run() -> tuple[bool, bool]:
        started = asyncio.Event()
        protected, unprotected = await asyncio.gather(
            protected_worker(started),
            unprotected_worker(started),
        )
        return protected, unprotected

    assert asyncio.run(run()) == (True, False)
    assert is_identity_privacy_runtime_active() is False
    assert privacy_safe_value("CANARY") == "CANARY"
    assert privacy_safe_exception_detail(ValueError("CANARY")) == "CANARY"

    token = begin_identity_privacy_runtime()
    try:
        assert is_identity_privacy_runtime_active() is True
        assert privacy_safe_value("CANARY") == "<redacted>"
        # Error texts stay complete by default; only data values are masked.
        assert privacy_safe_exception_detail(ValueError("CANARY")) == "CANARY"
    finally:
        reset_identity_privacy_runtime(token)

    assert is_identity_privacy_runtime_active() is False


def test_error_redaction_can_be_enabled_by_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("IDENTITY_PRIVACY_REDACT_ERRORS", "true")
    assert error_details_redacted() is False  # not inside a privacy runtime

    token = begin_identity_privacy_runtime()
    try:
        assert error_details_redacted() is True
        assert privacy_safe_exception_detail(ValueError("CANARY")) == "ValueError"
    finally:
        reset_identity_privacy_runtime(token)
