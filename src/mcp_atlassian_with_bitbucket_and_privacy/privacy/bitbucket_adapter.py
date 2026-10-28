"""Schema-aware protection of structured Bitbucket identities."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import PurePosixPath, PureWindowsPath
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
_LOGIN_KEYS = ("username", "userName", "name", "nickname")
_LOCAL_ID_KEYS = (
    "uuid",
    "account_id",
    "accountId",
    "id",
    "slug",
    "key",
)
_EMAIL_KEYS = frozenset({"email", "emailAddress"})
_URL_KEYS = frozenset(
    {
        "links",
        "self",
        "avatar",
        "avatar_url",
        "avatarUrl",
        "html",
        "profile_url",
        "profileUrl",
    }
)
_USER_SIGNATURE_KEYS = (
    _DISPLAY_KEYS
    | _EMAIL_KEYS
    | frozenset(
        {
            "account_id",
            "accountId",
            "nickname",
            "avatarUrl",
        }
    )
)
_IDENTITY_FIELDS = frozenset(
    {
        "author",
        "committer",
        "owner",
        "creator",
        "actor",
        "user",
        "closed_by",
        "closedBy",
        "tagger",
        "reviewer",
    }
)
_IDENTITY_LIST_FIELDS = frozenset(
    {
        "reviewers",
        "participants",
        "approved_by",
        "approvedBy",
        "users",
        "members",
        "approvers",
        "default_reviewers",
        "defaultReviewers",
    }
)
_COMMIT_IDENTITY_FIELDS = frozenset({"author", "committer"})


class BitbucketIdentityAdapter:
    """Protect Cloud/DC user objects without touching repository content."""

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
            instance or os.getenv("BITBUCKET_URL") or "bitbucket-default-instance"
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
        """Return a protected copy of structured Bitbucket identities."""
        if policy.service is not ToolService.BITBUCKET:
            raise ValueError("Bitbucket adapter received a non-Bitbucket policy")
        return self._walk(value, current_identity=current_identity)

    def _walk(
        self,
        value: Any,
        *,
        current_identity: CurrentIdentity | None,
        field_name: str | None = None,
    ) -> Any:
        if isinstance(value, dict):
            if self._is_artifact_metadata(value):
                return self._transform_artifact_metadata(
                    value,
                    current_identity=current_identity,
                )
            if self._is_owned_resource(value):
                return self._transform_owned_resource(
                    value,
                    current_identity=current_identity,
                )
            if self._is_commit_identity_wrapper(value, field_name):
                return self._transform_commit_identity_wrapper(
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
        if key in _IDENTITY_FIELDS and isinstance(value, str):
            return self._transform_scalar_identity(
                value,
                current_identity=current_identity,
                treat_as_login=key not in _COMMIT_IDENTITY_FIELDS,
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
    def _is_artifact_metadata(value: dict[str, Any]) -> bool:
        return isinstance(value.get("file_path"), str)

    def _transform_artifact_metadata(
        self,
        value: dict[str, Any],
        *,
        current_identity: CurrentIdentity | None,
    ) -> dict[str, Any]:
        raw_path = value["file_path"]
        filename = self._path_name(raw_path)
        result = {
            key: self._walk(
                item,
                current_identity=current_identity,
                field_name=key,
            )
            for key, item in value.items()
            if key != "file_path"
        }
        result["file_path"] = None
        result.setdefault("file_name", filename)
        message = result.get("message")
        if isinstance(message, str):
            result["message"] = message.replace(
                raw_path,
                "<server-local-path-redacted>",
            )
        return result

    @staticmethod
    def _path_name(path: str) -> str:
        if "\\" in path or re.match(r"^[A-Za-z]:", path):
            return PureWindowsPath(path).name
        return PurePosixPath(path).name

    @staticmethod
    def _is_owned_resource(value: dict[str, Any]) -> bool:
        return isinstance(value.get("owner"), dict) and any(
            key in value for key in ("full_name", "fullName", "key", "links")
        )

    def _transform_owned_resource(
        self,
        value: dict[str, Any],
        *,
        current_identity: CurrentIdentity | None,
    ) -> dict[str, Any]:
        owner = value["owner"]
        raw_login = self._extract_login(owner)
        transformed_owner = self._transform_user(
            owner,
            current_identity=current_identity,
        )
        safe_login = self._safe_user_identifier(transformed_owner)
        result: dict[str, Any] = {}
        for key, item in value.items():
            if key == "owner":
                result[key] = transformed_owner
            elif raw_login and key in {"full_name", "fullName", "key", "links"}:
                result[key] = self._replace_identity_in_strings(
                    item,
                    raw_login,
                    safe_login,
                )
            else:
                result[key] = self._walk(
                    item,
                    current_identity=current_identity,
                    field_name=key,
                )
        return result

    @classmethod
    def _replace_identity_in_strings(
        cls,
        value: Any,
        raw_identity: str,
        safe_identity: str,
    ) -> Any:
        if isinstance(value, str):
            return value.replace(raw_identity, safe_identity)
        if isinstance(value, list):
            return [
                cls._replace_identity_in_strings(
                    item,
                    raw_identity,
                    safe_identity,
                )
                for item in value
            ]
        if isinstance(value, dict):
            return {
                key: cls._replace_identity_in_strings(
                    item,
                    raw_identity,
                    safe_identity,
                )
                for key, item in value.items()
            }
        return value

    @staticmethod
    def _is_commit_identity_wrapper(
        value: dict[str, Any],
        field_name: str | None,
    ) -> bool:
        return (
            field_name in _COMMIT_IDENTITY_FIELDS
            and "raw" in value
            and ("user" in value or not set(value).intersection(_DISPLAY_KEYS))
        )

    def _transform_commit_identity_wrapper(
        self,
        value: dict[str, Any],
        *,
        current_identity: CurrentIdentity | None,
    ) -> dict[str, Any]:
        result = dict(value)
        user = value.get("user")
        transformed_user: dict[str, Any] | None = None
        if isinstance(user, dict):
            transformed = self._transform_user(
                user,
                current_identity=current_identity,
            )
            transformed_user = transformed
            result["user"] = transformed

        raw = value.get("raw")
        if isinstance(raw, str):
            if transformed_user is not None:
                result["raw"] = self._safe_user_label(transformed_user)
            else:
                result["raw"] = self._transform_scalar_identity(
                    raw,
                    current_identity=current_identity,
                    treat_as_login=False,
                )
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
                key in _LOCAL_ID_KEYS or key in _EMAIL_KEYS or key in _URL_KEYS
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

    def _protected_identifier(
        self,
        *,
        login: str | None,
        local_id: str | None,
        identity_class: IdentityClass,
    ) -> str:
        anonymous = (
            "anon:bitbucket:user:"
            f"{identity_class.affiliation.value}:"
            f"{identity_class.actor_type.value}"
        )
        if self._config.mode is PrivacyMode.ANONYMIZE:
            return anonymous
        canonical = self._resolver.resolve(
            IdentitySource(
                connector=ToolService.BITBUCKET.value,
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
                    service=ToolService.BITBUCKET,
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
    def _safe_user_identifier(value: dict[str, Any]) -> str:
        for key in (*_LOGIN_KEYS, *_LOCAL_ID_KEYS, *_DISPLAY_KEYS):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate
        return "protected-identity"

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
