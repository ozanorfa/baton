# Task Breakdown — AI Coding Orchestrator

**Status:** Frozen — historical record · **35/35 done, all milestones complete 2026-07-12** · post-MVP work is tracked in [CHANGELOG.md](../CHANGELOG.md), [DECISIONS.md](DECISIONS.md) and [WORKLOG.md](WORKLOG.md), not here
**Related docs:** [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) · [ARCHITECTURE.md](ARCHITECTURE.md) · [DECISIONS.md](DECISIONS.md) · [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) · [MVP.md](MVP.md)

35 tasks, 30–90 minutes each, strictly ordered — every task builds on a working previous state and ends in something runnable or testable. Tasks map to milestones M0–M5 from IMPLEMENTATION_PLAN.md §4. Total estimate: ~36 h.

Conventions:
- **Done when** is the acceptance criterion — a task isn't finished until it holds.
- Tasks depend on all earlier tasks in their milestone unless noted; cross-milestone dependencies are noted explicitly.
- Estimates assume the design docs are followed; if a task forces a design change, update the relevant doc (and DECISIONS.md if consequential) *as part of the task*.

---

## M0 — Foundations

**T01 ✅ · Project scaffolding — 45 min**
`uv init` with `src/` layout per PROJECT_STRUCTURE.md; `pyproject.toml` with deps (typer, rich, pydantic, pyyaml; dev: pytest, ruff), console script `batonai`, empty entry-point group `ai_orchestrator.providers`; `.gitignore`; git init + first commit.
**Done when:** `uv run batonai --version` prints the version; `uv run pytest` passes (one placeholder test); `ruff check` clean.

**T02 ✅ · Shared models — 60 min**
`core/models.py`: `StageSpec`, `StageStatus`, `StageResult`, `RunState`, `AgentRequest`, `AgentResult`, `Usage`, `Health`, `Capabilities` as pydantic models per ARCHITECTURE §2.2/§3.1. No imports from other project modules.
**Done when:** unit tests validate construction, serialization round-trip (`RunState` → JSON → `RunState`), and invalid-status rejection.

**T03 ✅ · Config schema + defaults — 60 min**
`config/schema.py` (`AppConfig`, `PipelineConfig`, `RoleConfig`, `ProviderConfig`) and `config/defaults.yaml` matching ARCHITECTURE §4 exactly (stage list, role bindings, provider commands/timeouts).
**Done when:** `defaults.yaml` parses into a valid `AppConfig`; unknown keys warn; a bad value fails with file+key in the message.

**T04 ✅ · Config loader with precedence — 90 min**
`config/loader.py`: merge defaults ← `~/.config/ai-orchestrator/config.yaml` ← `./.ai/config.yaml` ← env (`AI_ORCH_*`) ← CLI overrides; track the source of every value.
**Done when:** unit tests cover each precedence pair, deep-merge of nested keys, and missing-file tolerance; every value knows its source.

**T05 ✅ · `batonai config show` — 45 min**
Typer app skeleton (`cli/app.py`, `cli/commands/config_cmd.py`, `cli/render.py`): render merged config as a Rich table with a source column.
**Done when:** running it in a dir with a project config shows project values overriding user/defaults, each annotated with its source.

**T06 ✅ · RunManager — 60 min**
`core/run_manager.py`: run-id scheme (`YYYY-MM-DD_HHMM_<hex4>`), run-dir skeleton creation (`artifacts/ prompts/ logs/`), atomic `run.json` writes (temp file + rename), artifact save/load, load-existing-run.
**Done when:** unit tests cover create → transition → reload; a simulated crash between write and rename leaves the previous `run.json` intact.

**T07 ✅ · Structured event log — 45 min**
`observability/events.py`: JSONL writer bound to a run dir; events `run_started`, `stage_started`, `provider_invoked`, `stage_succeeded`, `stage_failed`, `run_finished` with timestamps/durations.
**Done when:** unit test replays a fake run and asserts the JSONL sequence parses and is ordered.

---

## M1 — Provider Adapter Layer

**T08 ✅ · Transport layer — 60 min**
`transport/base.py` (`Invocation`, `TransportResult`, `Transport` protocol) + `transport/headless.py`: `subprocess.run`, argv list, `shell=False`, prompt via stdin (ADR-010), timeout → structured timeout result (not an exception), stdout/stderr captured to files in the run dir.
**Done when:** unit tests against `/bin/cat` and a sleeping script verify stdin delivery, exit-code capture, and timeout handling.

**T09 ✅ · Adapter ABC + registry — 60 min**
`providers/base.py` (`ProviderAdapter` per ARCHITECTURE §3.1) and `providers/registry.py` with built-in registration; unknown-name error lists registered providers.
**Done when:** a dummy adapter registers and resolves by name; unknown name raises the actionable error.

**T10 ✅ · ClaudeCodeAdapter + fixtures — 90 min**
`providers/claude.py`: build `claude -p --output-format json` invocations (model/timeout from config; permission flags only when the role edits files, per ADR-007); parse JSON → `AgentResult` with `session_id` and measured `Usage`. Capture real fixtures: success, error, permission-block, malformed JSON → `tests/contract/fixtures/claude/`.
**Done when:** contract tests pass against all fixtures; malformed output yields a failed `AgentResult` pointing at the raw file, not an exception.

**T11 ✅ · CodexAdapter + fixtures — 75 min**
`providers/codex.py`: `codex exec` with pinned non-interactive sandbox/approval flags; parse text output; `Usage` = `None` when unavailable (ADR-003). Real fixtures: success + failure.
**Done when:** contract tests pass; capabilities correctly report token support.

**T12 ✅ · AntigravityAdapter + fixtures — 60 min** *(was GeminiAdapter; ADR-012)*
`providers/antigravity.py`: `agy -p` with explicit non-interactive approval flags; same pattern as T11. Verify actual flags/output against the installed `agy` first — it is younger than the other CLIs.
**Done when:** contract tests pass against captured fixtures.

**T13 ✅ · Entry-point plugin discovery — 45 min**
Registry discovers `ai_orchestrator.providers` entry points via `importlib.metadata` at startup; a broken plugin logs a warning and is skipped, never crashes startup.
**Done when:** integration test installs a toy plugin package into the test env and resolves its adapter by name.

**T14 ✅ · `batonai doctor` — 60 min**
Health checks per adapter (binary on PATH, `--version` parse, auth probe where cheap); Rich table: provider, binary, version, auth, status.
**Done when:** all three real CLIs report healthy on the dev machine; an uninstalled binary shows an actionable failure row instead of a crash.

**T15 ✅ · `batonai ask` — 60 min**
`batonai ask --role <role> "<prompt>"`: resolve role → adapter via config, one-shot invoke through the real transport, print result + usage. First end-to-end token spend.
**Done when:** `batonai ask --role planner "say hi"` round-trips through Codex CLI; result and (if reported) usage print correctly.

---

## M2 — Pipeline Engine

**T16 ✅ · RoutingEngine — 45 min**
`core/routing.py`: resolve **all** stages up front from config; health-check each distinct provider once before any stage runs (ARCHITECTURE §2.3).
**Done when:** unit tests: a mis-bound role fails at run start (not mid-run) with a message naming the role, provider, and failing check.

**T17 ✅ · PipelineEngine — 90 min**
`core/engine.py`: the sequential loop from ARCHITECTURE §2.2 — optional-stage gating, persist-before-evaluate, fail-stop, artifact registry, `run.json` transitions via RunManager, events via T07. Context assembly is a stub interface for now (real one lands in M3).
**Done when:** unit tests with mock adapters cover: happy path, skipped optional stage, mid-pipeline failure (later stages stay `pending`, artifacts preserved, run marked failed).

**T18 ✅ · Fake provider CLI — 60 min**
`tests/integration/fake_provider/`: a tiny script speaking the transport contract (reads stdin, emits configurable canned output/exit code/delay) + a test-only adapter registered via the plugin mechanism (validates T13 for real).
**Done when:** fake provider works through the *real* headless transport and registry — no test-only code paths in `src/`.

**T19 ✅ · Integration: two-stage pipeline — 60 min**
Full engine run (planner → coder, both fake) in a temp project dir: assert run-dir layout, artifact contents, `run.json` states, JSONL event sequence, and the failure variant.
**Done when:** the suite passes in CI-like conditions (no network, no real CLIs) in under ~5 s.

**T20 ✅ · `batonai "<request>"` wiring — 60 min**
Root command: bare argument triggers the pipeline; dirty-git-tree warning (ADR-007); minimal live progress line per stage via `render.py`.
**Done when:** `batonai "test request"` with fake-provider config runs the pipeline from the shell; **M2 demo achieved** with real providers on a toy request (manual).

---

## M3 — Context Management

**T21 ✅ · Role prompt templates — 90 min**
`prompts/{planner,designer,coder,reviewer}.md`: role definition, boundaries (single-responsibility per spec §5), output-format instructions, self-contained-artifact rule (ADR-006), named placeholders for context sections. The Reviewer template demands findings, not rewrites.
**Done when:** each template renders with sample context and passes a review against the role definitions in the original spec.

**T22 ✅ · Context layers + contracts — 60 min**
`context/layers.py` (Global static text; Project from `.ai/project.md`; Task from request + artifacts; Agent from templates) and `context/contracts.py` — the ARCHITECTURE §5 table as data.
**Done when:** unit tests assert exactly which artifacts each stage's contract admits (coder gets plan not transcript; reviewer gets diff not design).

**T23 ✅ · ContextManager — 75 min**
`context/manager.py`: `assemble(stage) → rendered prompt`; enforce contracts; persist every rendered prompt to `prompts/NN-<stage>.md` in the run dir; replace the T17 stub.
**Done when:** integration test inspects a run dir and verifies each stage's persisted prompt contains only contract-admitted sections.

**T24 ✅ · `batonai init` — 60 min**
Bootstrap `.ai/`: starter `config.yaml`, `project.md` skeleton (stack/conventions prompts for the user to fill), append `.ai/runs/` to `.gitignore`; idempotent (refuses to clobber, offers diff). *Extended post-M3 on user feedback: the Stack section is pre-filled by auto-detecting marker files (pubspec.yaml, package.json, pyproject.toml, go.mod, Cargo.toml, …); skeleton examples are framework-neutral.*
**Done when:** running in a fresh dir creates the documented footprint (PROJECT_STRUCTURE §2.1); second run is a no-op; **M3 demo achieved** — prompts in a real run visibly differ per role contract.

---

## M4 — MVP: Full Pipeline

**T25 ✅ · Four-stage default + designer gating — 45 min**
Default config gains the full stage list; designer `enabled: false` by default, activated via config or `--with-designer`.
**Done when:** integration tests cover both paths (designer skipped vs. included) with fake providers.

**T26 ✅ · Coder stage hardening — 75 min**
Coder invocation with scoped permission flags (ADR-007); capture `changes.md` (the Coder's self-reported summary, per its template) and a `git diff` snapshot into `artifacts/` after the stage; detect blocked-on-permission outcomes → failed stage with guidance.
**Done when:** manual run against a real toy repo: Claude Code edits files headlessly, and the diff artifact matches the actual repo changes.

**T27 ✅ · Reporter — 60 min**
`core/reporter.py`: aggregate `run.json` + usage into `report.json` (per-stage: provider, model, duration, tokens-or-null, status, artifact paths; totals; verdict from reviewer artifact presence + run status).
**Done when:** unit tests validate the schema against succeeded/failed/skipped-stage runs; `Usage=None` renders as `null`, never fabricated numbers (risk R2).

**T28 ✅ · Rich run UX — 75 min**
`render.py`: live per-stage progress (spinner, stage name, provider, elapsed) and the final summary table; failure rendering names the stage, cause, raw-output path, and next steps.
**Done when:** demo run reads clearly end-to-end; failure output includes the three pieces above (this is ADR-008's UX half).

**T29 ✅ · MVP integration suite — 60 min**
Fake-provider end-to-end of the full four-stage pipeline: report correctness, designer on/off, failure at each stage position (4 variants).
**Done when:** the whole suite stays green and fast (<10 s), zero tokens.

**T30 ✅ · MVP acceptance run — 90 min**
The real thing: `batonai init` + `batonai "Add Face ID support to the Flutter application"` against a real Flutter sample repo with real providers. Capture fresh contract fixtures from the run. File issues for every rough edge; fix in-scope ones.
**Done when:** the MVP acceptance test from IMPLEMENTATION_PLAN §5 passes; **M4/MVP achieved**.

---

## M5 — Hardening & DX

**T31 ✅ · `batonai runs list/show` — 60 min**
List: table of run dirs (id, request excerpt, status, duration, total tokens). Show: per-stage detail + artifact paths for one run.
**Done when:** both render correctly against a mix of succeeded/failed historical runs.

**T32 ✅ · Failure-path polish — 60 min**
Audit every failure mode surfaced by T30 (timeout, auth expiry, parse failure, permission block): each produces a failure report with cause + raw path + resume instructions, and a distinct exit code (`0` ok, `1` stage failed, `2` config/env error).
**Done when:** each failure mode is integration-tested via the fake provider (which can simulate all of them).

**T33 ✅ · `batonai resume <run-id>` — 90 min**
Load `run.json`, keep succeeded artifacts, re-enter the loop at the failed stage; refuse (with explanation) if config stage-list changed since the run; `--from <stage>` to deliberately redo a stage.
**Done when:** integration test: fail at coder → fix fake provider → resume → run completes reusing the original plan artifact; **M5 demo achieved**.

**T34 ✅ · Timeout & edge hardening — 60 min**
Per-provider timeouts from config enforced end-to-end; SIGINT during a run leaves a resumable `run.json`; concurrent runs in one project don't collide.
**Done when:** integration tests cover timeout-as-stage-failure and Ctrl-C-then-resume.

**T35 ✅ · README + quickstart — 45 min**
Install (uv), prerequisites (three CLIs + auth), 5-minute quickstart, trust-model note (ADR-007, prominently), pointers into `docs/`.
**Done when:** a fresh-machine walkthrough of the README reaches a successful `batonai doctor` and demo run without consulting anything else.

---

## Sequencing notes

- **First real token spend is T15** — everything before it is free; everything after M2 can develop against the fake provider (T18), which is why it lands early.
- **Fixture capture (T10–T12) needs the real CLIs installed and authenticated** on the dev machine; do `batonai doctor`'s manual equivalent before starting M1.
- **T21 (templates) is the highest-leverage 90 minutes in the project** — artifact quality downstream depends on it; budget review time accordingly.
- If any task exceeds ~2× its estimate, stop and check whether it's fighting a design decision — that's a signal to revisit the doc, not to push through.
