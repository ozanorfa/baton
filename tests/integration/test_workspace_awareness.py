"""ADR-013 end-to-end: real pipeline prompts differ by workspace maturity."""

from pathlib import Path

from typer.testing import CliRunner

from ai_orchestrator.cli.app import app

FAKE_CLI = Path(__file__).parent / "fake_provider" / "fake_ai.py"
runner = CliRunner()

CONFIG = (
    "pipeline:\n  stages: [planner, coder]\n"
    "roles:\n  planner: {provider: fake}\n  coder: {provider: fake}\n"
    "providers:\n"
    f"  fake: {{command: {FAKE_CLI}, timeout_s: 30}}\n"
)


def project(tmp_path: Path, monkeypatch, *, established: bool) -> Path:
    proj = tmp_path / "proj"
    (proj / ".ai").mkdir(parents=True)
    (proj / ".ai" / "config.yaml").write_text(CONFIG)
    if established:
        (proj / "README.md").write_text("# RealApp\n\nAn app that is real.\n")
        (proj / "src").mkdir()
        for i in range(4):
            (proj / "src" / f"part{i}.py").write_text("pass\n")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(proj)
    return proj


def planner_prompt(proj: Path) -> str:
    run_dir = next((proj / ".ai" / "runs").iterdir())
    return (run_dir / "prompts" / "01-planner.md").read_text()


def test_established_project_prompts_carry_orientation(tmp_path, fake_registry, monkeypatch):
    proj = project(tmp_path, monkeypatch, established=True)
    assert runner.invoke(app, ["run", "add a thing"]).exit_code == 0
    prompt = planner_prompt(proj)
    assert "Workspace: established project" in prompt
    assert "`README.md` — RealApp" in prompt
    assert "An app that is real." in prompt  # excerpt
    assert "part0.py" in prompt  # file map
    assert "Read before you write" in prompt


def test_greenfield_prompts_propose_instead(tmp_path, fake_registry, monkeypatch):
    proj = project(tmp_path, monkeypatch, established=False)
    result = runner.invoke(app, ["run", "start a thing"])
    assert result.exit_code == 0
    prompt = planner_prompt(proj)
    assert "Workspace: new project" in prompt
    assert "propose" in prompt
    assert "File map" not in prompt and "README" not in prompt
    # non-git dir → the safety-net tip is shown (ADR-013)
    assert "not a git repository" in result.output
