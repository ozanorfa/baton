# Manual Testing Guide

Commands you can run yourself to check the orchestrator, grouped by the milestone that introduced them. Grows with every milestone.

**`ai` is installed globally** (via `uv tool install --editable .`, 2026-07-11), so every command below works from **any directory** — no `uv run`, no `--project`. Because the install is editable, new milestones are picked up automatically. To remove it ever: `uv tool uninstall ai-orchestrator`.

## The simplest possible test

```bash
mkdir /tmp/play && cd /tmp/play
ai "Create a file hello.py that prints: Hello from the pipeline"
```

That's the whole thing. No config needed — built-in defaults run planner (codex) → designer (skipped) → coder (claude) → reviewer (codex). Costs roughly $0.15–0.30 (the Claude stage); the rest rides your subscriptions.

For real projects, run `ai init` first and fill in `.ai/project.md` — every stage reads it, and it noticeably improves output quality.

Only the test-suite commands (`uv run pytest`, `uv run ruff check .`) still need to run from the repo (`~/Desktop/ai/ai-agent-test`).

---

## M0 — Foundations (free, no tokens)

```bash
uv run ai --version        # prints: ai-orchestrator 0.1.0
uv run ai --help           # lists all commands
uv run ai config show      # merged config as a table with a "source" column
uv run pytest              # full test suite — everything should pass
uv run ruff check .        # lint — should print "All checks passed!"
```

**Config precedence experiment** — override a value via environment and watch its source change from `defaults` to `env (AI_ORCH_*)`:

```bash
AI_ORCH_PROVIDERS__CLAUDE__TIMEOUT_S=1234 uv run ai config show | grep timeout
```

The same works with a project file: put `providers: {claude: {timeout_s: 777}}` into `.ai/config.yaml` in any directory and run `ai config show` there — the source column will say `project`.

## M1 — Provider adapters

**Free:**

```bash
uv run ai doctor           # all three providers should show "✓ healthy"
                           # with versions and their role bindings
```

Break it on purpose to see the failure UX: `AI_ORCH_PROVIDERS__CODEX__COMMAND=/nope uv run ai doctor` → codex row shows "binary not found", exit code 1.

**Spends tokens** (one real AI call each; Claude ≈ $0.10–0.15 per call, Codex/Antigravity ride your subscriptions):

```bash
uv run ai ask --role planner  "In one sentence: what is Riverpod?"     # → Codex
uv run ai ask --role designer "In one sentence: what is Material 3?"   # → Antigravity
uv run ai ask --role coder    "In one sentence: what is a Dart mixin?" # → Claude Code
```

Check the dim usage line under each answer: Codex and Claude show measured tokens (Claude also cost and session id); Antigravity shows nothing — it reports nothing, and this tool never invents numbers.

## M2 — Pipeline engine

**Free** — run the full pipeline machinery on the fake provider (no AI, no tokens):

```bash
uv run pytest tests/integration/   # config → routing → engine → subprocess, end to end
```

**Spends tokens** — a real two-stage pipeline in a scratch directory (Codex plans ≈ free on subscription, Claude codes ≈ $0.15–0.30):

```bash
mkdir -p /tmp/pipeline-demo/.ai && cd /tmp/pipeline-demo && git init -q
cat > .ai/config.yaml << 'YAML'
pipeline:
  stages: [planner, coder]
roles:
  planner: {provider: codex}
  coder: {provider: claude}
YAML
uv run --project ~/Desktop/ai/ai-agent-test ai "Create a file hello.py that prints: Hello from the pipeline"
```

Then check what happened:

```bash
cat hello.py && python3 hello.py            # the coder's real work
ls .ai/runs/*/artifacts/                    # plan.md, changes.md
cat .ai/runs/*/artifacts/plan.md            # what the planner produced
cat .ai/runs/*/prompts/02-coder.md          # exactly what the coder was told
cat .ai/runs/*/logs/orchestrator.jsonl      # the machine-readable event stream
```

Failure UX (free, uses git being absent): run the same command in a directory whose config points a provider at a bad binary — preflight fails before any stage runs, exit code 2.

## M3 — Context management

**Free:**

```bash
mkdir /tmp/ctx-test && cd /tmp/ctx-test
ai init                 # creates .ai/config.yaml, .ai/project.md, .gitignore entry
ai init                 # run again → "nothing to do", nothing overwritten
cat .ai/project.md      # the profile skeleton — fill this in for real projects
```

**Stack auto-detection:** run `ai init` in a folder containing a `pyproject.toml` (or `pubspec.yaml`, `package.json`, `go.mod`, …) — the profile's Stack section is pre-filled, e.g. `Detected: Python (pyproject.toml).` With no marker files it stays neutral ("Nothing was auto-detected").

**After any pipeline run**, inspect the prompts to see the context system working:

```bash
cat .ai/runs/<run-id>/prompts/01-planner.md   # role template + boundaries + your project profile
cat .ai/runs/<run-id>/prompts/04-reviewer.md  # gets plan + changes — but never design.md (contract)
```

What to look for: every prompt has "Working rules", your `.ai/project.md` content, and *only* the artifacts that role's contract admits. Role boundaries are explicit ("You **plan only**", "do NOT rewrite the code").

**Template override experiment (free):** put a file at `.ai/prompts/planner.md` containing `MY TEMPLATE $request` — the next run's planner prompt uses it instead of the built-in.

## M4 — MVP (report, diff capture, run UX)

**Free** — the full MVP behavior on the fake provider:

```bash
uv run pytest tests/integration/test_mvp_suite.py   # 4-stage runs + failure at every stage
```

**After any real pipeline run**, new things to look at:

```bash
cat .ai/runs/<run-id>/report.json          # machine-readable report: stages, tokens
                                           #   (measured-or-null), totals, verdict
cat .ai/runs/<run-id>/artifacts/diff.patch # exactly what the coder changed (incl. new files)
```

What to look for in the terminal output: an animated spinner while each provider works, a `totals:` line, and a `reviewer verdict: APPROVE / APPROVE WITH NOTES / NEEDS WORK` line on success.

**Silent-failure detection (the ADR-007 safety net):** if an edit-stage claims success but changes nothing in a git repo, the run fails with "reported success but no workspace changes were detected". You saw the fail-stop UX for real if a provider ever hits its usage limit mid-run — artifacts up to that stage are preserved and the summary names the cause.

## Exit codes (for scripting)

| code | meaning |
|------|---------|
| 0 | success |
| 1 | a provider/stage failed |
| 2 | configuration or usage error |
