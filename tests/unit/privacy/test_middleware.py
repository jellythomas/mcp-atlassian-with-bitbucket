"""Tests for the FastMCP final-response identity privacy guard."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from mcp_atlassian_with_bitbucket_and_privacy.privacy import (
    CurrentIdentityResolver,
    IdentityPrivacyConfig,
    IdentityResponseTransformer,
    PrivacyFilterMiddleware,
    PrivacyMode,
    ToolResponsePolicy,
    ToolService,
    UnstructuredContentPolicy,
    install_identity_privacy,
    record_current_identity,
)
from mcp_atlassian_with_bitbucket_and_privacy.privacy.current_user import (
    CurrentIdentity,
)
from mcp_atlassian_with_bitbucket_and_privacy.utils.decorators import handle_tool_errors


class ReplacingAdapter:
    def __init__(
        self,
        *,
        fail_with: str | None = None,
        mark_current: bool = False,
    ) -> None:
        self.calls = 0
        self.fail_with = fail_with
        self.mark_current = mark_current

    def transform(
        self,
        *,
        tool_name: str,
        policy: ToolResponsePolicy,
        value: Any,
        current_identity: CurrentIdentity | None,
    ) -> Any:
        self.calls += 1
        assert tool_name.startswith(policy.service.value)
        if self.fail_with is not None:
            raise RuntimeError(self.fail_with)
        transformed = _replace_display_names(value)
        if self.mark_current:
            transformed = _mark_current_identity(
                transformed,
                current_identity,
            )
        return transformed


class InvalidTopLevelAdapter(ReplacingAdapter):
    def transform(
        self,
        *,
        tool_name: str,
        policy: ToolResponsePolicy,
        value: Any,
        current_identity: CurrentIdentity | None,
    ) -> Any:
        self.calls += 1
        return [value]


def _replace_display_names(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                "Protected"
                if key in {"display_name", "displayName"}
                else _replace_display_names(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_replace_display_names(item) for item in value]
    return value


def _mark_current_identity(
    value: Any,
    current_identity: CurrentIdentity | None,
) -> Any:
    if isinstance(value, dict):
        transformed = {
            key: _mark_current_identity(item, current_identity)
            for key, item in value.items()
        }
        if current_identity is not None and current_identity.matches(
            value.get("name"),
            value.get("account_id"),
        ):
            transformed["is_current_user"] = True
            transformed["display_name"] = "You"
        return transformed
    if isinstance(value, list):
        return [_mark_current_identity(item, current_identity) for item in value]
    return value


def _enabled_config(
    *,
    raw_policy: UnstructuredContentPolicy = UnstructuredContentPolicy.ALLOW,
) -> IdentityPrivacyConfig:
    return IdentityPrivacyConfig(
        mode=PrivacyMode.ANONYMIZE,
        unstructured_content_policy=raw_policy,
    )


def _server_with_adapter(
    adapter: ReplacingAdapter | None,
    *,
    config: IdentityPrivacyConfig | None = None,
) -> FastMCP:
    server = FastMCP("privacy-test")
    adapters = {} if adapter is None else {ToolService.JIRA: adapter}
    install_identity_privacy(
        server,
        config=config or _enabled_config(),
        transformer=IdentityResponseTransformer(adapters),
    )
    return server


def _server_with_service_adapter(
    service: ToolService,
    adapter: ReplacingAdapter,
) -> FastMCP:
    server = FastMCP("privacy-service-test")
    install_identity_privacy(
        server,
        config=_enabled_config(),
        transformer=IdentityResponseTransformer({service: adapter}),
    )
    return server


@pytest.mark.anyio
async def test_disabled_mode_does_not_install_or_change_output() -> None:
    server = FastMCP("disabled-privacy")

    @server.tool(name="jira_get_user_profile")
    async def profile() -> dict[str, Any]:
        return {"user": {"display_name": "Sensitive"}}

    before = len(server.middleware)
    installed = install_identity_privacy(
        server,
        config=IdentityPrivacyConfig(),
    )
    result = await server.call_tool("jira_get_user_profile", {})

    assert installed is False
    assert len(server.middleware) == before
    assert result.structured_content == {"user": {"display_name": "Sensitive"}}


@pytest.mark.anyio
async def test_transforms_mapping_once_and_projects_both_channels() -> None:
    adapter = ReplacingAdapter()
    server = _server_with_adapter(adapter)

    @server.tool(name="jira_get_user_profile")
    async def profile() -> dict[str, Any]:
        return {"user": {"display_name": "Sensitive"}}

    result = await server.call_tool("jira_get_user_profile", {})

    assert adapter.calls == 1
    assert result.structured_content == {"user": {"display_name": "Protected"}}
    assert json.loads(result.content[0].text) == result.structured_content


@pytest.mark.anyio
async def test_transforms_json_string_once_and_rewraps_structured_content() -> None:
    adapter = ReplacingAdapter()
    server = _server_with_adapter(adapter)

    @server.tool(name="jira_get_issue")
    async def issue() -> str:
        return json.dumps({"user": {"displayName": "Sensitive"}})

    result = await server.call_tool("jira_get_issue", {})

    assert adapter.calls == 1
    assert result.structured_content is not None
    transformed = json.loads(result.structured_content["result"])
    assert transformed == {"user": {"displayName": "Protected"}}
    assert json.loads(result.content[0].text) == transformed


@pytest.mark.anyio
async def test_registered_raw_tool_passes_through_unchanged() -> None:
    server = _server_with_adapter(None)

    @server.tool(name="bitbucket_get_file_content")
    async def file_content() -> str:
        return "Sensitive raw text"

    result = await server.call_tool("bitbucket_get_file_content", {})

    assert result.content[0].text == "Sensitive raw text"


@pytest.mark.anyio
async def test_bitbucket_opaque_text_json_string_is_never_parsed() -> None:
    adapter = ReplacingAdapter()
    server = _server_with_service_adapter(ToolService.BITBUCKET, adapter)
    opaque_json = '{"display_name":"CANARY SOURCE CONTENT"}'

    @server.tool(name="bitbucket_get_pull_request_diff")
    async def diff() -> str:
        return opaque_json

    result = await server.call_tool("bitbucket_get_pull_request_diff", {})

    assert adapter.calls == 1
    assert result.content[0].text == opaque_json
    assert result.structured_content == {"result": opaque_json}


@pytest.mark.anyio
async def test_raw_tool_can_be_denied() -> None:
    server = _server_with_adapter(
        None,
        config=_enabled_config(raw_policy=UnstructuredContentPolicy.DENY),
    )

    @server.tool(name="bitbucket_get_file_content")
    async def file_content() -> str:
        return "Sensitive raw text"

    with pytest.raises(ToolError, match="blocks raw output"):
        await server.call_tool("bitbucket_get_file_content", {})


@pytest.mark.anyio
async def test_unknown_tool_fails_closed() -> None:
    server = _server_with_adapter(ReplacingAdapter())

    @server.tool(name="jira_unregistered_tool")
    async def unknown() -> dict[str, str]:
        return {"display_name": "Sensitive"}

    with pytest.raises(ToolError, match="blocked tool"):
        await server.call_tool("jira_unregistered_tool", {})


@pytest.mark.anyio
async def test_missing_service_adapter_fails_closed() -> None:
    server = _server_with_adapter(None)

    @server.tool(name="jira_get_user_profile")
    async def profile() -> dict[str, str]:
        return {"display_name": "Sensitive"}

    with pytest.raises(ToolError, match="blocked tool"):
        await server.call_tool("jira_get_user_profile", {})


@pytest.mark.anyio
async def test_adapter_error_does_not_leak_sensitive_detail() -> None:
    adapter = ReplacingAdapter(fail_with="Sensitive Person")
    server = _server_with_adapter(adapter)

    @server.tool(name="jira_get_user_profile")
    async def profile() -> dict[str, str]:
        return {"display_name": "Sensitive Person"}

    with pytest.raises(ToolError) as exc_info:
        await server.call_tool("jira_get_user_profile", {})

    assert "Sensitive Person" not in str(exc_info.value)


@pytest.mark.anyio
async def test_invalid_adapter_output_shape_fails_closed() -> None:
    server = _server_with_adapter(InvalidTopLevelAdapter())

    @server.tool(name="jira_get_user_profile")
    async def profile() -> dict[str, str]:
        return {"display_name": "Sensitive Person"}

    with pytest.raises(ToolError, match="blocked tool"):
        await server.call_tool("jira_get_user_profile", {})


@pytest.mark.anyio
async def test_tool_error_reports_full_detail_in_message_and_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    server = _server_with_adapter(ReplacingAdapter())

    @server.tool(name="jira_get_user_profile")
    @handle_tool_errors
    async def profile() -> dict[str, str]:
        raise ValueError("CANARY-PERSON-123")

    with caplog.at_level(logging.ERROR), pytest.raises(ToolError) as exc_info:
        await server.call_tool("jira_get_user_profile", {})

    # Operator decision: errors are returned and logged completely so that
    # they stay diagnosable; log access is restricted to the operator.
    assert "failed while identity privacy was enabled" in str(exc_info.value)
    assert "CANARY-PERSON-123" in str(exc_info.value)
    assert "CANARY-PERSON-123" in caplog.text


@pytest.mark.anyio
async def test_failed_call_resets_request_local_current_identity() -> None:
    server = _server_with_adapter(ReplacingAdapter(mark_current=True))

    @server.tool(name="jira_get_user_profile")
    async def profile() -> dict[str, str]:
        record_current_identity(ToolService.JIRA, "self-login")
        raise ValueError("CANARY-PERSON-123")

    with pytest.raises(ToolError):
        await server.call_tool("jira_get_user_profile", {})

    assert CurrentIdentityResolver().resolve(ToolService.JIRA) is None


@pytest.mark.anyio
async def test_current_user_is_marked_in_stdio_style_call() -> None:
    adapter = ReplacingAdapter(mark_current=True)
    server = _server_with_adapter(adapter)

    @server.tool(name="jira_get_user_profile")
    async def profile() -> dict[str, Any]:
        record_current_identity(ToolService.JIRA, "self-login")
        return {
            "users": [
                {"name": "self-login", "display_name": "Sensitive Self"},
                {"name": "other", "display_name": "Sensitive Other"},
            ]
        }

    result = await server.call_tool("jira_get_user_profile", {})
    assert result.structured_content is not None
    users = result.structured_content["users"]

    assert users[0]["is_current_user"] is True
    assert users[0]["display_name"] == "You"
    assert "is_current_user" not in users[1]


@pytest.mark.anyio
async def test_self_identification_can_be_disabled() -> None:
    adapter = ReplacingAdapter(mark_current=True)
    server = _server_with_adapter(
        adapter,
        config=IdentityPrivacyConfig(
            mode=PrivacyMode.ANONYMIZE,
            self_identification_enabled=False,
        ),
    )

    @server.tool(name="jira_get_user_profile")
    async def profile() -> dict[str, str]:
        record_current_identity(ToolService.JIRA, "self-login")
        return {"name": "self-login", "display_name": "Sensitive Self"}

    result = await server.call_tool("jira_get_user_profile", {})
    assert result.structured_content is not None
    assert "is_current_user" not in result.structured_content


@pytest.mark.anyio
async def test_concurrent_calls_do_not_share_current_identity() -> None:
    adapter = ReplacingAdapter(mark_current=True)
    server = _server_with_adapter(adapter)

    @server.tool(name="jira_get_user_profile")
    async def profile(login: str) -> dict[str, Any]:
        record_current_identity(ToolService.JIRA, login)
        await asyncio.sleep(0)
        return {
            "users": [
                {"name": "alpha", "display_name": "Alpha"},
                {"name": "beta", "display_name": "Beta"},
            ]
        }

    alpha_result, beta_result = await asyncio.gather(
        server.call_tool("jira_get_user_profile", {"login": "alpha"}),
        server.call_tool("jira_get_user_profile", {"login": "beta"}),
    )

    assert alpha_result.structured_content is not None
    assert beta_result.structured_content is not None
    alpha_users = alpha_result.structured_content["users"]
    beta_users = beta_result.structured_content["users"]
    assert alpha_users[0]["is_current_user"] is True
    assert "is_current_user" not in alpha_users[1]
    assert "is_current_user" not in beta_users[0]
    assert beta_users[1]["is_current_user"] is True


def test_main_server_default_does_not_install_privacy_middleware() -> None:
    from mcp_atlassian_with_bitbucket_and_privacy.servers.main import main_mcp

    assert not any(
        isinstance(middleware, PrivacyFilterMiddleware)
        for middleware in main_mcp.middleware
    )
