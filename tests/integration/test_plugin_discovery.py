"""Plugin discovery against a real (unmocked) distribution on sys.path.

Builds a minimal installed-package layout (module + .dist-info with an
entry_points.txt) in a temp dir — importlib.metadata discovers it exactly
as it would a pip-installed plugin.
"""

from pathlib import Path

import pytest

from ai_orchestrator.providers import load_all
from ai_orchestrator.providers.registry import ProviderRegistry

PLUGIN_MODULE = '''
from ai_orchestrator.core.models import AgentRequest, AgentResult, Capabilities, Health
from ai_orchestrator.providers.base import ProviderAdapter
from ai_orchestrator.transport.base import Invocation, TransportResult


class ToyAdapter(ProviderAdapter):
    name = "toy"
    capabilities = Capabilities()

    def health_check(self, transport):
        return Health(ok=True)

    def build_invocation(self, request):
        return Invocation(argv=["toy"], stdin=request.prompt,
                          workdir=request.workdir, timeout_s=request.timeout_s)

    def parse(self, raw):
        return AgentResult(success=True, text=raw.stdout)


NOT_AN_ADAPTER = object()
'''


def install_toy_distribution(root: Path, entry_line: str) -> None:
    (root / "toyplug.py").write_text(PLUGIN_MODULE, encoding="utf-8")
    dist_info = root / "toyplug-0.1.dist-info"
    dist_info.mkdir()
    (dist_info / "METADATA").write_text("Metadata-Version: 2.1\nName: toyplug\nVersion: 0.1\n",
        encoding="utf-8")
    (dist_info / "entry_points.txt").write_text(
        f"[ai_orchestrator.providers]\n{entry_line}\n", encoding="utf-8")


def test_discovers_installed_plugin(tmp_path: Path, monkeypatch) -> None:
    install_toy_distribution(tmp_path, "toy = toyplug:ToyAdapter")
    monkeypatch.syspath_prepend(str(tmp_path))

    reg = ProviderRegistry()
    reg.discover_entry_points()

    assert "toy" in reg.names()
    adapter = reg.get("toy")(command="toy-bin")
    assert adapter.command == "toy-bin"


def test_broken_plugin_warns_and_is_skipped(tmp_path: Path, monkeypatch) -> None:
    install_toy_distribution(tmp_path, "bad = toyplug:NOT_AN_ADAPTER")
    monkeypatch.syspath_prepend(str(tmp_path))

    reg = ProviderRegistry()
    with pytest.warns(UserWarning, match="skipping broken provider plugin 'bad'"):
        reg.discover_entry_points()

    assert "bad" not in reg.names()


def test_load_all_registers_builtins() -> None:
    reg = load_all()
    for name in ("claude", "codex", "antigravity"):
        assert name in reg.names()
