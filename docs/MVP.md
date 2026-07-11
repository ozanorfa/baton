# MVP — First Working Version

**Status:** Draft v1 · 2026-07-11
**Related docs:** [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) · [ARCHITECTURE.md](ARCHITECTURE.md) · [DECISIONS.md](DECISIONS.md) · [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) · [TASKS.md](TASKS.md)

The MVP is milestone **M4** (tasks T01–T30): one command runs a deterministic four-stage pipeline over three AI CLIs and produces inspectable artifacts plus an execution report. Nothing dynamic, nothing parallel, nothing clever.

---

## 1. The Command

```bash
cd my-flutter-app
ai init                                              # once per project
ai "Add Face ID support to the Flutter application"
```

Optional variations:

```bash
ai --with-designer "Redesign the settings screen"    # enable the optional Designer stage
ai ask --role planner "Is Riverpod or Bloc better here?"   # one-shot escape hatch, no pipeline
ai doctor                                            # verify providers before a big run
```

## 2. What Happens, Stage by Stage

Pipeline and bindings from `.ai/config.yaml` (defaults shown; changing any of this is a config edit, never code):

```yaml
pipeline:
  stages: [planner, designer, coder, reviewer]
roles:
  planner:  { provider: codex }
  designer: { provider: antigravity, enabled: false }
  coder:    { provider: claude }
  reviewer: { provider: codex }
```

**Stage 0 — Preflight (free, no tokens).** Resolve all four role→provider bindings up front; health-check each distinct provider once; warn if the git working tree is dirty (ADR-007); create `.ai/runs/<run-id>/`.

**Stage 1 — Planner (Codex CLI).** Receives: the request + the Project layer (`.ai/project.md`) + planner role template. Produces `artifacts/plan.md` — a self-contained, numbered implementation plan (files to touch, approach, acceptance criteria). Self-contained because downstream stages get the plan, never the Planner's transcript (ADR-006).

**Stage 2 — Designer (Antigravity CLI, ADR-012) — skipped unless enabled.** Receives: request + Project layer + `plan.md`. Produces `artifacts/design.md` — widget hierarchy, UX flow, UI suggestions. For the Face ID example this stage is off by default; a `--with-designer` run would add biometric-prompt UX guidance here.

**Stage 3 — Coder (Claude Code).** Receives: `plan.md` (+ `design.md` if present) + Project layer + coder role template. Runs headless with scoped edit permissions (`--permission-mode acceptEdits`, ADR-007) **in the project directory** — it explores the repo with its own tools; the orchestrator never inlines source files into the prompt. Edits land directly in the repo. Produces `artifacts/changes.md` (its own summary of what it changed and why); the orchestrator then snapshots `git diff` into the run dir.

**Stage 4 — Reviewer (Codex CLI).** Receives: `plan.md` + `changes.md` + the git diff + reviewer role template. Produces `artifacts/review.md` — findings and improvement suggestions, explicitly *not* rewritten code (role boundary, spec §5). The Reviewer's verdict feeds the report; in the MVP it does **not** gate or loop back to the Coder — the human decides what to do with findings.

**Stage 5 — Report (free, no tokens).** `report.json` + Rich terminal summary.

## 3. What You See

```
$ ai "Add Face ID support to the Flutter application"

  Run 2026-07-11_1432_a3f9 · my-flutter-app

  ✓ preflight   4 roles resolved · 3 providers healthy · git tree clean
  ✓ planner     codex      1m 42s   plan.md
  ○ designer    skipped (disabled)
  ✓ coder       claude     6m 18s   changes.md · 7 files changed (+412 −38)
  ✓ reviewer    codex      1m 05s   review.md · 2 findings

  Run succeeded in 9m 05s
  ─────────────────────────────────────────────────────────────
  stage      provider   duration   tokens (in/out)      status
  planner    codex      1m 42s     — / —                ✓
  designer   —          —          —                    skipped
  coder      claude     6m 18s     48 210 / 9 833       ✓
  reviewer   codex      1m 05s     — / —                ✓
  ─────────────────────────────────────────────────────────────
  artifacts  .ai/runs/2026-07-11_1432_a3f9/artifacts/
  report     .ai/runs/2026-07-11_1432_a3f9/report.json

  Review findings (review.md):
   1. Missing NSFaceIDUsageDescription fallback copy for Touch ID devices
   2. BiometricService swallows PlatformException — surface auth errors to UI
```

Token columns show **measured values only** (Claude's JSON reports them; Codex/Antigravity may not → `—`, never an estimate presented as fact — risk R2).

## 4. What's on Disk Afterwards

```
.ai/runs/2026-07-11_1432_a3f9/
├── run.json          # state machine: every stage's status, timings, session ids
├── report.json       # the summary above, machine-readable
├── artifacts/
│   ├── plan.md
│   ├── changes.md
│   ├── diff.patch    # git diff snapshot of the coder's edits
│   └── review.md
├── prompts/          # the exact prompt each stage received — the token audit trail
│   ├── 01-planner.md
│   ├── 03-coder.md
│   └── 04-reviewer.md
└── logs/
    ├── orchestrator.jsonl
    └── *.stdout / *.stderr per stage
```

Plus the actual code changes in the repo, uncommitted, ready for `git diff` / your editor. **The orchestrator never commits** — reviewing and committing is the human's job in the MVP.

## 5. When Something Fails

Fail-stop (ADR-008): the run halts at the failed stage; everything already produced is preserved.

```
  ✓ planner     codex      1m 42s   plan.md
  ✗ coder       claude     0m 14s   FAILED

  Stage 'coder' failed: process exited 1 (auth expired?)
  Raw output: .ai/runs/…/logs/03-coder.stderr
  Completed artifacts preserved: plan.md

  Next steps:
    ai doctor                 # check provider health
    ai runs show 2026-07-11_1432_a3f9
```

No retries, no fallback provider, no skipping ahead. (`ai resume <run-id>` — continue from the failed stage reusing `plan.md` — arrives in M5, immediately after the MVP.)

## 6. Explicitly Out of Scope (MVP)

Per IMPLEMENTATION_PLAN §3 — worth restating because each of these will be tempting mid-build:

- Retries, provider fallback, escalation — **no** (ADR-008)
- Parallel stages, dynamic reordering, model-decided routing — **no** (ADR-004)
- Review→Coder feedback loop / auto-fix of findings — **no** (human decides)
- tmux sessions — **no** (ADR-002); session *ids* are recorded, session *reuse* is post-MVP
- Tester/Docs/Security/Perf/Deploy roles, MCP, memory — **no**
- Cost estimation for providers that don't report usage — **no** (show `—`)

## 7. Trust Model (read before first run)

The Coder stage edits your repository unattended (ADR-007). The safety net is: run from a clean git tree (warned otherwise) → every change is in `diff.patch` and `git diff` → the Reviewer reports findings on the actual diff → nothing is committed by the tool. If that trust level is wrong for your project, don't run the pipeline on it — use `ai ask` for advisory-only output.

## 8. MVP Definition of Done

- [ ] `ai init` bootstraps `.ai/` per PROJECT_STRUCTURE §2.1 in a fresh Flutter repo
- [ ] `ai doctor` shows all three providers healthy
- [ ] `ai "Add Face ID support to the Flutter application"` completes planner → coder → reviewer with real providers; `--with-designer` adds the Antigravity (Gemini-model) stage
- [ ] All artifacts, prompts, logs, `run.json`, `report.json` present and correct in the run dir
- [ ] Coder's real edits match `diff.patch`; nothing committed
- [ ] Terminal summary shows per-stage provider, duration, status, and measured-or-`—` tokens
- [ ] A mid-pipeline failure (kill a provider) produces the §5 experience: preserved artifacts, cause, raw-output path, next steps
- [ ] Fake-provider integration suite (T29) green with zero token cost
- [ ] Swapping a role's provider in `.ai/config.yaml` changes the execution with no code change
