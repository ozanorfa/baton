# Manual Testing Guide

Commands you can run yourself to check the orchestrator, grouped by the milestone that introduced them. Grows with every milestone.

**`batonai` is installed globally** (via `uv tool install --editable .`, 2026-07-11), so every command below works from **any directory** — no `uv run`, no `--project`. Because the install is editable, new milestones are picked up automatically. To remove it ever: `uv tool uninstall ai-orchestrator`.

## The simplest possible test

```bash
mkdir /tmp/play && cd /tmp/play
batonai "Create a file hello.py that prints: Hello from the pipeline"
```

That's the whole thing. No config needed — built-in defaults run planner (codex) → designer (skipped) → coder (claude) → reviewer (codex).

**About the `$` figures below and in run output:** they are the provider-reported API-equivalent value. On subscription plans (Claude Pro/Max, ChatGPT) you are **not charged per run** — runs consume your plan's included quota (session limits are that quota running low). Only API-key users pay the figure as a real bill. A typical full run consumes $0.15–1.50 of quota-equivalent, mostly fixed overhead.

For real projects, run `batonai init` first and fill in `.ai/project.md` — every stage reads it, and it noticeably improves output quality.

Only the test-suite commands (`uv run pytest`, `uv run ruff check .`) still need to run from the repo (`~/Desktop/ai/ai-agent-test`).

---

## M0 — Foundations (free, no tokens)

```bash
uv run batonai --version        # prints: ai-orchestrator 0.1.0
uv run batonai --help           # lists all commands
uv run batonai config show      # merged config as a table with a "source" column
uv run pytest              # full test suite — everything should pass
uv run ruff check .        # lint — should print "All checks passed!"
```

**Config precedence experiment** — override a value via environment and watch its source change from `defaults` to `env (AI_ORCH_*)`:

```bash
AI_ORCH_PROVIDERS__CLAUDE__TIMEOUT_S=1234 uv run batonai config show | grep timeout
```

The same works with a project file: put `providers: {claude: {timeout_s: 777}}` into `.ai/config.yaml` in any directory and run `batonai config show` there — the source column will say `project`.

## M1 — Provider adapters

**Free:**

```bash
uv run batonai doctor           # all three providers should show "✓ healthy"
                           # with versions and their role bindings
```

Break it on purpose to see the failure UX: `AI_ORCH_PROVIDERS__CODEX__COMMAND=/nope uv run batonai doctor` → codex row shows "binary not found", exit code 1.

**Spends tokens** (one real AI call each; Claude ≈ $0.10–0.15 per call, Codex/Antigravity ride your subscriptions):

```bash
uv run batonai ask --role planner  "In one sentence: what is Riverpod?"     # → Codex
uv run batonai ask --role designer "In one sentence: what is Material 3?"   # → Antigravity
uv run batonai ask --role coder    "In one sentence: what is a Dart mixin?" # → Claude Code
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
uv run --project ~/Desktop/ai/ai-agent-test batonai "Create a file hello.py that prints: Hello from the pipeline"
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
batonai init                 # creates .ai/config.yaml, .ai/project.md, .ai/.gitignore
batonai init                 # run again → "nothing to do", nothing overwritten
cat .ai/project.md      # the profile skeleton — fill this in for real projects
```

**Stack auto-detection:** run `batonai init` in a folder containing a `pyproject.toml` (or `pubspec.yaml`, `package.json`, `go.mod`, …) — the profile's Stack section is pre-filled, e.g. `Detected: Python (pyproject.toml).` With no marker files it stays neutral ("Nothing was auto-detected").

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
batonai runs list             # all runs: status, per-stage glyphs (✓✗○·), cost, verdict
batonai runs show <run-id>    # one run in detail
```

**Resume, the real thing:** whenever a run fails (provider limit, timeout, Ctrl-C), the failure message now prints the exact command: `batonai resume <run-id>`. It re-enters at the failed stage and reuses every artifact that already succeeded — the planner is never paid twice. `batonai resume <id> --from reviewer` deliberately redoes a stage of a successful run. Resume refuses (with explanation) if you changed the pipeline config since the run.

**Ctrl-C experiment (spends a few planner tokens):** start a run, hit Ctrl-C during a stage — then `batonai runs show <id>` shows the interrupted stage as failed with a resume hint, and `batonai resume <id>` continues it.

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
batonai init                                                    # then a small real feature:
batonai "one small real feature request"                        # ~$1–2 quota
```

Judge three artifacts: `prompts/01-planner.md` (does the Workspace section list *your* docs?), `artifacts/plan.md` (does the plan follow *your* conventions — state management, folder layout — instead of generic boilerplate?), and the `git diff` + review. Discard everything with `git checkout main && git branch -D ai-experiment`, or commit and PR as usual.

## Publisher role (ADR-014) — different provider than the Coder, prepare-only

**Safety guarantee, upfront:** this stage is **off by default in every project** — a plain `batonai "<request>"` never invokes it. Even enabled, it **never runs `git commit`, `git push`, or any GitHub operation** — it only writes a draft text file for you to read. Verify this yourself any time with `git log --oneline` before/after.

Motivated by: "I don't want Claude Code to also handle git — let Codex (or whoever) draft that instead, and only for projects I choose."

**Free:** the whole gating + provider-independence behavior, zero tokens:

```bash
uv run pytest tests/integration/test_publisher_gating.py
```

**Real test, any git repo:**

```bash
batonai --with-publisher "your feature request"
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
batonai "your feature request"
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

## Interactive iteration (ADR-019/020) — `batonai revise` and `batonai publish`

The "run → correct → ship" loop. This is the conversational layer: iterate on a run without starting over, then commit on your own command.

**Free (no tokens):** the logic in isolation.

```bash
uv run pytest tests/unit/test_session_chaining.py tests/integration/test_revise_cli.py tests/integration/test_publish.py
```

**`batonai revise` — real test, any git repo:**

```bash
batonai "add a small feature"                 # 1. run the pipeline
git diff                                 # 2. review what the Coder did
batonai revise "change X to work differently" # 3. correct it — SAME run, no restart
```

Then verify it continued rather than restarted:
- `batonai runs list` shows **still one run** (no new run-id) — `revise` reuses the last one.
- In `run.json`, the coder's `session_id` is **unchanged** across the revise — the Coder resumed its own session (it remembers its prior work); Planner→Reviewer keep their shared Codex session id.
- `.ai/runs/<id>/prompts/02-coder.md` now contains your correction text (it's injected into the request so the Coder sees it).
- `--from planner` re-runs from the top (re-plans); default is from the Coder.

**`batonai publish` — the only command that runs git, and only when you ask:**

```bash
batonai publish                    # preview only — prints the drafted commit message, touches nothing
batonai publish --commit           # git add -A && git commit (shows the file list, asks to confirm)
batonai publish --push             # ...and git push
batonai publish -m "fix: x" --push # skip drafting, use your own message
batonai publish --push --yes       # skip the confirmation prompt
```

Verify the guarantee yourself: `git log --oneline` before/after a plain `batonai publish` (no flags) — **no new commit**. Then `batonai publish --commit` and confirm — exactly one new commit, `git status` clean. Message source precedence: `-m` > the last run's `commit_message.md` (if you ran `--with-publisher`) > a fresh draft (the Publisher's provider, falling back to the deterministic `git diff` message).

## `batonai review` (ADR-022) — a second opinion on your own diff

Review the current working-tree changes with the Reviewer's model, pipeline-free and read-only:

```bash
# edit some files (yours or a run's output), then:
batonai review                      # verdict + findings over the current diff
batonai review -m "focus on error handling and edge cases"
```

Read-only by design: it captures the diff (`snapshot_changes`, untracked included), assembles the real `reviewer.md` context around it, and prints the verdict — it **commits nothing, edits nothing, saves no run**. Clean tree → "nothing to review"; non-git dir → exit 2. Costs one Reviewer call (cheaper than a full pipeline). Free logic check: `uv run pytest tests/integration/test_review.py`.

## fix-loop (ADR-023) — auto-fix once on a NEEDS WORK verdict

Off by default. Opt in per run or per project; it runs **exactly one** automatic fix pass when the Reviewer returns `NEEDS WORK`, then stops.

```bash
batonai --fix-loop "implement something with a deliberately tricky requirement"
# or, always-on for a project: .ai/config.yaml → pipeline: {fix_loop: true}
```

What to expect: the pipeline runs; if the reviewer verdict is `NEEDS WORK`, you'll see `⟳ reviewer flagged blockers — running one fix pass…`, then the Coder re-runs (resuming its own session, now with the review findings) and the Reviewer re-checks — a second summary prints. It's the automatic cousin of `batonai revise`; the same run-id is reused (check `batonai runs list`). It never loops twice, even if the second verdict is still `NEEDS WORK` (bounded by construction). `APPROVE`/`APPROVE WITH NOTES` never trigger it. Free trigger-logic check: `uv run pytest tests/integration/test_fix_loop.py`.

## Tester stage (ADR-024) — run your tests, zero-LLM

Off by default. Enable per run; it runs the project's test command after the Coder and hands the result to the Reviewer. **Zero tokens** — it just runs a command.

```bash
# auto-detected command (pyproject.toml → pytest, package.json → npm test, …):
batonai --with-tester "add a feature"
# or pin it in .ai/config.yaml:
#   providers: {testrunner: {command: "uv run pytest"}}
```

What to expect: after the Coder, a `tester` stage runs; `.ai/runs/<id>/artifacts/test_report.md` holds `PASSED`/`FAILED` + the output tail, and the Reviewer's prompt now includes it. **Report-and-continue**: failing tests do *not* stop the run — the tester stage still succeeds, and the Reviewer factors the failure into its verdict (`NEEDS WORK`), which `--fix-loop` (ADR-023) can then auto-fix. Only a missing/undetectable command or a timeout fails the stage. Free check: `uv run pytest tests/contract/test_testrunner_adapter.py tests/integration/test_tester.py`.

## Code-health context (ADR-025) — hotspots in every stage prompt

Off by default. Needs the `repowise` tool installed (`pipx install repowise`). Enable per run; baton runs `repowise health` itself (no manual setup) and injects the worst-scoring files into every stage's prompt so they tread carefully there. On an **established** project only.

```bash
batonai --health "refactor the busiest module"
# or pin it in .ai/config.yaml:
#   context: {health: true}
```

What to expect: each stage's prompt (see `.ai/runs/<id>/prompts/*`) gains a **"Code-health hotspots"** section listing the ≤5 worst files with complexity/nesting. The transient `.repowise/` index baton creates is **removed after the run** (a `.repowise/` you made yourself with `repowise init` is left untouched). If `repowise` isn't installed, the flag is a silent no-op — the run is byte-identical to a plain run, never an error. Free checks: `uv run pytest tests/unit/test_health.py`; and to see the injected slice without spending tokens: `python -c "from pathlib import Path; from ai_orchestrator.context.health import health_section; print(health_section(Path('.')))"` (run via `uv run`).

**Caution:** baton only ever runs `repowise health` (in-process, no network, no LLM, no config writes). It never runs `repowise init` — that command registers machine-wide MCP hooks in `~/.claude`. If you set repowise up yourself, that's your one-time step, not baton's.

## Interactive front door (ADR-026) — bare `batonai`

The guided way in: scan → offer the missing setup → ask → run. Everything it does, a flag could already do; it exists so a newcomer doesn't need to know which flag.

**Free (no tokens):** the decision table and the entry-point guarantees.

```bash
uv run pytest tests/unit/test_scan.py tests/integration/test_wizard.py
```

**Free, ten seconds — see the scan without starting anything:** run it in any project and press Ctrl-C at the first question.

```bash
cd ~/some-project && batonai      # then Ctrl-C
```

What to look for: a `providers / project / git / baton / health` report, then a question. The `health` row appears only if `repowise` is installed — and the ≤3 hotspots listed there are the same ones that get injected into the stage prompts for the run you start from here (this is the one path where code-health is on by default; the scripted path still needs `--health`, ADR-025 unchanged).

**The state matrix** — each row is one defined behavior, all free to check:

```bash
mkdir /tmp/empty && cd /tmp/empty && batonai   # empty: asks what to build FIRST, then offers setup
cd ~/an-uninitialized-repo && batonai          # offers `init`, then asks
cd ~/a-repo-with-runs && batonai               # shows the last run + a menu (new/revise/review/publish)
```

Verify the guarantees yourself:

- **Cancellation is clean:** Ctrl-C at any question → `cancelled — nothing was changed.`, exit code **130** (not 1 — a cancel is not a stage failure). Check with `echo $?`, and confirm no `.ai/` was created if you declined setup.
- **A broken provider blocks before it asks:** `AI_ORCH_PROVIDERS__CODEX__COMMAND=/nope batonai` → names the provider and the roles needing it, exits **2**, and never reaches a question.
- **Scripts are unaffected:** `batonai < /dev/null` (or in CI) prints help and exits 0 — it must never prompt where there is no terminal. This is the compatibility promise; if it ever hangs, that's the bug.
- **Declining changes nothing:** answer `n` to the setup offer and confirm `.ai/` was not created.

Note the wizard hands off to the *same* `run` code path as `batonai "<request>"` — so a run started from it is indistinguishable from a typed one (same artifacts, same `runs list` entry), except that code-health is on.

## Baton's own footprint stays out of the diff (ADR-027)

Two guarantees found the hard way — by a real run, where a reviewer wasted a finding on baton's `.gitignore` edit and a stray `.pyc` flipped a verdict to NEEDS WORK.

**Free — the root `.gitignore` is never touched:**

```bash
mkdir /tmp/own-files && cd /tmp/own-files && git init -q
echo "node_modules/" > .gitignore
batonai init
cat .gitignore                    # unchanged, byte for byte
cat .ai/.gitignore                # the rule lives here instead: "runs/"
git check-ignore -v .ai/runs/x    # git confirms the nested rule is in force
```

Then the point of it: right after `init`, a run's diff must be **empty** — baton's setup is not the Coder's work.

```bash
python3 -c "
from pathlib import Path
from ai_orchestrator.core.workspace import snapshot_changes
print(snapshot_changes(Path('.')))"      # changed=False
```

**Free — generated artifacts never reach the reviewer:**

```bash
mkdir -p __pycache__ && touch __pycache__/x.cpython-312.pyc
python3 -c "
from pathlib import Path
from ai_orchestrator.core.workspace import snapshot_changes
s = snapshot_changes(Path('.')); print(s.changed)"     # still False — noise is not a change
```

Excluded: `__pycache__`, `*.pyc`, `*.pyo`, `.pytest_cache`, `.ruff_cache`, `.mypy_cache`, `node_modules`, `.DS_Store`. **Not** excluded on purpose: `build/`, `dist/`, `target/` — real source directories in some projects, and already gitignored when they aren't. Free checks: `uv run pytest tests/unit/test_run_manager.py tests/unit/test_cli_init.py`.


## Code-health cache (ADR-028) — computed once per project, not per run

**Free, and the point of it:** the first call computes and stores; the second is served from disk.

```bash
time batonai health          # first call: shells out to repowise, ~2-4s
time batonai health          # second call: from .ai/health.json, well under 1s
                             #   and prints "from the cached analysis, computed <age> ago"
batonai health --refresh     # force a recompute regardless of freshness
```

**Free — the cache invalidates itself when code changes:**

```bash
touch src/some_file.py       # any source file, newer than the cache
batonai health                # recomputes automatically — no stale reading served
```

`.ai/health.json` holds the rendered slice next to the raw KPIs, so it's readable by just opening it — no command needed. It's covered by `.ai/.gitignore` (local state, like `runs/`). Free logic check: `uv run pytest tests/unit/test_health.py -k cache`.

## No-baseline-commit reporting (ADR-029) — a repo baton (or you) just `git init`'d

**Free:** create a git repo with files but no commit, and watch both surfaces name it distinctly from "dirty":

```bash
mkdir /tmp/nobase && cd /tmp/nobase && git init -q && echo "x=1" > a.py
batonai            # wizard scan: "repository has no commits yet — with no baseline,
                   #   every file counts as a change…" + the exact `git commit` command
git rev-parse --verify HEAD   # still fails afterward — baton never committed it for you
```

Same wording from a scripted run (no wizard): `batonai "<request>"` prints the identical warning before the pipeline starts. Free logic check: `uv run pytest tests/unit/test_scan.py -k commits`.

## Live progress notes (ADR-030) — evidence a long stage is actually working

**Real test, spends quota:** watch the spinner *change text* while the Planner (codex) works, instead of sitting still for minutes.

```bash
batonai "<a request that makes the planner explore several files>"
```

What to expect: next to the spinner, short notes like `$ sed -n '1,240p' src/thing.py` appear and update as codex works — this is `codex --json`'s own event stream, forwarded live, not a fabricated heartbeat. The **Coder** (claude) still shows a plain spinner — claude doesn't stream yet (documented limitation, see ADR-030's status line). Notes never reach the durable log: `grep -c stage_progress .ai/runs/*/logs/orchestrator.jsonl` must print `0`.

Free logic check (no live provider): `uv run pytest tests/unit/test_progress.py` — covers the buffered-path-unless-streaming guarantee, a watchdog timeout on a hanging streamed process, and that notes can't carry escape sequences or Rich markup.

## Model choice at setup, and `batonai setup` to change it later (ADR-031/032/033)

**Free — offered once, at `init`:**

```bash
mkdir /tmp/models && cd /tmp/models && git init -q && echo "[project]" > pyproject.toml
batonai init
```
Enter keeps everything (writes no `providers:` block at all — byte-identical to today); typing `haiku` for claude writes `providers: {claude: {model: haiku}}`. `--no-models` skips the question outright; without a terminal it's never asked (a scripted `batonai init` never blocks).

**Free — revise it later, any time, without re-running `init`:**

```bash
batonai setup    # shows the current role→provider→model table, then asks about each
```
Enter everywhere → "nothing changed", file untouched. Provider names are validated (an unknown one is rejected with a note); model ids are **not** — whatever you type is passed straight to the CLI. `-` clears a model pin back to the CLI's own default.

**Free — live model discovery for antigravity:** unlike codex/claude, `agy` can list its own current models. Enable the Designer role first (`roles: {designer: {enabled: true}}` in `.ai/config.yaml`), then:
```bash
batonai setup    # the antigravity model prompt shows a real, live list (e.g. "gemini-3.6-flash-high/…")
                 #   fetched from `agy models`, not a hardcoded guess
```
If `agy` is missing or the call fails, this silently falls back to no suggestion — never an error. codex and opencode have no such list; they show an explanatory hint instead (where to find a valid id) rather than nothing.

Free logic checks: `uv run pytest tests/unit/test_model_catalog.py tests/unit/test_setup.py`.


## Hardening pass — no silent states (ADR-034)

**Free — a crash never leaves a run "running":**
```bash
uv run pytest tests/unit/test_hardening_adr034.py -q
```
Covers: an exception from the transport marks the stage and run FAILED on disk before propagating; a RUNNING run renders as "run not finished", never "run succeeded"; porcelain `-z` parsing keeps paths with spaces; undecodable bytes become U+FFFD instead of an error; a timed-out stage kills its *grandchild* too (both transport paths); claude's `allow_commands` flags; case-insensitive verdicts.

**Free — end to end on the fake provider:**
```bash
uv run pytest tests/integration/test_hardening_adr034_e2e.py -q
```
Covers: `revise` with a do-nothing Coder fails ("no workspace changes") even though the tree is already dirty; a real revise still passes and the Reviewer sees the cumulative diff; an untracked `my new file.txt` reaches the diff; Ctrl-C mid-stage → summary + exit 130; `publish` reuses a run's draft only while `diff.patch` still matches the tree.

**Live — the Coder actually runs your tests (costs one Coder stage):**
```yaml
# .ai/config.yaml
providers:
  claude: {allow_commands: true}
```
```bash
batonai "add a failing-then-fixed unit test for <some function>"
cat .ai/runs/<run-id>/artifacts/changes.md     # "How to verify" now reports a command that RAN
grep -c '"Bash(git commit:\*)' .ai/runs/<run-id>/logs/*coder*.stdout || true
```
Without the setting, the same summary must say it could not run anything (the Coder prompt requires this). With it, try asking the Coder to commit: it must report that `git commit` was denied — the deny list, not the prompt, is what stops it.

**Live — Ctrl-C during a stage:** start any run, press Ctrl-C while the Coder spinner is up. Expect the summary table with the Coder row ✗, the line "interrupted — the run above was stopped mid-stage…", exit code 130 (`echo $?`), and `ps aux | grep -c "[c]laude"` → `0` (the whole provider tree is gone). `batonai runs list` shows the run as `failed`, not `unfinished`.

**Live — `publish` does not reuse a stale draft:** after a run with `--with-publisher`, edit any file, then `batonai publish`. Expect "the draft from run … describes a different diff than the working tree now holds — drafting afresh." and a new message.
