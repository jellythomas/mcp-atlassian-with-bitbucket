"""Regression tests for known authentication identity logs."""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from mcp_atlassian_with_bitbucket_and_privacy.jira.client import JiraClient
from mcp_atlassian_with_bitbucket_and_privacy.servers.dependencies import (
    _confluence_on_validated,
    _jira_on_validated,
)


def test_jira_validation_log_does_not_include_identity(
    caplog: pytest.LogCaptureFixture,
) -> None:
    request = MagicMock()
    request.state = SimpleNamespace()

    with caplog.at_level(logging.DEBUG):
        _jira_on_validated(
            "get_jira_fetcher",
            request,
            "CANARY-ACCOUNT-ID",
            "header_pat",
            "CANARY@example.test",
        )

    assert "CANARY" not in caplog.text


def test_confluence_validation_log_does_not_include_identity(
    caplog: pytest.LogCaptureFixture,
) -> None:
    request = MagicMock()
    request.state = SimpleNamespace()

    with caplog.at_level(logging.DEBUG):
        _confluence_on_validated(
            "get_confluence_fetcher",
            request,
            {
                "email": "CANARY@example.test",
                "displayName": "CANARY PERSON",
            },
            "header_pat",
            None,
        )

    assert "CANARY" not in caplog.text


def test_jira_authentication_success_log_does_not_include_identity(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = object.__new__(JiraClient)
    client.jira = MagicMock()
    client.jira.myself.return_value = {
        "displayName": "CANARY PERSON",
        "emailAddress": "CANARY@example.test",
    }
    client.config = SimpleNamespace(url="https://jira.example.test")

    with caplog.at_level(logging.INFO):
        client._validate_authentication()

    assert "CANARY" not in caplog.text
