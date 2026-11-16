"""Tests for the optional client header check."""

import logging

import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from mcp_atlassian_with_bitbucket_and_privacy.servers import client_header
from mcp_atlassian_with_bitbucket_and_privacy.servers.client_header import (
    ClientHeaderConfig,
    ClientHeaderMiddleware,
)
from mcp_atlassian_with_bitbucket_and_privacy.servers.main import (
    AtlassianMCP,
    UserTokenMiddleware,
)

HEADER = "X-Example-Client"
ENV = {"MCP_CLIENT_HEADER_NAME": HEADER}


def _config(**overrides: str) -> ClientHeaderConfig:
    config = ClientHeaderConfig.from_env({**ENV, **overrides})
    assert config is not None
    return config


def _client(**overrides: str) -> TestClient:
    async def ok(request: object) -> PlainTextResponse:
        return PlainTextResponse("ok")

    inner = Starlette(
        routes=[Route("/mcp", ok, methods=["GET", "POST"]), Route("/healthz", ok)]
    )
    return TestClient(ClientHeaderMiddleware(inner, _config(**overrides)))


class TestConfig:
    def test_disabled_without_header_name(self) -> None:
        assert ClientHeaderConfig.from_env({}) is None
        assert ClientHeaderConfig.from_env({"MCP_CLIENT_HEADER_NAME": "  "}) is None

    def test_defaults_to_count_mode(self) -> None:
        config = _config()

        assert config.mode == "count"
        assert config.header_name == b"x-example-client"

    def test_unknown_mode_never_enforces(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger=client_header.logger.name):
            config = _config(MCP_CLIENT_HEADER_MODE="strict")

        assert config.mode == "count"
        assert any("strict" in record.getMessage() for record in caplog.records)

    def test_invalid_pattern_falls_back_to_default(self) -> None:
        config = _config(MCP_CLIENT_HEADER_PATTERN="(")

        assert config.pattern.fullmatch("example/1.4.2")


class TestCountMode:
    def test_lets_every_request_through(self) -> None:
        client = _client()

        assert client.post("/mcp", headers={HEADER: "example/1.4.2"}).status_code == 200
        assert client.post("/mcp").status_code == 200
        assert client.post("/mcp", headers={HEADER: "nonsense"}).status_code == 200

    def test_log_names_only_the_value(self, caplog: pytest.LogCaptureFixture) -> None:
        client = _client()

        with caplog.at_level(logging.INFO, logger=client_header.logger.name):
            client.post(
                "/mcp",
                headers={
                    HEADER: "example/1.4.2",
                    "Authorization": "Bearer secret-token",
                    "X-Other": "secret-other",
                },
            )
            client.post("/mcp")
            client.post("/mcp", headers={HEADER: "no way"})

        lines = [
            record.getMessage()
            for record in caplog.records
            if record.name == client_header.logger.name
        ]
        assert lines == [
            "Client header example/1.4.2",
            "Client header missing",
            "Client header invalid",
        ]


class TestEnforceMode:
    def test_rejects_missing_and_invalid_values_with_426(self) -> None:
        client = _client(MCP_CLIENT_HEADER_MODE="enforce")

        for response in (
            client.post("/mcp"),
            client.post("/mcp", headers={HEADER: "no way"}),
        ):
            assert response.status_code == 426
            assert response.json() == {
                "error": {
                    "code": "client_rejected",
                    "message": "Unsupported or outdated client.",
                }
            }

    def test_accepts_a_valid_value(self) -> None:
        client = _client(MCP_CLIENT_HEADER_MODE="enforce")

        response = client.post("/mcp", headers={HEADER.lower(): "example/1.4.2"})

        assert response.status_code == 200

    def test_reject_message_and_pattern_are_configurable(self) -> None:
        client = _client(
            MCP_CLIENT_HEADER_MODE="enforce",
            MCP_CLIENT_HEADER_PATTERN=r"acme/\d+",
            MCP_CLIENT_HEADER_REJECT_MESSAGE="Please update the acme tool.",
        )

        assert client.post("/mcp", headers={HEADER: "acme/7"}).status_code == 200
        rejected = client.post("/mcp", headers={HEADER: "example/1.4.2"})
        assert rejected.status_code == 426
        assert rejected.json()["error"]["message"] == "Please update the acme tool."

    def test_health_probe_needs_no_header(self) -> None:
        client = _client(MCP_CLIENT_HEADER_MODE="enforce")

        assert client.get("/healthz").status_code == 200


class TestServerWiring:
    def test_http_app_is_unchanged_without_the_setting(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("MCP_CLIENT_HEADER_NAME", raising=False)

        app = AtlassianMCP("test").http_app()

        assert ClientHeaderMiddleware not in [m.cls for m in app.user_middleware]

    def test_http_app_runs_the_check_before_the_token_handling(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MCP_CLIENT_HEADER_NAME", HEADER)
        monkeypatch.setenv("MCP_CLIENT_HEADER_MODE", "enforce")

        app = AtlassianMCP("test").http_app()

        classes = [m.cls for m in app.user_middleware]
        assert classes.index(ClientHeaderMiddleware) < classes.index(
            UserTokenMiddleware
        )
