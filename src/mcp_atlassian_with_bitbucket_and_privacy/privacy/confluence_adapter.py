"""Schema-aware protection of structured Confluence identities."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime
from typing import Any

from .alias_roundtrip import AliasRoundtripRegistry
from .classifier import IdentityClassifier
from .config import IdentityPrivacyConfig
from .current_user import CurrentIdentity
from .pseudonymizer import Pseudonymizer
from .registry import ToolResponsePolicy, ToolService
from .resolver import CanonicalIdentityResolver
from .types import ActorType, IdentityClass, IdentitySource, PrivacyMode

_DISPLAY_KEYS = frozenset({"display_name", "displayName"})
_LOGIN_KEYS = ("username", "name", "user_key", "userKey")
_LOCAL_ID_KEYS = ("account_id", "accountId", "key", "id", "uuid")
_EMAIL_KEYS = frozenset({"email", "emailAddress"})
_URL_KEYS = frozenset(
    {
        "profile_picture",
        "profilePicture",
        "profile_url",
        "profileUrl",
        "avatar",
        "links",
        "self",
        "url",
    }
)
_USER_SIGNATURE_KEYS = (
    _DISPLAY_KEYS
    | _EMAIL_KEYS
    | frozenset(
        {
            "account_id",
            "accountId",
            "user_key",
            "userKey",
            "profile_picture",
            "profilePicture",
        }
    )
)
_IDENTITY_FIELDS = frozenset(
    {
        "author",
        "by",
        "createdBy",
        "ownedBy",
        "user",
        "subject",
    }
)
_DISPLAY_SCALAR_FIELDS = frozenset(
    {
        "author",
        "version_author",
        "author_display_name",
    }
)
_IDENTITY_LIST_FIELDS = frozenset({"users", "members"})


class ConfluenceIdentityAdapter:
    """Protect Confluence identities without scanning content bodies."""

    def __init__(
        self,
        config: IdentityPrivacyConfig,
        *,
        instance: str | None = None,
        clock: Callable[[], datetime] | None = None,
        alias_roundtrip_registry: AliasRoundtripRegistry | None = None,
    ) -> None:
        self._config = config
        self._instance = (
            instance or os.getenv("CONFLUENCE_URL") or "confluence-default-instance"
        )
        self._classifier = IdentityClassifier(config.policy)
        self._resolver = CanonicalIdentityResolver(config.correlation_scope)
        self._alias_roundtrip_registry = alias_roundtrip_registry
        self._pseudonymizer = (
            Pseudonymizer.from_config(config, clock=clock)
            if config.mode is PrivacyMode.PSEUDONYMIZE
            else None
        )

    def transform(
        self,
        *,
        tool_name: str,
        policy: ToolResponsePolicy,
        value: Any,
        current_identity: CurrentIdentity | None,
    ) -> Any:
        """Return a protected copy of structured Confluence identities."""
        if policy.service is not ToolService.CONFLUENCE:
            raise ValueError("Confluence adapter received a non-Confluence policy")
        return self._walk(value, current_identity=current_identity)

    def _walk(
        self,
        value: Any,
        *,
        current_identity: CurrentIdentity | None,
        field_name: str | None = None,
    ) -> Any:
        if isinstance(value, dict):
            if self._is_user_search_wrapper(value):
                return self._transform_user_search(
                    value,
                    current_identity=current_identity,
                )
            if self._should_transform_user(value, field_name):
                return self._transform_user(
                    value,
                    current_identity=current_identity,
                )
            return {
                key: self._walk_field(
                    key,
                    item,
                    current_identity=current_identity,
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [
                self._walk(
                    item,
                    current_identity=current_identity,
                    field_name=field_name,
                )
                for item in value
            ]
        return value

    def _walk_field(
        self,
        key: str,
        value: Any,
        *,
        current_identity: CurrentIdentity | None,
    ) -> Any:
        if key in _DISPLAY_SCALAR_FIELDS and isinstance(value, str):
            return self._transform_scalar_identity(
                value,
                current_identity=current_identity,
                treat_as_login=False,
            )
        if key in _IDENTITY_LIST_FIELDS and isinstance(value, list):
            return [
                (
                    self._transform_scalar_identity(
                        item,
                        current_identity=current_identity,
                        treat_as_login=True,
                    )
                    if isinstance(item, str)
                    else self._walk(
                        item,
                        current_identity=current_identity,
                        field_name="user",
                    )
                )
                for item in value
            ]
        return self._walk(
            value,
            current_identity=current_identity,
            field_name=key,
        )

    @staticmethod
    def _is_user_search_wrapper(value: dict[str, Any]) -> bool:
        return value.get("entity_type") == "user" and isinstance(
            value.get("user"), dict
        )

    def _transform_user_search(
        self,
        value: dict[str, Any],
        *,
        current_identity: CurrentIdentity | None,
    ) -> dict[str, Any]:
        raw_user = value["user"]
        transformed_user = self._transform_user(
            raw_user,
            current_identity=current_identity,
        )
        result = {
            key: self._walk(
                item,
                current_identity=current_identity,
                field_name=key,
            )
            for key, item in value.items()
            if key not in {"user", "title", "url"}
        }
        result["user"] = transformed_user
        result["title"] = self._safe_user_label(transformed_user)
        if "url" in value:
            result["url"] = None
        return result

    def _should_transform_user(
        self,
        value: dict[str, Any],
        field_name: str | None,
    ) -> bool:
        if set(value).intersection(_USER_SIGNATURE_KEYS):
            return True
        if field_name not in _IDENTITY_FIELDS:
            return False
        return any(
            isinstance(value.get(key), str) and value[key].strip()
            for key in (*_LOGIN_KEYS, *_LOCAL_ID_KEYS)
        )

    def _transform_user(
        self,
        value: dict[str, Any],
        *,
        current_identity: CurrentIdentity | None,
    ) -> dict[str, Any]:
        login = self._extract_login(value)
        local_id = self._extract_local_id(value)
        identity_class = self._classifier.classify(login)
        is_current = current_identity is not None and current_identity.matches(
            login,
            local_id,
            *(value.get(key) for key in _EMAIL_KEYS),
        )
        if self._classifier.may_expose_service_display_name_and_login(identity_class):
            return self._service_user(
                value,
                identity_class=identity_class,
                is_current=is_current,
            )

        protected_identifier = self._protected_identifier(
            login=login,
            local_id=local_id,
            identity_class=identity_class,
        )
        label = (
            "You"
            if is_current
            else self._protected_display_label(
                identity_class,
                protected_identifier,
            )
        )
        result = dict(value)
        for key in result:
            if key in _LOGIN_KEYS or key in _LOCAL_ID_KEYS:
                result[key] = protected_identifier
            elif key in _DISPLAY_KEYS:
                result[key] = label
            elif key in _EMAIL_KEYS or key in _URL_KEYS:
                result[key] = None
        if not set(result).intersection(_DISPLAY_KEYS):
            result["display_name"] = label
        result["identity_class"] = identity_class.to_dict()
        if is_current:
            result["is_current_user"] = True
        return result

    def _service_user(
        self,
        value: dict[str, Any],
        *,
        identity_class: IdentityClass,
        is_current: bool,
    ) -> dict[str, Any]:
        result = dict(value)
        login_key = self._login_key(value)
        for key in result:
            if (
                key in _LOGIN_KEYS
                or key in _LOCAL_ID_KEYS
                or key in _EMAIL_KEYS
                or key in _URL_KEYS
            ) and key != login_key:
                result[key] = None
        result["identity_class"] = identity_class.to_dict()
        if is_current:
            result["is_current_user"] = True
            for key in _DISPLAY_KEYS:
                if key in result:
                    result[key] = "You"
        return result

    def _transform_scalar_identity(
        self,
        value: str,
        *,
        current_identity: CurrentIdentity | None,
        treat_as_login: bool,
    ) -> str:
        login = value if treat_as_login else None
        identity_class = self._classifier.classify(login)
        if (
            treat_as_login
            and self._classifier.may_expose_service_display_name_and_login(
                identity_class
            )
        ):
            return value
        if current_identity is not None and current_identity.matches(value):
            return "You"
        return self._protected_identifier(
            login=login,
            local_id=None if treat_as_login else value,
            identity_class=identity_class,
        )

    def alias_for_login(self, login: str) -> str | None:
        """Return the pseudonymous alias for a login, or None without a stable alias."""
        identity_class = self._classifier.classify(login)
        alias = self._protected_identifier(
            login=login,
            local_id=None,
            identity_class=identity_class,
        )
        return None if alias.startswith("anon:") else alias

    def _protected_identifier(
        self,
        *,
        login: str | None,
        local_id: str | None,
        identity_class: IdentityClass,
    ) -> str:
        anonymous = (
            "anon:confluence:user:"
            f"{identity_class.affiliation.value}:"
            f"{identity_class.actor_type.value}"
        )
        if self._config.mode is PrivacyMode.ANONYMIZE:
            return anonymous
        canonical = self._resolver.resolve(
            IdentitySource(
                connector=ToolService.CONFLUENCE.value,
                instance=self._instance,
                login=login,
                local_id=local_id,
            )
        )
        if canonical is None or self._pseudonymizer is None:
            return anonymous
        aliases = self._pseudonymizer.pseudonymize_candidates(canonical)
        alias = aliases[0]
        if self._alias_roundtrip_registry is not None:
            for candidate in aliases:
                self._alias_roundtrip_registry.register(
                    service=ToolService.CONFLUENCE,
                    instance=self._instance,
                    alias=candidate,
                    login=login,
                    local_id=local_id,
                )
        return alias

    @staticmethod
    def _protected_display_label(
        identity_class: IdentityClass,
        protected_identifier: str,
    ) -> str:
        affiliation = identity_class.affiliation.value.capitalize()
        actor = identity_class.actor_type.value
        if protected_identifier.startswith("pid:"):
            marker = {
                ActorType.HUMAN: "H",
                ActorType.SERVICE: "S",
                ActorType.UNKNOWN: "U",
            }[identity_class.actor_type]
            return f"{affiliation} {actor} {marker}-{protected_identifier[-6:].upper()}"
        return f"{affiliation} {actor}"

    @staticmethod
    def _safe_user_label(value: dict[str, Any]) -> str:
        for key in (*_DISPLAY_KEYS, *_LOGIN_KEYS, *_LOCAL_ID_KEYS):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate
        return "Protected identity"

    @staticmethod
    def _login_key(value: dict[str, Any]) -> str | None:
        for key in _LOGIN_KEYS:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return key
        return None

    @classmethod
    def _extract_login(cls, value: dict[str, Any]) -> str | None:
        key = cls._login_key(value)
        candidate = value.get(key) if key is not None else None
        return candidate if isinstance(candidate, str) else None

    @staticmethod
    def _extract_local_id(value: dict[str, Any]) -> str | None:
        for key in _LOCAL_ID_KEYS:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate
        return None
