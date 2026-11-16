"""The health endpoint reports the active identity privacy mode."""

import json
from unittest.mock import Mock

import pytest

from mcp_atlassian_with_bitbucket_and_privacy.servers.main import health_check


@pytest.mark.anyio
async def test_healthz_reports_off_without_privacy_variables(monkeypatch) -> None:
    monkeypatch.delenv("MCP_ATLASSIAN_IDENTITY_PRIVACY_MODE", raising=False)

    response = await health_check(Mock())

    assert json.loads(response.body) == {"status": "ok", "identity_privacy": "off"}


@pytest.mark.anyio
async def test_healthz_reports_configured_mode(monkeypatch) -> None:
    monkeypatch.setenv("MCP_ATLASSIAN_IDENTITY_PRIVACY_MODE", "anonymize")

    response = await health_check(Mock())

    assert json.loads(response.body)["identity_privacy"] == "anonymize"
