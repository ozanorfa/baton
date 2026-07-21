"""Provider adapters. `load_all()` is the one entry point the CLI uses."""


def load_all():
    """Register built-ins, discover plugins, return the populated registry."""
    from ai_orchestrator.providers import (  # noqa: F401 — importing registers built-ins
        antigravity,
        claude,
        codex,
        deterministic,
        opencode,
    )
    from ai_orchestrator.providers.registry import registry

    registry.discover_entry_points()
    return registry
