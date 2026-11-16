"""Versioned pseudonym master-key domain types."""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PseudonymKeyVersion:
    """One named master secret in a pseudonym keyring."""

    key_id: str
    key: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class PseudonymKeyring:
    """Active master secret plus a bounded set of accepted predecessors."""

    active: PseudonymKeyVersion
    previous: tuple[PseudonymKeyVersion, ...] = field(
        default_factory=tuple,
        repr=False,
    )

    @property
    def versions(self) -> tuple[PseudonymKeyVersion, ...]:
        """Return active first, followed by accepted predecessor versions."""
        return (self.active, *self.previous)
