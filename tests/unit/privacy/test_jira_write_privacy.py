"""Tests for Jira write-response privacy helpers."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from mcp_atlassian_with_bitbucket_and_privacy.jira.issues import (
    _privacy_issue_metadata_kwargs,
)
from mcp_atlassian_with_bitbucket_and_privacy.jira.watchers import WatchersMixin
from mcp_atlassian_with_bitbucket_and_privacy.privacy import (
    begin_identity_privacy_runtime,
    reset_identity_privacy_runtime,
)


def test_issue_refetch_metadata_is_added_only_in_privacy_runtime() -> None:
    assert _privacy_issue_metadata_kwargs() == {}

    token = begin_identity_privacy_runtime()
    try:
        assert _privacy_issue_metadata_kwargs() == {"expand": "names,schema"}
    finally:
        reset_identity_privacy_runtime(token)

    assert _privacy_issue_metadata_kwargs() == {}


def _watchers_mixin() -> WatchersMixin:
    mixin = object.__new__(WatchersMixin)
    mixin.jira = MagicMock()
    mixin.config = SimpleNamespace()
    return mixin


def test_add_watcher_message_hides_identifier_only_in_privacy_runtime() -> None:
    mixin = _watchers_mixin()

    off_result = mixin.add_watcher("TEST-1", "human01")
    assert "human01" in off_result["message"]
    assert off_result["user"] == "human01"

    token = begin_identity_privacy_runtime()
    try:
        protected = mixin.add_watcher("TEST-1", "human01")
    finally:
        reset_identity_privacy_runtime(token)

    assert "human01" not in protected["message"]
    assert "<redacted>" in protected["message"]
    assert protected["user"] == "human01"


def test_remove_watcher_message_hides_identifier_in_privacy_runtime() -> None:
    mixin = _watchers_mixin()
    token = begin_identity_privacy_runtime()
    try:
        protected = mixin.remove_watcher(
            "TEST-1",
            account_id="CANARY-ACCOUNT-ID",
        )
    finally:
        reset_identity_privacy_runtime(token)

    assert "CANARY" not in protected["message"]
    assert protected["user"] == "CANARY-ACCOUNT-ID"
