"""Tests for request-local current identity state."""

import asyncio

from mcp_atlassian_with_bitbucket_and_privacy.privacy import (
    CurrentIdentityResolver,
    ToolService,
    begin_current_identity_scope,
    record_current_identity,
    reset_current_identity_scope,
)


def test_recording_outside_scope_is_a_noop() -> None:
    record_current_identity(ToolService.JIRA, "user")

    assert CurrentIdentityResolver().resolve(ToolService.JIRA) is None


def test_scope_records_normalizes_and_merges_identifiers() -> None:
    token = begin_current_identity_scope()
    try:
        record_current_identity(ToolService.JIRA, " User ", None)
        record_current_identity(ToolService.JIRA, "ACCOUNT-ID")
        current = CurrentIdentityResolver().resolve(ToolService.JIRA)

        assert current is not None
        assert current.matches("user")
        assert current.matches("account-id")
        assert "user" not in repr(current)
    finally:
        reset_current_identity_scope(token)

    assert CurrentIdentityResolver().resolve(ToolService.JIRA) is None


def test_services_are_isolated_within_scope() -> None:
    token = begin_current_identity_scope()
    try:
        record_current_identity(ToolService.JIRA, "jira-user")
        record_current_identity(ToolService.CONFLUENCE, "confluence-user")

        jira = CurrentIdentityResolver().resolve(ToolService.JIRA)
        confluence = CurrentIdentityResolver().resolve(ToolService.CONFLUENCE)
        assert jira is not None and jira.matches("jira-user")
        assert confluence is not None and confluence.matches("confluence-user")
        assert not jira.matches("confluence-user")
    finally:
        reset_current_identity_scope(token)


def test_concurrent_scopes_do_not_leak() -> None:
    async def worker(login: str) -> bool:
        token = begin_current_identity_scope()
        try:
            record_current_identity(ToolService.JIRA, login)
            await asyncio.sleep(0)
            current = CurrentIdentityResolver().resolve(ToolService.JIRA)
            return current is not None and current.matches(login)
        finally:
            reset_current_identity_scope(token)

    async def run() -> tuple[bool, bool]:
        first, second = await asyncio.gather(
            worker("first"),
            worker("second"),
        )
        return first, second

    assert asyncio.run(run()) == (True, True)
