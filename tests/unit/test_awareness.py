from pathlib import Path

from ai_orchestrator.context.awareness import (
    DOCS_INDEX_MAX,
    TREE_MAX_ENTRIES,
    WorkspaceMode,
    detect_mode,
    docs_index,
    repo_map,
    workspace_layer,
)


def make_established(root: Path) -> Path:
    (root / "lib").mkdir(parents=True)
    for i in range(4):
        (root / "lib" / f"mod{i}.dart").write_text(f"// module {i}\n")
    return root


def test_empty_dir_is_greenfield(tmp_path: Path) -> None:
    assert detect_mode(tmp_path) is WorkspaceMode.GREENFIELD


def test_docs_alone_stay_greenfield(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Just an idea\n")
    assert detect_mode(tmp_path) is WorkspaceMode.GREENFIELD


def test_source_files_make_established(tmp_path: Path) -> None:
    make_established(tmp_path)
    assert detect_mode(tmp_path) is WorkspaceMode.ESTABLISHED


def test_plain_html_site_is_established(tmp_path: Path) -> None:
    """Field bug (charm_website, 2026-07-12): HTML/CSS sites are real projects."""
    for name in ("index.html", "contact.html", "privacy.html"):
        (tmp_path / name).write_text("<html></html>")
    assert detect_mode(tmp_path) is WorkspaceMode.ESTABLISHED


def test_stack_marker_alone_makes_established(tmp_path: Path) -> None:
    (tmp_path / "pubspec.yaml").write_text("name: app\n")
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "main.dart").write_text("void main() {}\n")
    assert detect_mode(tmp_path) is WorkspaceMode.ESTABLISHED  # < threshold, but scaffolded


def test_claude_md_is_indexed_as_doc(tmp_path: Path) -> None:
    make_established(tmp_path)
    (tmp_path / "CLAUDE.md").write_text("# Conventions for AI\nUse Riverpod.\n")
    layer = workspace_layer(tmp_path)
    assert "`CLAUDE.md` — Conventions for AI" in layer


def test_noise_dirs_do_not_count(tmp_path: Path) -> None:
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    for i in range(10):
        (tmp_path / "node_modules" / "pkg" / f"x{i}.js").write_text("junk")
    (tmp_path / ".ai").mkdir()
    assert detect_mode(tmp_path) is WorkspaceMode.GREENFIELD


def test_greenfield_layer_proposes_instead_of_reading(tmp_path: Path) -> None:
    layer = workspace_layer(tmp_path)
    assert "new project" in layer
    assert "propose" in layer
    assert "File map" not in layer and "Project documents" not in layer


def test_established_layer_has_docs_index_readme_and_map(tmp_path: Path) -> None:
    make_established(tmp_path)
    (tmp_path / "README.md").write_text("# Habit App\n\nTracks habits.\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "state.md").write_text("# State rules\nRiverpod only.\n")

    layer = workspace_layer(tmp_path)
    assert "established project" in layer
    assert "`README.md` — Habit App" in layer
    assert "`docs/state.md` — State rules" in layer
    assert "read" in layer.lower()  # the read-first instruction
    assert "Tracks habits." in layer  # README excerpt
    assert "lib/" in layer and "mod0.dart" in layer  # file map


def test_readme_excerpt_is_capped(tmp_path: Path) -> None:
    make_established(tmp_path)
    (tmp_path / "README.md").write_text("# Big\n" + "x" * 10_000)
    layer = workspace_layer(tmp_path)
    assert "truncated — read the full file" in layer
    assert len(layer) < 8_000  # whole section stays bounded


def test_repo_map_entry_cap(tmp_path: Path) -> None:
    for i in range(300):
        (tmp_path / f"file{i:03d}.py").write_text("pass")
    tree = repo_map(tmp_path)
    assert len(tree.splitlines()) <= TREE_MAX_ENTRIES + 1
    assert "truncated" in tree


def test_docs_index_cap_and_ai_exclusion(tmp_path: Path) -> None:
    make_established(tmp_path)
    (tmp_path / "docs").mkdir()
    for i in range(30):
        (tmp_path / "docs" / f"d{i:02d}.md").write_text(f"# Doc {i}\n")
    (tmp_path / ".ai").mkdir()
    (tmp_path / ".ai" / "project.md").write_text("# not a doc for the index")

    index = docs_index(tmp_path)
    assert len(index) <= DOCS_INDEX_MAX
    assert all(not rel.startswith(".ai") for rel, _ in index)
