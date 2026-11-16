"""Classification of structured identities using private deployment policy."""

from __future__ import annotations

from .policy import IdentityPolicy, normalize_login
from .types import ActorType, Affiliation, IdentityClass


class IdentityClassifier:
    """Classify affiliation and actor type as independent dimensions."""

    def __init__(self, policy: IdentityPolicy) -> None:
        self._policy = policy

    def classify(self, login: str | None) -> IdentityClass:
        """Classify a login without exposing or guessing missing values.

        Args:
            login: Service-provided login name.

        Returns:
            The two-axis classification. Blank or missing logins remain unknown.
        """
        normalized = normalize_login(login or "")
        if not normalized:
            return IdentityClass()

        return IdentityClass(
            affiliation=self._classify_affiliation(normalized),
            actor_type=self._classify_actor_type(normalized),
        )

    def may_expose_service_display_name_and_login(
        self,
        identity_class: IdentityClass,
    ) -> bool:
        """Return whether the deployment permits the service clear-text exception."""
        return (
            self._policy.expose_service_display_name_and_login
            and identity_class.actor_type is ActorType.SERVICE
        )

    def _classify_affiliation(self, normalized_login: str) -> Affiliation:
        is_internal = normalized_login in self._policy.internal_logins or any(
            pattern.search(normalized_login)
            for pattern in self._policy.internal_login_patterns
        )
        is_external = normalized_login in self._policy.external_logins or any(
            pattern.search(normalized_login)
            for pattern in self._policy.external_login_patterns
        )
        if is_internal == is_external:
            return Affiliation.UNKNOWN
        return Affiliation.INTERNAL if is_internal else Affiliation.EXTERNAL

    def _classify_actor_type(self, normalized_login: str) -> ActorType:
        threshold = self._policy.human_username_max_length
        if threshold is None:
            return ActorType.UNKNOWN
        if len(normalized_login) <= threshold:
            return ActorType.HUMAN
        return ActorType.SERVICE
