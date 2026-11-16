"""Schema-aware protection of standard Jira identity fields."""

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
from .transformer import PrivacyTransformationError
from .types import ActorType, IdentityClass, IdentitySource, PrivacyMode

_DISPLAY_KEYS = frozenset({"display_name", "displayName"})
_EXPLICIT_LOGIN_KEYS = ("username", "userName", "login")
_LOGIN_KEYS = frozenset({*_EXPLICIT_LOGIN_KEYS, "name"})
_LOCAL_ID_KEYS = (
    "account_id",
    "accountId",
    "user_key",
    "userKey",
    "key",
    "id",
    "uuid",
    "slug",
)
_EMAIL_KEYS = frozenset({"email", "emailAddress"})
_URL_KEYS = frozenset(
    {
        "avatar_url",
        "avatarUrl",
        "avatarUrls",
        "profile_url",
        "profileUrl",
        "self",
    }
)
_USER_OBJECT_HINTS = (
    _DISPLAY_KEYS
    | _EMAIL_KEYS
    | frozenset(
        {
            "account_id",
            "accountId",
            "user_key",
            "userKey",
            "avatar_url",
            "avatarUrl",
            "avatarUrls",
        }
    )
)
_STANDARD_USER_FIELDS = frozenset(
    {
        "assignee",
        "reporter",
        "creator",
        "author",
        "user",
        "lead",
    }
)
_LOGIN_SCALAR_FIELDS = frozenset(
    {
        "on_behalf_user",
        "onBehalfUser",
        "raiseOnBehalfOf",
        "reviewer",
        "leadUserName",
        "realAssignee",
    }
)
_DISPLAY_SCALAR_FIELDS = frozenset(
    {
        "transitioned_by",
        "transitionedBy",
    }
)
_STANDARD_USER_LIST_FIELDS = frozenset(
    {
        "users",
        "watchers",
        "reviewers",
        "approved_by",
        "approvedBy",
        "participants",
        "request_participants",
        "requestParticipants",
        "approvers",
    }
)
_CHANGELOG_IDENTITY_FIELDS = frozenset(
    {
        "assignee",
        "reporter",
        "creator",
    }
)
_UNASSIGNED_LABELS = frozenset({"unassigned", "none"})
_CUSTOM_FIELD_SCHEMA_KEY = "_identity_schema"


class JiraIdentityAdapter:
    """Protect Jira user objects while preserving unrelated Jira structures."""

    def __init__(
        self,
        config: IdentityPrivacyConfig,
        *,
        instance: str | None = None,
        clock: Callable[[], datetime] | None = None,
        alias_roundtrip_registry: AliasRoundtripRegistry | None = None,
    ) -> None:
        self._config = config
        self._instance = instance or os.getenv("JIRA_URL") or "jira-default-instance"
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
        """Return a protected copy of standard Jira identity fields."""
        if policy.service is not ToolService.JIRA:
            raise ValueError("Jira adapter received a non-Jira policy")
        return self._walk(value, current_identity=current_identity)

    def _walk(
        self,
        value: Any,
        *,
        current_identity: CurrentIdentity | None,
        field_name: str | None = None,
    ) -> Any:
        if isinstance(value, dict):
            if self._is_custom_field_envelope(value, field_name):
                return self._transform_custom_field(
                    value,
                    field_name=field_name,
                    current_identity=current_identity,
                )
            if self._is_identity_changelog(value):
                return self._transform_changelog(
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
        if key in _STANDARD_USER_FIELDS and isinstance(value, str):
            return self._transform_scalar_identity(
                value,
                current_identity=current_identity,
                treat_as_login=key != "author",
            )
        if key in _LOGIN_SCALAR_FIELDS and isinstance(value, str):
            return self._transform_scalar_identity(
                value,
                current_identity=current_identity,
                treat_as_login=True,
            )
        if key in _DISPLAY_SCALAR_FIELDS and isinstance(value, str):
            return self._transform_scalar_identity(
                value,
                current_identity=current_identity,
                treat_as_login=False,
            )
        if key in _STANDARD_USER_LIST_FIELDS and isinstance(value, list):
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
    def _is_custom_field_envelope(
        value: dict[str, Any],
        field_name: str | None,
    ) -> bool:
        field_id = value.get("field_id")
        return "value" in value and (
            _CUSTOM_FIELD_SCHEMA_KEY in value
            or (isinstance(field_name, str) and field_name.startswith("customfield_"))
            or (isinstance(field_id, str) and field_id.startswith("customfield_"))
        )

    def _transform_custom_field(
        self,
        value: dict[str, Any],
        *,
        field_name: str | None,
        current_identity: CurrentIdentity | None,
    ) -> dict[str, Any]:
        result = dict(value)
        identity_schema = result.pop(_CUSTOM_FIELD_SCHEMA_KEY, None)
        field_id = self._custom_field_id(result, field_name)
        display_name = self._custom_field_name(result, field_name)
        raw_value = value.get("value")

        if identity_schema in {"user", "array:user"}:
            result["value"] = self._transform_custom_identity_value(
                raw_value,
                current_identity=current_identity,
            )
            return result

        transformed = self._walk(
            raw_value,
            current_identity=current_identity,
            field_name=None,
        )
        if isinstance(transformed, str):
            transformed = self._transform_configured_text(
                transformed,
                field_id=field_id,
                field_name=display_name,
                current_identity=current_identity,
            )
        result["value"] = transformed
        return result

    def _transform_custom_identity_value(
        self,
        value: Any,
        *,
        current_identity: CurrentIdentity | None,
    ) -> Any:
        if isinstance(value, dict):
            return self._transform_user(
                value,
                current_identity=current_identity,
            )
        if isinstance(value, str):
            return self._transform_scalar_identity(
                value,
                current_identity=current_identity,
                treat_as_login=True,
            )
        if isinstance(value, list):
            return [
                self._transform_custom_identity_value(
                    item,
                    current_identity=current_identity,
                )
                for item in value
            ]
        return value

    def _transform_configured_text(
        self,
        text: str,
        *,
        field_id: str | None,
        field_name: str | None,
        current_identity: CurrentIdentity | None,
    ) -> str:
        patterns = self._config.policy.jira_text_patterns_for(
            field_id,
            field_name,
        )
        replacements: list[tuple[int, int, str]] = []
        for pattern in patterns:
            for match in pattern.finditer(text):
                start, end = match.span("identity")
                if start == end:
                    raise PrivacyTransformationError(
                        "Jira identity text rule produced an empty match"
                    )
                raw_identity = match.group("identity")
                replacements.append(
                    (
                        start,
                        end,
                        self._transform_scalar_identity(
                            raw_identity,
                            current_identity=current_identity,
                            treat_as_login=True,
                        ),
                    )
                )

        replacements.sort(key=lambda item: (item[0], item[1]))
        previous_end = -1
        for start, end, _replacement in replacements:
            if start < previous_end:
                raise PrivacyTransformationError(
                    "Jira identity text rules produced overlapping matches"
                )
            previous_end = end

        transformed = text
        for start, end, replacement in reversed(replacements):
            transformed = transformed[:start] + replacement + transformed[end:]
        return transformed

    @staticmethod
    def _custom_field_id(
        value: dict[str, Any],
        field_name: str | None,
    ) -> str | None:
        explicit_id = value.get("field_id")
        if isinstance(explicit_id, str):
            return explicit_id
        if isinstance(field_name, str) and field_name.startswith("customfield_"):
            return field_name
        return None

    @staticmethod
    def _custom_field_name(
        value: dict[str, Any],
        field_name: str | None,
    ) -> str | None:
        explicit_name = value.get("name")
        if isinstance(explicit_name, str):
            return explicit_name
        if isinstance(field_name, str) and not field_name.startswith("customfield_"):
            return field_name
        return None

    @staticmethod
    def _is_identity_changelog(value: dict[str, Any]) -> bool:
        field = value.get("field")
        return (
            isinstance(field, str)
            and field.strip().casefold() in _CHANGELOG_IDENTITY_FIELDS
        )

    def _transform_changelog(
        self,
        value: dict[str, Any],
        *,
        current_identity: CurrentIdentity | None,
    ) -> dict[str, Any]:
        result = {
            key: self._walk(
                item,
                current_identity=current_identity,
                field_name=key,
            )
            for key, item in value.items()
        }
        variants = (
            (
                ("from_id", "from"),
                ("from_string", "fromString"),
            ),
            (
                ("to_id", "to"),
                ("to_string", "toString"),
            ),
        )
        for id_keys, display_keys in variants:
            raw_id = self._first_string(value, id_keys)
            raw_display = self._first_string(value, display_keys)
            if raw_id is None and raw_display is None:
                continue
            if current_identity is not None and current_identity.matches(
                raw_id,
                raw_display,
            ):
                protected = "You"
            else:
                protected = self._protected_identifier(
                    login=None,
                    local_id=raw_id or raw_display,
                    identity_class=IdentityClass(),
                )
            for key in (*id_keys, *display_keys):
                if key in result and result[key] is not None:
                    result[key] = protected
        return result

    @staticmethod
    def _first_string(
        value: dict[str, Any],
        keys: tuple[str, ...],
    ) -> str | None:
        for key in keys:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate
        return None

    def _should_transform_user(
        self,
        value: dict[str, Any],
        field_name: str | None,
    ) -> bool:
        if self._is_unassigned(value):
            return False
        if field_name in _STANDARD_USER_FIELDS:
            return bool(
                set(value).intersection(
                    _USER_OBJECT_HINTS | _LOGIN_KEYS | frozenset(_LOCAL_ID_KEYS)
                )
            )
        return bool(set(value).intersection(_USER_OBJECT_HINTS))

    def _is_unassigned(self, value: dict[str, Any]) -> bool:
        has_identifier = any(
            isinstance(value.get(key), str) and value[key].strip()
            for key in (*_EXPLICIT_LOGIN_KEYS, *_LOCAL_ID_KEYS, *_EMAIL_KEYS)
        )
        if has_identifier:
            return False
        display = next(
            (value[key] for key in _DISPLAY_KEYS if isinstance(value.get(key), str)),
            "",
        )
        return display.strip().casefold() in _UNASSIGNED_LABELS

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
        for key in result:
            if key in _LOCAL_ID_KEYS or key in _EMAIL_KEYS or key in _URL_KEYS:
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

    def _protected_identifier(
        self,
        *,
        login: str | None,
        local_id: str | None,
        identity_class: IdentityClass,
    ) -> str:
        anonymous = (
            "anon:jira:user:"
            f"{identity_class.affiliation.value}:"
            f"{identity_class.actor_type.value}"
        )
        if self._config.mode is PrivacyMode.ANONYMIZE:
            return anonymous

        canonical = self._resolver.resolve(
            IdentitySource(
                connector=ToolService.JIRA.value,
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
                    service=ToolService.JIRA,
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
    def _extract_login(value: dict[str, Any]) -> str | None:
        for key in _EXPLICIT_LOGIN_KEYS:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate

        has_cloud_account_id = any(
            isinstance(value.get(key), str) and value[key].strip()
            for key in ("account_id", "accountId")
        )
        candidate = value.get("name")
        if (
            not has_cloud_account_id
            and isinstance(candidate, str)
            and candidate.strip()
        ):
            return candidate
        return None

    @staticmethod
    def _extract_local_id(value: dict[str, Any]) -> str | None:
        for key in _LOCAL_ID_KEYS:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate
        return None
