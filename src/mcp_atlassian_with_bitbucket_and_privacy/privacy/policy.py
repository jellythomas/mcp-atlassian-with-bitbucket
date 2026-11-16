"""Deployment-specific identity classification policy."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

_ALLOWED_POLICY_KEYS = frozenset(
    {
        "human_username_max_length",
        "expose_service_display_name_and_login",
        "internal_logins",
        "external_logins",
        "internal_login_patterns",
        "external_login_patterns",
        "jira_identity_text_rules",
    }
)
_ALLOWED_JIRA_TEXT_RULE_KEYS = frozenset(
    {
        "field_id",
        "field_name_pattern",
        "patterns",
    }
)
_JIRA_CUSTOM_FIELD_ID_RE = re.compile(r"^customfield_\d+$")


def normalize_login(login: str) -> str:
    """Normalize a login for exact comparison and cross-system correlation."""
    return login.strip().casefold()


def _parse_login_set(value: object, field_name: str) -> frozenset[str]:
    if value is None:
        return frozenset()
    if not isinstance(value, list):
        message = f"{field_name} must be a JSON array of strings"
        raise ValueError(message)

    result: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            message = f"{field_name} must contain only strings"
            raise ValueError(message)
        normalized = normalize_login(item)
        if not normalized:
            message = f"{field_name} must not contain blank logins"
            raise ValueError(message)
        result.add(normalized)
    return frozenset(result)


def _parse_patterns(value: object, field_name: str) -> tuple[re.Pattern[str], ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        message = f"{field_name} must be a JSON array of regex strings"
        raise ValueError(message)

    patterns: list[re.Pattern[str]] = []
    for item in value:
        if not isinstance(item, str) or not item:
            message = f"{field_name} must contain non-empty strings"
            raise ValueError(message)
        try:
            patterns.append(re.compile(item, re.IGNORECASE))
        except re.error as exc:
            message = f"{field_name} contains an invalid regex: {exc}"
            raise ValueError(message) from exc
    return tuple(patterns)


@dataclass(frozen=True, slots=True)
class JiraIdentityTextRule:
    """Regex rules for identities embedded in one configured Jira text field."""

    field_id: str | None = None
    field_name_pattern: re.Pattern[str] | None = field(
        default=None,
        repr=False,
    )
    identity_patterns: tuple[re.Pattern[str], ...] = field(
        default_factory=tuple,
        repr=False,
    )

    def matches_field_name(self, field_name: str | None) -> bool:
        """Return whether this name-selected rule matches a field name."""
        return (
            self.field_name_pattern is not None
            and field_name is not None
            and self.field_name_pattern.search(field_name) is not None
        )


def _compile_identity_pattern(raw: object, field_name: str) -> re.Pattern[str]:
    if not isinstance(raw, str) or not raw:
        message = f"{field_name} must contain non-empty regex strings"
        raise ValueError(message)
    try:
        pattern = re.compile(raw)
    except re.error as exc:
        message = f"{field_name} contains an invalid regex: {exc}"
        raise ValueError(message) from exc
    if "identity" not in pattern.groupindex:
        message = f"{field_name} regex must define a named 'identity' group"
        raise ValueError(message)
    return pattern


def _parse_jira_identity_text_rules(
    value: object,
) -> tuple[JiraIdentityTextRule, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError("jira_identity_text_rules must be a JSON array")

    rules: list[JiraIdentityTextRule] = []
    for index, item in enumerate(value):
        field_name = f"jira_identity_text_rules[{index}]"
        if not isinstance(item, dict):
            message = f"{field_name} must be a JSON object"
            raise ValueError(message)
        unknown_keys = set(item).difference(_ALLOWED_JIRA_TEXT_RULE_KEYS)
        if unknown_keys:
            joined = ", ".join(sorted(unknown_keys))
            message = f"{field_name} contains unknown fields: {joined}"
            raise ValueError(message)

        raw_field_id = item.get("field_id")
        raw_name_pattern = item.get("field_name_pattern")
        if (raw_field_id is None) == (raw_name_pattern is None):
            message = (
                f"{field_name} must define exactly one of field_id "
                "or field_name_pattern"
            )
            raise ValueError(message)

        field_id: str | None = None
        compiled_name_pattern: re.Pattern[str] | None = None
        if raw_field_id is not None:
            if (
                not isinstance(raw_field_id, str)
                or _JIRA_CUSTOM_FIELD_ID_RE.fullmatch(raw_field_id) is None
            ):
                message = f"{field_name}.field_id must match customfield_<number>"
                raise ValueError(message)
            field_id = raw_field_id
        else:
            if not isinstance(raw_name_pattern, str) or not raw_name_pattern:
                message = f"{field_name}.field_name_pattern must be a non-empty regex"
                raise ValueError(message)
            try:
                compiled_name_pattern = re.compile(
                    raw_name_pattern,
                    re.IGNORECASE,
                )
            except re.error as exc:
                message = f"{field_name}.field_name_pattern is invalid: {exc}"
                raise ValueError(message) from exc

        raw_patterns = item.get("patterns")
        if not isinstance(raw_patterns, list) or not raw_patterns:
            message = f"{field_name}.patterns must be a non-empty JSON array"
            raise ValueError(message)
        identity_patterns = tuple(
            _compile_identity_pattern(
                pattern,
                f"{field_name}.patterns",
            )
            for pattern in raw_patterns
        )
        rules.append(
            JiraIdentityTextRule(
                field_id=field_id,
                field_name_pattern=compiled_name_pattern,
                identity_patterns=identity_patterns,
            )
        )
    return tuple(rules)


@dataclass(frozen=True, slots=True)
class IdentityPolicy:
    """Private deployment rules layered on secure generic defaults."""

    human_username_max_length: int | None = None
    expose_service_display_name_and_login: bool = False
    internal_logins: frozenset[str] = field(
        default_factory=frozenset,
        repr=False,
    )
    external_logins: frozenset[str] = field(
        default_factory=frozenset,
        repr=False,
    )
    internal_login_patterns: tuple[re.Pattern[str], ...] = field(
        default_factory=tuple,
        repr=False,
    )
    external_login_patterns: tuple[re.Pattern[str], ...] = field(
        default_factory=tuple,
        repr=False,
    )
    jira_identity_text_rules: tuple[JiraIdentityTextRule, ...] = field(
        default_factory=tuple,
        repr=False,
    )

    def jira_text_patterns_for(
        self,
        field_id: str | None,
        field_name: str | None,
    ) -> tuple[re.Pattern[str], ...]:
        """Return ID-prioritized identity regexes for one Jira custom field."""
        id_patterns = tuple(
            pattern
            for rule in self.jira_identity_text_rules
            if rule.field_id == field_id
            for pattern in rule.identity_patterns
        )
        if id_patterns:
            return id_patterns
        return tuple(
            pattern
            for rule in self.jira_identity_text_rules
            if rule.field_id is None and rule.matches_field_name(field_name)
            for pattern in rule.identity_patterns
        )

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> IdentityPolicy:
        """Build and validate a policy from parsed JSON data.

        Args:
            data: Policy object parsed from JSON.

        Returns:
            A validated immutable policy.

        Raises:
            ValueError: If a field is unknown, malformed, or contradictory.
        """
        unknown_keys = set(data).difference(_ALLOWED_POLICY_KEYS)
        if unknown_keys:
            joined = ", ".join(sorted(unknown_keys))
            message = f"Identity policy contains unknown fields: {joined}"
            raise ValueError(message)

        max_length = data.get("human_username_max_length")
        if max_length is not None and (
            isinstance(max_length, bool)
            or not isinstance(max_length, int)
            or max_length < 1
        ):
            raise ValueError(
                "human_username_max_length must be a positive integer or null"
            )

        expose_service = data.get(
            "expose_service_display_name_and_login",
            False,
        )
        if not isinstance(expose_service, bool):
            raise ValueError("expose_service_display_name_and_login must be a boolean")

        internal_logins = _parse_login_set(
            data.get("internal_logins"),
            "internal_logins",
        )
        external_logins = _parse_login_set(
            data.get("external_logins"),
            "external_logins",
        )
        overlap = internal_logins.intersection(external_logins)
        if overlap:
            raise ValueError(
                "Identity policy assigns the same login to internal and external"
            )

        return cls(
            human_username_max_length=max_length,
            expose_service_display_name_and_login=expose_service,
            internal_logins=internal_logins,
            external_logins=external_logins,
            internal_login_patterns=_parse_patterns(
                data.get("internal_login_patterns"),
                "internal_login_patterns",
            ),
            external_login_patterns=_parse_patterns(
                data.get("external_login_patterns"),
                "external_login_patterns",
            ),
            jira_identity_text_rules=_parse_jira_identity_text_rules(
                data.get("jira_identity_text_rules")
            ),
        )
