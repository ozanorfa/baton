"""Workspace awareness (ADR-013): established vs greenfield, decided by code.

Established projects get orientation material (capped repo map + docs index
+ read-instruction); greenfield directories get proposal guidance instead.
Nothing here is an LLM decision, and no document is ever inlined whole —
agents are pointed at doors, the furniture stays where it is (risk R4).
"""

from enum import StrEnum
from pathlib import Path

from ai_orchestrator.context.health import health_section

# Directories that are tooling/VCS noise, never project source.
EXCLUDED_DIRS = {
    ".git", ".ai", ".github", "node_modules", ".venv", "venv", "__pycache__",
    "build", "dist", ".dart_tool", ".idea", ".vscode", "Pods", ".gradle",
    "target", ".pytest_cache", ".ruff_cache",
}

CODE_EXTENSIONS = {
    ".py", ".dart", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java",
    ".kt", ".swift", ".rb", ".php", ".c", ".cc", ".cpp", ".h", ".hpp",
    ".cs", ".m", ".mm", ".scala", ".vue", ".svelte",
    # the web fundamentals — a plain HTML/CSS site is very much a real project
    # (field bug: charm_website was misdetected as greenfield, 2026-07-12)
    ".html", ".htm", ".css", ".scss", ".sass", ".less",
}

# A workspace with at least this many source files is "established".
ESTABLISHED_THRESHOLD = 3

# Ecosystem marker files (shared with `batonai init`'s stack detection): their
# presence means a scaffold/toolchain exists → conventions exist → established,
# even with fewer than ESTABLISHED_THRESHOLD source files.
STACK_MARKERS: list[tuple[str, str]] = [
    ("pubspec.yaml", "Flutter/Dart (pubspec.yaml)"),
    ("package.json", "JavaScript/TypeScript (package.json)"),
    ("pyproject.toml", "Python (pyproject.toml)"),
    ("requirements.txt", "Python (requirements.txt)"),
    ("go.mod", "Go (go.mod)"),
    ("Cargo.toml", "Rust (Cargo.toml)"),
    ("Gemfile", "Ruby (Gemfile)"),
    ("pom.xml", "Java (pom.xml)"),
    ("build.gradle", "Java/Kotlin (build.gradle)"),
    ("*.xcodeproj", "iOS/macOS (Xcode project)"),
]


def stack_labels(project_dir: Path) -> list[str]:
    """Labels for every ecosystem marker present, in STACK_MARKERS order.

    Shared by `batonai init`'s profile skeleton and the wizard's scan (ADR-026) so
    the two never disagree about what stack a directory is.
    """
    labels: list[str] = []
    for pattern, label in STACK_MARKERS:
        if "*" in pattern:
            if next(project_dir.glob(pattern), None) is not None:
                labels.append(label)
        elif (project_dir / pattern).exists():
            labels.append(label)
    return labels


def has_stack_marker(project_dir: Path) -> bool:
    return bool(stack_labels(project_dir))

# Hard caps — the whole point is bounded context (ADR-013 trade-offs).
TREE_MAX_DEPTH = 3
TREE_MAX_ENTRIES = 100
DOCS_INDEX_MAX = 12
README_EXCERPT_CHARS = 1500


class WorkspaceMode(StrEnum):
    GREENFIELD = "greenfield"
    ESTABLISHED = "established"


def _iter_tree(root: Path, max_depth: int):
    """Yield (depth, path) breadth-ish, skipping noise dirs; deterministic order."""
    stack: list[tuple[int, Path]] = [(0, root)]
    while stack:
        depth, current = stack.pop(0)
        try:
            entries = sorted(current.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except (PermissionError, OSError):
            continue
        for entry in entries:
            if entry.name.startswith(".") and entry.name not in {".gitignore"}:
                continue
            if entry.is_dir():
                if entry.name in EXCLUDED_DIRS:
                    continue
                yield depth, entry
                if depth + 1 < max_depth:
                    stack.append((depth + 1, entry))
            else:
                yield depth, entry


def detect_mode(project_dir: Path) -> WorkspaceMode:
    if has_stack_marker(project_dir):
        return WorkspaceMode.ESTABLISHED
    code_files = 0
    for _, path in _iter_tree(project_dir, TREE_MAX_DEPTH):
        if path.is_file() and path.suffix.lower() in CODE_EXTENSIONS:
            code_files += 1
            if code_files >= ESTABLISHED_THRESHOLD:
                return WorkspaceMode.ESTABLISHED
    return WorkspaceMode.GREENFIELD


def repo_map(project_dir: Path) -> str:
    """A capped, indented file tree — orientation, not inventory."""
    lines: list[str] = []
    truncated = False
    for depth, path in _iter_tree(project_dir, TREE_MAX_DEPTH):
        if len(lines) >= TREE_MAX_ENTRIES:
            truncated = True
            break
        suffix = "/" if path.is_dir() else ""
        lines.append(f"{'  ' * depth}{path.name}{suffix}")
    if truncated:
        lines.append("… (truncated — explore further with your own tools)")
    return "\n".join(lines)


def _doc_title(path: Path) -> str:
    try:
        for line in path.read_text(errors="replace", encoding="utf-8").splitlines()[:10]:
            line = line.strip()
            if line.startswith("#"):
                return line.lstrip("# ").strip()
            if line:
                return line[:80]
    except OSError:
        pass
    return "(unreadable)"


def docs_index(project_dir: Path) -> list[tuple[str, str]]:
    """(relative path, title) of the project's own markdown docs, capped."""
    candidates: list[Path] = []
    for name in (
        "README.md", "readme.md", "CONTRIBUTING.md", "ARCHITECTURE.md",
        "AGENTS.md", "CLAUDE.md",  # AI-assistant convention files are prime docs
    ):
        if (project_dir / name).is_file():
            candidates.append(project_dir / name)
    docs_dir = project_dir / "docs"
    if docs_dir.is_dir():
        candidates.extend(
            sorted(p for p in docs_dir.rglob("*.md") if ".ai" not in p.parts)
        )
    index: list[tuple[str, str]] = []
    seen_ids: set[tuple[int, int]] = set()  # dedupe by inode: case-insensitive
    for path in candidates:  # filesystems (macOS) make README.md == readme.md
        try:
            stat = path.stat()
        except OSError:
            continue
        file_id = (stat.st_dev, stat.st_ino)
        if file_id in seen_ids:
            continue
        seen_ids.add(file_id)
        # as_posix(): the index is prose for a model, and `docs\\state.md` would
        # both read oddly and break the tests' expectations on Windows (ADR-035)
        index.append((path.relative_to(project_dir).as_posix(), _doc_title(path)))
        if len(index) >= DOCS_INDEX_MAX:
            break
    return index


def _readme_excerpt(project_dir: Path) -> str | None:
    for name in ("README.md", "readme.md"):
        path = project_dir / name
        if path.is_file():
            text = path.read_text(errors="replace", encoding="utf-8").strip()
            if not text:
                return None
            if len(text) > README_EXCERPT_CHARS:
                return text[:README_EXCERPT_CHARS] + "\n… (truncated — read the full file)"
            return text
    return None


def workspace_layer(project_dir: Path, include_health: bool = False) -> str:
    """The mode-appropriate workspace section for every stage's prompt.

    `include_health` (opt-in, ADR-025) appends a repowise code-health hotspot
    slice for established projects — greenfield has no history to score.
    """
    if detect_mode(project_dir) is WorkspaceMode.GREENFIELD:
        return (
            "## Workspace: new project\n\n"
            "This directory has little or no existing code. There are no conventions "
            "to discover — propose them: state your structure, stack, and naming "
            "choices explicitly, and call out every assumption you make."
        )

    parts = ["## Workspace: established project\n"]
    parts.append(
        "Existing code and conventions are authoritative here. Read before you "
        "write: consult the documents below and neighboring source files with "
        "your own tools before making decisions. Match what exists — naming, "
        "structure, libraries, test patterns."
    )
    index = docs_index(project_dir)
    if index:
        listing = "\n".join(f"- `{rel}` — {title}" for rel, title in index)
        parts.append(f"### Project documents (read the relevant ones first)\n{listing}")
    excerpt = _readme_excerpt(project_dir)
    if excerpt:
        parts.append(f"### README excerpt\n{excerpt}")
    parts.append(f"### File map (partial)\n```\n{repo_map(project_dir)}\n```")
    if include_health:
        section = health_section(project_dir)
        if section:
            parts.append(section)
    return "\n\n".join(parts)
