# Manual Testing Guide

Commands you can run yourself to check the orchestrator, grouped by the milestone that introduced them. Grows with every milestone.

**`ai` is installed globally** (via `uv tool install --editable .`, 2026-07-11), so every command below works from **any directory** — no `uv run`, no `--project`. Because the install is editable, new milestones are picked up automatically. To remove it ever: `uv tool uninstall ai-orchestrator`.

## The simplest possible test

```bash
mkdir /tmp/play && cd /tmp/play
ai "Create a file hello.py that prints: Hello from the pipeline"
```

That's the whole thing. No config needed — built-in defaults run planner (codex) → designer (skipped) → coder (claude) → reviewer (codex).

**About the `$` figures below and in run output:** they are the provider-reported API-equivalent value. On subscription plans (Claude Pro/Max, ChatGPT) you are **not charged per run** — runs consume your plan's included quota (session limits are that quota running low). Only API-key users pay the figure as a real bill. A typical full run consumes $0.15–1.50 of quota-equivalent, mostly fixed overhead.

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

## M5 — Hardening (runs, resume)

**Free** — the whole resume/failure machinery on the fake provider:

```bash
uv run pytest tests/integration/test_resume_and_hardening.py tests/integration/test_runs_command.py
```

**With any project that has run history:**

```bash
ai runs list             # all runs: status, per-stage glyphs (✓✗○·), cost, verdict
ai runs show <run-id>    # one run in detail
```

**Resume, the real thing:** whenever a run fails (provider limit, timeout, Ctrl-C), the failure message now prints the exact command: `ai resume <run-id>`. It re-enters at the failed stage and reuses every artifact that already succeeded — the planner is never paid twice. `ai resume <id> --from reviewer` deliberately redoes a stage of a successful run. Resume refuses (with explanation) if you changed the pipeline config since the run.

**Ctrl-C experiment (spends a few planner tokens):** start a run, hit Ctrl-C during a stage — then `ai runs show <id>` shows the interrupted stage as failed with a resume hint, and `ai resume <id>` continues it.

## Exit codes (for scripting)

| code | meaning |
|------|---------|
| 0 | success |
| 1 | a provider/stage failed |
| 2 | configuration or usage error |

## Workspace awareness (ADR-013)

**Free, ten seconds:** compare what stages are told in the two worlds.

```bash
cd ~/Desktop/ai/ai-agent-test && uv run python -c "
from pathlib import Path
from ai_orchestrator.context.awareness import workspace_layer
print(workspace_layer(Path.cwd()))"        # established: docs index + file map
```

Run the same in an empty directory → the greenfield guidance instead ("propose your structure… state assumptions"). In any real run's `prompts/*.md` you'll now see a `## Workspace:` section; in an established repo it lists the project's own README/docs and instructs the agent to read them before working. Running in a non-git directory now also prints a tip that diff capture is disabled until `git init`.

### Testing workspace awareness on a real project (the one that matters)

```bash
cd ~/your-real-project && git checkout -b ai-experiment   # throwaway branch
uv run --project ~/Desktop/ai/ai-agent-test python -c "
from pathlib import Path
from ai_orchestrator.context.awareness import workspace_layer
print(workspace_layer(Path.cwd()))"                        # free: what stages will be told
ai init                                                    # then a small real feature:
ai "one small real feature request"                        # ~$1–2 quota
```

Judge three artifacts: `prompts/01-planner.md` (does the Workspace section list *your* docs?), `artifacts/plan.md` (does the plan follow *your* conventions — state management, folder layout — instead of generic boilerplate?), and the `git diff` + review. Discard everything with `git checkout main && git branch -D ai-experiment`, or commit and PR as usual.

## Publisher role (ADR-014) — different provider than the Coder, prepare-only

**Safety guarantee, upfront:** this stage is **off by default in every project** — a plain `ai "<request>"` never invokes it. Even enabled, it **never runs `git commit`, `git push`, or any GitHub operation** — it only writes a draft text file for you to read. Verify this yourself any time with `git log --oneline` before/after.

Motivated by: "I don't want Claude Code to also handle git — let Codex (or whoever) draft that instead, and only for projects I choose."

**Free:** the whole gating + provider-independence behavior, zero tokens:

```bash
uv run pytest tests/integration/test_publisher_gating.py
```

**Real test, any git repo:**

```bash
ai --with-publisher "your feature request"
```

Then check two things: `.ai/runs/<id>/artifacts/commit_message.md` (a drafted commit message + PR description — Conventional Commits style, cites the reviewer's verdict) and `git log --oneline` (must show **no new commit** — the stage only drafts text, it never runs `git commit`/`git push`, per the explicit trust-model decision in ADR-014). To use a different provider for publishing than for coding: `.ai/config.yaml` → `roles: {publisher: {provider: codex}}` while `roles: {coder: {provider: claude}}` — completely independent, guaranteed by config, never a runtime guess.

Enable it permanently for a project (skip the flag every time): `.ai/config.yaml` → `roles: {publisher: {enabled: true}}`.

## Session chaining (ADR-015) — the token-savings feature

**Free:** the chaining decision logic in isolation, zero tokens:

```bash
uv run pytest tests/unit/test_session_chaining.py
```

**Real test, any git repo:**

```bash
ai "your feature request"
```

Then look at `run.json` — Planner and Reviewer should show the **identical Codex `session_id`**, proving it's one continued conversation, not two cold ones (Publisher/Designer default to Antigravity now — ADR-016 — so they won't show a Codex session id at all; that's by design, not a bug):

```bash
python3 -c "
import json
d = json.load(open('.ai/runs/<run-id>/run.json'))
for s in d['stages']: print(s['name'], s['provider'], s['session_id'])"
```

For the token effect: grep each stage's raw stdout log for `"usage"` and compare `cached_input_tokens` against `input_tokens` — the cached ratio should *rise* through the chain (each later stage's genuinely new/fresh cost should stay roughly flat rather than growing).

Opt out for a project that wants stages fully independent: `.ai/config.yaml` → `pipeline: {session_chaining: false}`.

## Interactive iteration (ADR-019/020) — `ai revise` and `ai publish`

The "run → correct → ship" loop. This is the conversational layer: iterate on a run without starting over, then commit on your own command.

**Free (no tokens):** the logic in isolation.

```bash
uv run pytest tests/unit/test_session_chaining.py tests/integration/test_revise_cli.py tests/integration/test_publish.py
```

**`ai revise` — real test, any git repo:**

```bash
ai "add a small feature"                 # 1. run the pipeline
git diff                                 # 2. review what the Coder did
ai revise "change X to work differently" # 3. correct it — SAME run, no restart
```

Then verify it continued rather than restarted:
- `ai runs list` shows **still one run** (no new run-id) — `revise` reuses the last one.
- In `run.json`, the coder's `session_id` is **unchanged** across the revise — the Coder resumed its own session (it remembers its prior work); Planner→Reviewer keep their shared Codex session id.
- `.ai/runs/<id>/prompts/02-coder.md` now contains your correction text (it's injected into the request so the Coder sees it).
- `--from planner` re-runs from the top (re-plans); default is from the Coder.

**`ai publish` — the only command that runs git, and only when you ask:**

```bash
ai publish                    # preview only — prints the drafted commit message, touches nothing
ai publish --commit           # git add -A && git commit (shows the file list, asks to confirm)
ai publish --push             # ...and git push
ai publish -m "fix: x" --push # skip drafting, use your own message
ai publish --push --yes       # skip the confirmation prompt
```

Verify the guarantee yourself: `git log --oneline` before/after a plain `ai publish` (no flags) — **no new commit**. Then `ai publish --commit` and confirm — exactly one new commit, `git status` clean. Message source precedence: `-m` > the last run's `commit_message.md` (if you ran `--with-publisher`) > a fresh draft (the Publisher's provider, falling back to the deterministic `git diff` message).

