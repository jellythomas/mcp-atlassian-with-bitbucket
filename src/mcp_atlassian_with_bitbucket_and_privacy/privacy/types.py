"""Domain types for structured identity privacy."""

from dataclasses import dataclass, field
from enum import Enum


class PrivacyMode(str, Enum):
    """Configured identity privacy behavior."""

    OFF = "off"
    ANONYMIZE = "anonymize"
    PSEUDONYMIZE = "pseudonymize"


class Affiliation(str, Enum):
    """Organizational affiliation of an identity."""

    INTERNAL = "internal"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


class ActorType(str, Enum):
    """Whether an identity represents a person or a service."""

    HUMAN = "human"
    SERVICE = "service"
    UNKNOWN = "unknown"


class CorrelationScope(str, Enum):
    """Scope in which a pseudonym may be correlated."""

    DEPLOYMENT = "deployment"
    CONNECTOR = "connector"
    INSTANCE = "instance"


class UnstructuredContentPolicy(str, Enum):
    """Policy for explicitly registered opaque tool content."""

    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class IdentityClass:
    """Two-axis classification retained after identity protection."""

    affiliation: Affiliation = Affiliation.UNKNOWN
    actor_type: ActorType = ActorType.UNKNOWN

    def to_dict(self) -> dict[str, str]:
        """Return the stable MCP output representation."""
        return {
            "affiliation": self.affiliation.value,
            "actor_type": self.actor_type.value,
        }


@dataclass(frozen=True, slots=True)
class IdentitySource:
    """Service-specific identity values used for safe canonicalization."""

    connector: str
    instance: str
    entity_kind: str = "user"
    login: str | None = field(default=None, repr=False)
    local_id: str | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class CanonicalIdentity:
    """Sensitive canonical input for a later pseudonymizer."""

    scope: CorrelationScope
    entity_kind: str
    subject_id: str = field(repr=False)
    connector: str | None = None
    instance: str | None = None

    def __post_init__(self) -> None:
        """Validate the context required by the selected scope."""
        if not self.subject_id:
            raise ValueError("Canonical identity subject_id must not be empty")
        if not self.entity_kind:
            raise ValueError("Canonical identity entity_kind must not be empty")
        if self.scope in {CorrelationScope.CONNECTOR, CorrelationScope.INSTANCE}:
            if not self.connector:
                raise ValueError(
                    "Connector-scoped canonical identity requires connector"
                )
        if self.scope is CorrelationScope.INSTANCE and not self.instance:
            raise ValueError("Instance-scoped canonical identity requires instance")
