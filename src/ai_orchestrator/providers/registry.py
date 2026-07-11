"""Provider registry: built-in registration + entry-point plugin discovery (ADR-009)."""

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


registry = ProviderRegistry()
