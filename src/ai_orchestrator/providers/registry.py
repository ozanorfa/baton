"""Provider registry: built-in registration + entry-point plugin discovery (ADR-009)."""

import warnings
from importlib.metadata import entry_points

from ai_orchestrator.providers.base import ProviderAdapter

ENTRY_POINT_GROUP = "ai_orchestrator.providers"


class UnknownProviderError(Exception):
    pass


class ProviderRegistry:
    def __init__(self) -> None:
        self._classes: dict[str, type[ProviderAdapter]] = {}

    def register(self, cls: type[ProviderAdapter]) -> type[ProviderAdapter]:
        """Usable as a decorator on adapter classes."""
        self._classes[cls.name] = cls
        return cls

    def get(self, name: str) -> type[ProviderAdapter]:
        try:
            return self._classes[name]
        except KeyError:
            raise UnknownProviderError(
                f"unknown provider {name!r}; registered providers: {self.names() or ['(none)']}"
            ) from None

    def names(self) -> list[str]:
        return sorted(self._classes)

    def discover_entry_points(self) -> None:
        """Load third-party adapters. A broken plugin warns and is skipped —
        it must never take the orchestrator down (ADR-009)."""
        for ep in entry_points(group=ENTRY_POINT_GROUP):
            try:
                cls = ep.load()
                if not (isinstance(cls, type) and issubclass(cls, ProviderAdapter)):
                    raise TypeError(f"{ep.value} is not a ProviderAdapter subclass")
                self.register(cls)
            except Exception as exc:  # noqa: BLE001 — isolation is the point
                warnings.warn(
                    f"skipping broken provider plugin {ep.name!r} ({ep.value}): {exc}",
                    stacklevel=2,
                )


registry = ProviderRegistry()
