"""Config loading & merging (ARCHITECTURE.md §4).

Precedence, highest wins:

    CLI overrides > env (AI_ORCH_*) > project .ai/config.yaml
        > user ~/.config/batonai/config.yaml > built-in defaults

Every leaf value remembers which layer set it (`LoadedConfig.sources`), which
powers `batonai config show` and lets validation errors name the offending file.

Env var mapping: `AI_ORCH_` prefix, `__` for nesting, values YAML-parsed.
Example: AI_ORCH_PROVIDERS__CLAUDE__TIMEOUT_S=300 → providers.claude.timeout_s.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path

import yaml
from pydantic import ValidationError

from ai_orchestrator.config.schema import AppConfig, warn_unknown_keys

ENV_PREFIX = "AI_ORCH_"


class ConfigError(Exception):
    """Invalid configuration; message names the offending key and its source."""


@dataclass
class LoadedConfig:
    config: AppConfig
    sources: dict[str, str] = field(default_factory=dict)  # dotted leaf path -> source label
    files_read: list[Path] = field(default_factory=list)

    def source_of(self, dotted_path: str) -> str:
        return self.sources.get(dotted_path, "defaults")


LEGACY_USER_CONFIG_DIR = "ai-orchestrator"  # the pre-0.1.0 distribution name


def user_config_path() -> Path:
    """`~/.config/batonai/config.yaml` (XDG-aware).

    A config written under the old distribution name is still honoured when no
    new-style file exists, so a pre-release install keeps working after the
    rename; the new path wins as soon as it is created.
    """
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    preferred = root / "batonai" / "config.yaml"
    legacy = root / LEGACY_USER_CONFIG_DIR / "config.yaml"
    if not preferred.is_file() and legacy.is_file():
        return legacy
    return preferred


def project_config_path(project_dir: Path) -> Path:
    return project_dir / ".ai" / "config.yaml"


def _deep_merge(base: dict, override: dict) -> dict:
    """Dicts merge recursively; scalars and lists replace."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _leaf_paths(data: dict, prefix: str = "") -> list[str]:
    paths: list[str] = []
    for key, value in data.items():
        dotted = f"{prefix}{key}"
        if isinstance(value, dict) and value:
            paths.extend(_leaf_paths(value, f"{dotted}."))
        else:
            paths.append(dotted)
    return paths


def _read_yaml(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        # Without this, a mistyped .ai/config.yaml escapes as a raw parser
        # traceback out of *every* command (found via the wizard's exit-2 test,
        # 2026-07-28) instead of the documented config error.
        raise ConfigError(f"{path}: not valid YAML — {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"{path}: could not be read — {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top level must be a mapping, got {type(data).__name__}")
    return data


def _env_layer(env: Mapping[str, str]) -> dict:
    layer: dict = {}
    for name, raw in env.items():
        if not name.startswith(ENV_PREFIX):
            continue
        segments = [s.lower() for s in name.removeprefix(ENV_PREFIX).split("__") if s]
        if not segments:
            continue
        node = layer
        for segment in segments[:-1]:
            node = node.setdefault(segment, {})
        node[segments[-1]] = yaml.safe_load(raw)
    return layer


def _overrides_layer(overrides: Mapping[str, object]) -> dict:
    layer: dict = {}
    for dotted, value in overrides.items():
        node = layer
        segments = dotted.split(".")
        for segment in segments[:-1]:
            node = node.setdefault(segment, {})
        node[segments[-1]] = value
    return layer


def load_config(
    project_dir: Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
    overrides: Mapping[str, object] | None = None,
    user_path: Path | None = None,
) -> LoadedConfig:
    project_dir = project_dir or Path.cwd()
    env = os.environ if env is None else env
    user_path = user_path or user_config_path()
    project_path = project_config_path(project_dir)

    defaults = yaml.safe_load((files("ai_orchestrator.config") / "defaults.yaml").read_text())

    layers: list[tuple[str, dict, Path | None]] = [("defaults", defaults, None)]
    if user_path.is_file():
        layers.append(("user", _read_yaml(user_path), user_path))
    if project_path.is_file():
        layers.append(("project", _read_yaml(project_path), project_path))
    env_layer = _env_layer(env)
    if env_layer:
        layers.append((f"env ({ENV_PREFIX}*)", env_layer, None))
    if overrides:
        layers.append(("cli", _overrides_layer(overrides), None))

    merged: dict = {}
    sources: dict[str, str] = {}
    files_read: list[Path] = []
    label_paths: dict[str, Path] = {}
    for label, layer, path in layers:
        merged = _deep_merge(merged, layer)
        for leaf in _leaf_paths(layer):
            sources[leaf] = label
        if path is not None:
            files_read.append(path)
            label_paths[label] = path

    try:
        config = AppConfig.model_validate(merged)
    except ValidationError as exc:
        lines = []
        for err in exc.errors():
            dotted = ".".join(str(part) for part in err["loc"])
            origin = sources.get(dotted, "merged config")
            if origin in label_paths:
                origin = f"{origin}: {label_paths[origin]}"
            lines.append(f"  {dotted}: {err['msg']} (set by {origin})")
        raise ConfigError("invalid configuration:\n" + "\n".join(lines)) from exc

    warn_unknown_keys(config, " + ".join(label for label, _, _ in layers))
    return LoadedConfig(config=config, sources=sources, files_read=files_read)
