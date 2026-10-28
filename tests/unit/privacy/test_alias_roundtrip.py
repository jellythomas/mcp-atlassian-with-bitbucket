"""Tests for caller- and tenant-isolated identity alias resolution."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from mcp_atlassian_with_bitbucket_and_privacy.privacy import (
    AliasResolutionError,
    AliasRoundtripRegistry,
    IdentityPolicy,
    IdentityPrivacyConfig,
    IdentityResponseTransformer,
    JiraIdentityAdapter,
    PrivacyMode,
    ToolService,
    begin_alias_caller_scope,
    begin_alias_roundtrip_registry_scope,
    install_identity_privacy,
    record_alias_caller,
    record_current_identity,
    reset_alias_caller_scope,
    reset_alias_roundtrip_registry_scope,
    resolve_identity_alias,
)
from mcp_atlassian_with_bitbucket_and_privacy.privacy.bitbucket_adapter import (
    BitbucketIdentityAdapter,
)
from mcp_atlassian_with_bitbucket_and_privacy.privacy.middleware import (
    _record_request_alias_caller,
)
from mcp_atlassian_with_bitbucket_and_privacy.privacy.registry import (
    ResponseCategory,
    ToolResponsePolicy,
)
from mcp_atlassian_with_bitbucket_and_privacy.servers.bitbucket import (
    _resolve_bitbucket_reviewers,
)
from mcp_atlassian_with_bitbucket_and_privacy.servers.jira import (
    _resolve_jira_identity_input,
)


class MutableClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current


def _config(*, enabled: bool = True) -> IdentityPrivacyConfig:
    return IdentityPrivacyConfig(
        mode=PrivacyMode.PSEUDONYMIZE,
        policy=IdentityPolicy(human_username_max_length=8),
        pseudonym_key=b"k" * 32,
        correlation_domain="test-deployment",
        rotation_hours=24,
        alias_roundtrip_enabled=enabled,
    )


def _register(
    registry: AliasRoundtripRegistry,
    *,
    service: ToolService = ToolService.JIRA,
    instance: str = "https://jira.example",
    token: str = "caller-token",
    alias: str = "pid:v1:test-alias",
    login: str | None = "target-user",
    local_id: str | None = "target-id",
) -> None:
    caller_scope = begin_alias_caller_scope()
    try:
        record_alias_caller(service, instance, token)
        registry.register(
            service=service,
            instance=instance,
            alias=alias,
            login=login,
            local_id=local_id,
        )
    finally:
        reset_alias_caller_scope(caller_scope)


def _resolve(
    registry: AliasRoundtripRegistry,
    *,
    service: ToolService = ToolService.JIRA,
    instance: str = "https://jira.example",
    token: str = "caller-token",
    alias: str = "pid:v1:test-alias",
    prefer_local_id: bool = False,
) -> str:
    registry_scope = begin_alias_roundtrip_registry_scope(registry)
    caller_scope = begin_alias_caller_scope()
    try:
        record_alias_caller(service, instance, token)
        return resolve_identity_alias(
            alias,
            service=service,
            instance=instance,
            prefer_local_id=prefer_local_id,
        )
    finally:
        reset_alias_caller_scope(caller_scope)
        reset_alias_roundtrip_registry_scope(registry_scope)


def test_same_caller_and_tenant_resolve_login_or_local_id() -> None:
    registry = AliasRoundtripRegistry(_config())
    _register(registry)

    assert _resolve(registry) == "target-user"
    assert _resolve(registry, prefer_local_id=True) == "target-id"


@pytest.mark.parametrize(
    ("token", "instance"),
    [
        ("foreign-token", "https://jira.example"),
        ("caller-token", "https://other-jira.example"),
    ],
)
def test_foreign_caller_or_tenant_is_rejected(token: str, instance: str) -> None:
    registry = AliasRoundtripRegistry(_config())
    _register(registry)

    with pytest.raises(AliasResolutionError, match="unauthorized"):
        _resolve(registry, token=token, instance=instance)


def test_unknown_alias_is_rejected() -> None:
    registry = AliasRoundtripRegistry(_config())

    with pytest.raises(AliasResolutionError, match="unknown"):
        _resolve(registry, alias="pid:v1:unknown")


def test_http_header_credentials_bind_alias_without_exposing_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = SimpleNamespace(
        atlassian_service_headers={
            "X-Atlassian-Jira-Personal-Token": "caller-token",
            "X-Atlassian-Jira-Url": "https://jira.example",
        }
    )
    monkeypatch.setattr(
        "mcp_atlassian_with_bitbucket_and_privacy.privacy.middleware.get_http_request",
        lambda: SimpleNamespace(state=state),
    )
    registry = AliasRoundtripRegistry(_config())

    caller_scope = begin_alias_caller_scope()
    try:
        _record_request_alias_caller(ToolService.JIRA)
        registry.register(
            service=ToolService.JIRA,
            instance="https://ignored.example",
            alias="pid:v1:http-alias",
            login="target-user",
            local_id="target-id",
        )
    finally:
        reset_alias_caller_scope(caller_scope)

    caller_scope = begin_alias_caller_scope()
    try:
        _record_request_alias_caller(ToolService.JIRA)
        assert (
            registry.resolve(
                service=ToolService.JIRA,
                instance="https://ignored.example",
                alias="pid:v1:http-alias",
                prefer_local_id=False,
            )
            == "target-user"
        )
    finally:
        reset_alias_caller_scope(caller_scope)

    state.atlassian_service_headers["X-Atlassian-Jira-Personal-Token"] = "foreign-token"
    caller_scope = begin_alias_caller_scope()
    try:
        _record_request_alias_caller(ToolService.JIRA)
        with pytest.raises(AliasResolutionError, match="unauthorized"):
            registry.resolve(
                service=ToolService.JIRA,
                instance="https://ignored.example",
                alias="pid:v1:http-alias",
                prefer_local_id=False,
            )
    finally:
        reset_alias_caller_scope(caller_scope)


def test_alias_expires_exactly_at_rotation_boundary() -> None:
    boundary = datetime(2026, 10, 6, tzinfo=timezone.utc)
    clock = MutableClock(boundary - timedelta(microseconds=1))
    registry = AliasRoundtripRegistry(_config(), clock=clock)
    _register(registry)

    assert _resolve(registry) == "target-user"
    clock.current = boundary
    with pytest.raises(AliasResolutionError, match="expired"):
        _resolve(registry)


def test_disabled_registry_leaves_values_unchanged() -> None:
    registry = AliasRoundtripRegistry(_config(enabled=False))
    registry_scope = begin_alias_roundtrip_registry_scope(registry)
    try:
        assert (
            resolve_identity_alias(
                "pid:v1:unknown",
                service=ToolService.JIRA,
                instance="https://jira.example",
                prefer_local_id=False,
            )
            == "pid:v1:unknown"
        )
    finally:
        reset_alias_roundtrip_registry_scope(registry_scope)


def test_concurrent_registry_scopes_do_not_cross_resolve() -> None:
    async def worker(target: str) -> str:
        registry = AliasRoundtripRegistry(_config())
        registry_scope = begin_alias_roundtrip_registry_scope(registry)
        caller_scope = begin_alias_caller_scope()
        try:
            record_alias_caller(
                ToolService.JIRA,
                "https://jira.example",
                "same-caller",
            )
            registry.register(
                service=ToolService.JIRA,
                instance="https://jira.example",
                alias="pid:v1:same-alias",
                login=target,
                local_id=None,
            )
            await asyncio.sleep(0)
            return resolve_identity_alias(
                "pid:v1:same-alias",
                service=ToolService.JIRA,
                instance="https://jira.example",
                prefer_local_id=False,
            )
        finally:
            reset_alias_caller_scope(caller_scope)
            reset_alias_roundtrip_registry_scope(registry_scope)

    async def run() -> tuple[str, str]:
        first, second = await asyncio.gather(
            worker("target-one"),
            worker("target-two"),
        )
        return first, second

    assert asyncio.run(run()) == ("target-one", "target-two")


@pytest.mark.anyio
async def test_roundtrip_across_tool_calls_and_foreign_caller_block() -> None:
    config = _config()
    registry = AliasRoundtripRegistry(config)
    adapter = JiraIdentityAdapter(
        config,
        instance="https://jira.example",
        alias_roundtrip_registry=registry,
    )
    server = FastMCP("alias-roundtrip")
    install_identity_privacy(
        server,
        config=config,
        transformer=IdentityResponseTransformer({ToolService.JIRA: adapter}),
        alias_roundtrip_registry=registry,
    )
    captured: dict[str, Any] = {}

    @server.tool(name="jira_get_user_profile")
    async def read_user(caller: str) -> dict[str, Any]:
        record_current_identity(ToolService.JIRA, caller)
        return {
            "user": {
                "name": "target01",
                "displayName": "Target User",
                "key": "TARGET-ID",
            }
        }

    @server.tool(name="jira_assign_issue")
    async def assign(alias: str, caller: str) -> dict[str, bool]:
        record_current_identity(ToolService.JIRA, caller)
        captured["resolved"] = resolve_identity_alias(
            alias,
            service=ToolService.JIRA,
            instance="https://jira.example",
            prefer_local_id=False,
        )
        return {"success": True}

    read_result = await server.call_tool(
        "jira_get_user_profile",
        {"caller": "caller01"},
    )
    assert read_result.structured_content is not None
    alias = read_result.structured_content["user"]["name"]

    await server.call_tool(
        "jira_assign_issue",
        {"alias": alias, "caller": "caller01"},
    )
    assert captured["resolved"] == "target01"

    with pytest.raises(
        ToolError,
        match=(
            "failed while identity privacy was enabled: "
            ".*unknown, expired, or unauthorized.*Hint: aliases"
        ),
    ):
        await server.call_tool(
            "jira_assign_issue",
            {"alias": alias, "caller": "foreign"},
        )

    with pytest.raises(
        ToolError,
        match="(?s)ValidationError: .*page_id.*Hint: the tool arguments do not match",
    ):
        await server.call_tool(
            "jira_assign_issue",
            {"alias": alias, "caller": "caller01", "page_id": "1"},
        )


def test_jira_and_bitbucket_write_helpers_resolve_aliases() -> None:
    jira_registry = AliasRoundtripRegistry(_config())
    _register(jira_registry)
    registry_scope = begin_alias_roundtrip_registry_scope(jira_registry)
    caller_scope = begin_alias_caller_scope()
    try:
        record_alias_caller(
            ToolService.JIRA,
            "https://jira.example",
            "caller-token",
        )
        jira = SimpleNamespace(
            config=SimpleNamespace(
                is_cloud=True,
                url="https://jira.example",
            )
        )
        assert _resolve_jira_identity_input("plain-user", jira) == "plain-user"
        assert _resolve_jira_identity_input(
            {"accountId": "pid:v1:test-alias"},
            jira,
        ) == {"accountId": "target-id"}
    finally:
        reset_alias_caller_scope(caller_scope)
        reset_alias_roundtrip_registry_scope(registry_scope)


def test_bitbucket_cloud_adapter_registers_uuid_for_reviewer_write() -> None:
    config = _config()
    registry = AliasRoundtripRegistry(config)
    adapter = BitbucketIdentityAdapter(
        config,
        instance="https://bitbucket.example",
        alias_roundtrip_registry=registry,
    )
    registry_scope = begin_alias_roundtrip_registry_scope(registry)
    caller_scope = begin_alias_caller_scope()
    try:
        record_alias_caller(
            ToolService.BITBUCKET,
            "https://bitbucket.example",
            "caller-token",
        )
        protected = adapter.transform(
            tool_name="bitbucket_get_pull_request",
            policy=ToolResponsePolicy(
                service=ToolService.BITBUCKET,
                category=ResponseCategory.STRUCTURED,
            ),
            value={
                "nickname": "target01",
                "uuid": "{target-uuid}",
                "account_id": "target-account",
                "display_name": "Target User",
            },
            current_identity=None,
        )
        client = SimpleNamespace(
            config=SimpleNamespace(
                is_cloud=True,
                url="https://bitbucket.example",
            )
        )
        assert _resolve_bitbucket_reviewers(protected["nickname"], client) == [
            "{target-uuid}"
        ]
    finally:
        reset_alias_caller_scope(caller_scope)
        reset_alias_roundtrip_registry_scope(registry_scope)


def test_bitbucket_write_helper_preserves_plain_and_resolves_alias() -> None:
    bitbucket_registry = AliasRoundtripRegistry(_config())
    _register(
        bitbucket_registry,
        service=ToolService.BITBUCKET,
        instance="https://bitbucket.example",
    )
    registry_scope = begin_alias_roundtrip_registry_scope(bitbucket_registry)
    caller_scope = begin_alias_caller_scope()
    try:
        record_alias_caller(
            ToolService.BITBUCKET,
            "https://bitbucket.example",
            "caller-token",
        )
        client = SimpleNamespace(
            config=SimpleNamespace(
                is_cloud=False,
                url="https://bitbucket.example",
            )
        )
        assert _resolve_bitbucket_reviewers(
            "plain-user,pid:v1:test-alias",
            client,
        ) == ["plain-user", "target-user"]
    finally:
        reset_alias_caller_scope(caller_scope)
        reset_alias_roundtrip_registry_scope(registry_scope)
