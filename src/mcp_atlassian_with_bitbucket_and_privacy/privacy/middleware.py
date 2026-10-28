"""FastMCP final-response guard for structured identity privacy."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Literal, cast

import mcp.types as mt
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_request
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools import ToolResult
from pydantic import ValidationError

from .alias_roundtrip import (
    AliasResolutionError,
    AliasRoundtripRegistry,
    begin_alias_caller_scope,
    begin_alias_roundtrip_registry_scope,
    record_alias_caller,
    reset_alias_caller_scope,
    reset_alias_roundtrip_registry_scope,
)
from .config import IdentityPrivacyConfig
from .current_user import (
    CurrentIdentity,
    CurrentIdentityResolver,
    begin_current_identity_scope,
    reset_current_identity_scope,
)
from .registry import (
    ResponseCategory,
    ToolResponsePolicy,
    ToolService,
    UnknownToolResponsePolicyError,
    get_tool_response_policy,
)
from .runtime import (
    begin_identity_privacy_runtime,
    begin_mention_alias_resolver,
    reset_identity_privacy_runtime,
    reset_mention_alias_resolver,
)
from .transformer import (
    IdentityResponseTransformer,
    PrivacyTransformationError,
)
from .types import UnstructuredContentPolicy

logger = logging.getLogger(
    "mcp-atlassian-with-bitbucket-and-privacy.privacy.middleware"
)

_StructuredKind = Literal["dict", "wrap", "wrap_json_string"]


def _error_chain(exc: BaseException) -> list[BaseException]:
    """Return exc and its causes; FastMCP wraps tool errors in a ToolError."""
    chain: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and current not in chain:
        chain.append(current)
        current = current.__cause__
    return chain


def _error_hint(exc: Exception) -> str:
    """Return a short remedy for well-known failure classes, else an empty string."""
    chain = _error_chain(exc)
    if any(isinstance(item, ValidationError) for item in chain):
        return (
            "Hint: the tool arguments do not match its schema; pass only the "
            "parameters defined in the tool schema (tools/list)"
        )
    if any(isinstance(item, AliasResolutionError) for item in chain):
        return (
            "Hint: aliases are valid only for the same caller and day; "
            "read the object again in this session before writing"
        )
    return ""


@dataclass(frozen=True, slots=True)
class _CanonicalStructured:
    value: Any
    kind: _StructuredKind
    original_inner: str = ""

    @classmethod
    def from_value(
        cls,
        structured: dict[str, Any] | None,
        *,
        parse_json_string: bool = True,
    ) -> _CanonicalStructured | None:
        if structured is None:
            return None
        if set(structured) != {"result"}:
            return cls(value=structured, kind="dict")

        inner = structured["result"]
        if parse_json_string and isinstance(inner, str):
            parsed = _try_parse_json(inner)
            if isinstance(parsed, dict | list):
                return cls(
                    value=parsed,
                    kind="wrap_json_string",
                    original_inner=inner,
                )
        return cls(value=inner, kind="wrap")

    def repack(self, transformed: Any) -> dict[str, Any]:
        if self.kind == "dict":
            if not isinstance(transformed, dict):
                raise PrivacyTransformationError(
                    "Structured dictionary response changed its top-level type"
                )
            return transformed
        if self.kind == "wrap":
            return {"result": transformed}
        return {
            "result": _serialize_json(transformed),
        }


class PrivacyFilterMiddleware(Middleware):
    """Apply one fail-closed identity transformation to each protected result."""

    def __init__(
        self,
        *,
        config: IdentityPrivacyConfig,
        transformer: IdentityResponseTransformer,
        current_identity_resolver: CurrentIdentityResolver | None = None,
        alias_roundtrip_registry: AliasRoundtripRegistry | None = None,
    ) -> None:
        self._config = config
        self._transformer = transformer
        self._current_identity_resolver = (
            current_identity_resolver or CurrentIdentityResolver()
        )
        self._alias_roundtrip_registry = alias_roundtrip_registry

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        privacy_runtime = begin_identity_privacy_runtime()
        mention_resolver = begin_mention_alias_resolver(
            self._transformer.alias_for_login
        )
        identity_scope = begin_current_identity_scope()
        alias_caller_scope = begin_alias_caller_scope()
        alias_registry_scope = begin_alias_roundtrip_registry_scope(
            self._alias_roundtrip_registry
        )
        tool_name = context.message.name
        try:
            policy = get_tool_response_policy(tool_name)
            _record_request_alias_caller(policy.service)
            try:
                result = await call_next(context)
            except Exception as exc:  # noqa: BLE001 - outward boundary must redact
                # Log access is limited to the operator, so the complete error
                # is logged and returned to the client to keep it diagnosable.
                logger.error(
                    "Tool %s failed inside identity privacy runtime after %s: %s",
                    tool_name,
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                )
                message = (
                    f"Tool '{tool_name}' failed while identity privacy was enabled: "
                    f"{type(exc).__name__}: {exc}"
                )
                hint = _error_hint(exc)
                if hint:
                    message = f"{message}. {hint}"
                raise ToolError(message) from exc

            if policy.category is ResponseCategory.RAW:
                return self._handle_raw(tool_name, result)
            current_identity = (
                self._current_identity_resolver.resolve(policy.service)
                if self._config.self_identification_enabled
                else None
            )
            return self._filter_result(
                tool_name,
                policy,
                result,
                current_identity=current_identity,
            )
        except ToolError:
            raise
        except (
            PrivacyTransformationError,
            UnknownToolResponsePolicyError,
            TypeError,
            ValueError,
        ) as exc:
            logger.error(
                "Identity privacy blocked tool %s after %s",
                tool_name,
                type(exc).__name__,
            )
            message = f"Identity privacy filter blocked tool '{tool_name}'"
            raise ToolError(message) from exc
        except Exception as exc:  # noqa: BLE001 - security boundary must fail closed
            logger.error(
                "Identity privacy blocked tool %s after unexpected %s",
                tool_name,
                type(exc).__name__,
            )
            message = f"Identity privacy filter blocked tool '{tool_name}'"
            raise ToolError(message) from exc
        finally:
            reset_alias_roundtrip_registry_scope(alias_registry_scope)
            reset_alias_caller_scope(alias_caller_scope)
            reset_current_identity_scope(identity_scope)
            reset_mention_alias_resolver(mention_resolver)
            reset_identity_privacy_runtime(privacy_runtime)

    def _handle_raw(self, tool_name: str, result: ToolResult) -> ToolResult:
        if self._config.unstructured_content_policy is UnstructuredContentPolicy.ALLOW:
            return result
        message = f"Identity privacy policy blocks raw output from '{tool_name}'"
        raise ToolError(message)

    def _filter_result(
        self,
        tool_name: str,
        policy: ToolResponsePolicy,
        result: ToolResult,
        *,
        current_identity: CurrentIdentity | None,
    ) -> ToolResult:
        canonical = _CanonicalStructured.from_value(
            result.structured_content,
            parse_json_string=not policy.opaque_string_result,
        )
        if canonical is not None:
            transformed = self._transformer.transform(
                tool_name=tool_name,
                policy=policy,
                value=canonical.value,
                current_identity=current_identity,
            )
            new_structured = canonical.repack(transformed)
            new_content = _project_content(
                result.content,
                original=canonical.value,
                transformed=transformed,
            )
        else:
            original, text_index = _canonicalize_content(
                result.content,
                parse_json=not policy.opaque_string_result,
            )
            transformed = self._transformer.transform(
                tool_name=tool_name,
                policy=policy,
                value=original,
                current_identity=current_identity,
            )
            new_structured = None
            new_content = list(result.content)
            new_content[text_index] = cast(
                mt.ContentBlock,
                _replace_text_block(
                    cast(mt.TextContent, new_content[text_index]),
                    transformed,
                ),
            )

        return ToolResult(
            content=new_content,
            structured_content=new_structured,
            meta=result.meta,
            is_error=result.is_error,
        )


def install_identity_privacy(
    server: FastMCP[Any],
    *,
    config: IdentityPrivacyConfig | None = None,
    transformer: IdentityResponseTransformer | None = None,
    alias_roundtrip_registry: AliasRoundtripRegistry | None = None,
) -> bool:
    """Install the final-response guard when privacy mode is enabled.

    Args:
        server: FastMCP server receiving the middleware.
        config: Optional validated configuration. Defaults to environment.
        transformer: Optional service-adapter dispatcher.

    Returns:
        True when middleware was installed, otherwise False.
    """
    resolved_config = config or IdentityPrivacyConfig.from_env()
    if not resolved_config.enabled:
        return False
    resolved_alias_registry = (
        alias_roundtrip_registry
        if alias_roundtrip_registry is not None
        else (
            AliasRoundtripRegistry(resolved_config)
            if resolved_config.alias_roundtrip_enabled
            else None
        )
    )
    server.add_middleware(
        PrivacyFilterMiddleware(
            config=resolved_config,
            transformer=(
                transformer
                or IdentityResponseTransformer.from_config(
                    resolved_config,
                    alias_roundtrip_registry=resolved_alias_registry,
                )
            ),
            alias_roundtrip_registry=resolved_alias_registry,
        )
    )
    return True


def _record_request_alias_caller(service: ToolService) -> None:
    """Bind aliases to request credentials without retaining raw secrets."""
    try:
        request = get_http_request()
    except RuntimeError:
        return

    state = request.state
    service_headers = getattr(state, "atlassian_service_headers", {})
    header_names = {
        ToolService.JIRA: (
            "X-Atlassian-Jira-Personal-Token",
            "X-Atlassian-Jira-Url",
            "JIRA_URL",
        ),
        ToolService.CONFLUENCE: (
            "X-Atlassian-Confluence-Personal-Token",
            "X-Atlassian-Confluence-Url",
            "CONFLUENCE_URL",
        ),
        ToolService.BITBUCKET: (
            "X-Atlassian-Bitbucket-Personal-Token",
            "X-Atlassian-Bitbucket-Url",
            "BITBUCKET_URL",
        ),
    }
    token_header, url_header, url_env = header_names[service]
    instance = ""
    if isinstance(service_headers, dict):
        token = service_headers.get(token_header)
        instance = service_headers.get(url_header) or ""
        if isinstance(token, str) and token:
            record_alias_caller(
                service,
                instance or os.getenv(url_env, ""),
                token,
            )
            return

    auth_type = getattr(state, "user_atlassian_auth_type", None)
    if auth_type == "basic":
        record_alias_caller(
            service,
            os.getenv(url_env, ""),
            getattr(state, "user_atlassian_email", None),
            getattr(state, "user_atlassian_api_token", None),
        )
        return

    token = getattr(state, "user_atlassian_token", None)
    if isinstance(token, str) and token:
        tenant = getattr(state, "user_atlassian_cloud_id", None)
        record_alias_caller(
            service,
            str(tenant or instance or os.getenv(url_env, "")),
            token,
        )


def _canonicalize_content(
    blocks: list[mt.ContentBlock],
    *,
    parse_json: bool,
) -> tuple[Any, int]:
    text_indexes = [
        index for index, block in enumerate(blocks) if isinstance(block, mt.TextContent)
    ]
    if len(text_indexes) != 1:
        raise PrivacyTransformationError(
            "Protected response without structured content must have one text block"
        )
    index = text_indexes[0]
    text = cast(mt.TextContent, blocks[index]).text
    parsed = _try_parse_json(text) if parse_json else None
    return (parsed if parsed is not None else text), index


def _project_content(
    blocks: list[mt.ContentBlock],
    *,
    original: Any,
    transformed: Any,
) -> list[mt.ContentBlock]:
    projected: list[mt.ContentBlock] = []
    for block in blocks:
        if not isinstance(block, mt.TextContent):
            projected.append(block)
            continue

        replacement = _derive_text(
            original_text=block.text,
            original=original,
            transformed=transformed,
        )
        if replacement is None:
            raise PrivacyTransformationError(
                "Text content does not match the canonical structured response"
            )
        projected.append(block.model_copy(update={"text": replacement}))
    return projected


def _replace_text_block(
    block: mt.TextContent,
    transformed: Any,
) -> mt.TextContent:
    text = transformed if isinstance(transformed, str) else _serialize_json(transformed)
    return block.model_copy(update={"text": text})


def _derive_text(
    *,
    original_text: str,
    original: Any,
    transformed: Any,
) -> str | None:
    if isinstance(original, str) and original_text == original:
        return (
            transformed
            if isinstance(transformed, str)
            else _serialize_json(transformed)
        )
    parsed = _try_parse_json(original_text)
    if parsed == original:
        return _serialize_json(transformed)
    return None


def _try_parse_json(text: str) -> Any:
    stripped = text.strip()
    if not stripped or stripped[0] not in "[{":
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return None


def _serialize_json(value: Any) -> str:
    try:
        return json.dumps(value, indent=2, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise PrivacyTransformationError(
            "Protected response is not JSON serializable"
        ) from exc
