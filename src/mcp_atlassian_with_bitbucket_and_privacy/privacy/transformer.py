"""Service-adapter dispatch for identity response transformations."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from types import MappingProxyType
from typing import Any, Protocol

from .alias_roundtrip import AliasRoundtripRegistry
from .config import IdentityPrivacyConfig
from .current_user import CurrentIdentity
from .registry import ToolResponsePolicy, ToolService


class PrivacyTransformationError(RuntimeError):
    """Raised when a protected response cannot be transformed safely."""


class IdentityResponseAdapter(Protocol):
    """Contract implemented by Jira, Confluence, and Bitbucket adapters."""

    def transform(
        self,
        *,
        tool_name: str,
        policy: ToolResponsePolicy,
        value: Any,
        current_identity: CurrentIdentity | None,
    ) -> Any:
        """Return a protected copy of one canonical tool response."""
        ...


class IdentityResponseTransformer:
    """Dispatch canonical responses to explicitly registered service adapters."""

    def __init__(
        self,
        adapters: Mapping[ToolService, IdentityResponseAdapter] | None = None,
    ) -> None:
        self._adapters = MappingProxyType(dict(adapters or {}))

    @classmethod
    def from_config(
        cls,
        config: IdentityPrivacyConfig,
        *,
        clock: Callable[[], datetime] | None = None,
        alias_roundtrip_registry: AliasRoundtripRegistry | None = None,
    ) -> IdentityResponseTransformer:
        """Build the adapters currently available in the privacy MVP."""
        from .bitbucket_adapter import BitbucketIdentityAdapter
        from .confluence_adapter import ConfluenceIdentityAdapter
        from .jira_adapter import JiraIdentityAdapter

        return cls(
            {
                ToolService.JIRA: JiraIdentityAdapter(
                    config,
                    clock=clock,
                    alias_roundtrip_registry=alias_roundtrip_registry,
                ),
                ToolService.BITBUCKET: BitbucketIdentityAdapter(
                    config,
                    clock=clock,
                    alias_roundtrip_registry=alias_roundtrip_registry,
                ),
                ToolService.CONFLUENCE: ConfluenceIdentityAdapter(
                    config,
                    clock=clock,
                    alias_roundtrip_registry=alias_roundtrip_registry,
                ),
            }
        )

    def alias_for_login(self, login: str) -> str | None:
        """Return the Confluence alias for a login used in page mentions."""
        from .confluence_adapter import ConfluenceIdentityAdapter

        adapter = self._adapters.get(ToolService.CONFLUENCE)
        if not isinstance(adapter, ConfluenceIdentityAdapter):
            return None
        return adapter.alias_for_login(login)

    def transform(
        self,
        *,
        tool_name: str,
        policy: ToolResponsePolicy,
        value: Any,
        current_identity: CurrentIdentity | None = None,
    ) -> Any:
        """Transform a response or fail closed when no adapter is available."""
        adapter = self._adapters.get(policy.service)
        if adapter is None:
            message = (
                "No identity privacy adapter registered for service: "
                f"{policy.service.value}"
            )
            raise PrivacyTransformationError(message)
        return adapter.transform(
            tool_name=tool_name,
            policy=policy,
            value=value,
            current_identity=current_identity,
        )
