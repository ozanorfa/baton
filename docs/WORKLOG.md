# Work Log — AI Coding Orchestrator

Running log of all work sessions: what was done, by whom (👤 user / 🤖 Claude), problems hit, and how they were resolved. Newest entries at the bottom. Git history covers the code; this covers everything else.

---

## 2026-07-11 · Session 1 — Phase 1 documentation

- 👤 Provided the full project specification (deterministic multi-CLI orchestrator, Planner/Designer/Coder/Reviewer roles, tmux, CAO evaluation request).
- 🤖 Researched Amazon CAO (awslabs/cli-agent-orchestrator). Verdict: not a foundation (agent-driven supervisor model, heavyweight FastAPI/SQLite runtime, coordination costs tokens); borrow its tmux/adapter patterns later.
- 👤 Approved two deviations from the original spec:
  - **Headless-first transport** instead of tmux scraping (`claude -p --output-format json`, `codex exec`, `gemini -p`); tmux deferred to post-MVP observability (ADR-002).
  - **Codex CLI** as the OpenAI provider vehicle for Planner/Reviewer (ADR-003).
- 🤖 Wrote the six design docs, reviewed one at a time by user: IMPLEMENTATION_PLAN, ARCHITECTURE, DECISIONS (11 ADRs), PROJECT_STRUCTURE, TASKS (35 tasks, ~36 h), MVP. Consistency pass found and fixed one drift (missing `diff.patch` in ARCHITECTURE's run-dir tree).
- 👤 Approved all docs; gave go for implementation.

## 2026-07-11 · Session 1 — Milestone M0: Foundations (T01–T07)

- 🤖 T01: git init, uv project (`src/` layout), `ai` console script, pytest+ruff. Python 3.13.2 via uv (spec: ≥3.12).
- 🤖 T02: shared pydantic models (`core/models.py`) — stage/run state machines, AgentRequest/Result, Usage (None = unmeasured, never estimated).
- 🤖 T03: config schema + `defaults.yaml`; cross-checks (stage→role, role→provider) fail at load time; unknown keys warn.
- 🤖 T04: config loader — precedence CLI > env (`AI_ORCH_*`) > project > user > defaults; every value tracks its source; validation errors name the offending file.
- 🤖 T05: `ai config show` with source column. Deviation: source labels shortened to `project`/`user` (full paths listed below table) because long paths wrapped the Rich table badly.
- 🤖 T06: RunManager — atomic `run.json` writes (temp+rename); crash-at-rename test proves prior state survives.
- 🤖 T07: JSONL event log per run.
- ✅ **M0 demo passed:** `ai --version`, `ai config show` with live source annotation. 29 tests green, ruff clean, one commit per task (7 commits).

## 2026-07-11 · Session 1 — Provider CLI setup (prep for M1)

- 🤖 Found only Claude Code installed; `codex` and `gemini` missing.
- 👤 Installed both via npm — hit `command not found`: npm's global bin (`~/npm/bin`) was not on PATH (longstanding; `firebase`/`tsc` in there were also unreachable).
- 🤖 Was correctly permission-blocked from editing `~/.zshrc`; provided the fix for user to run. Recommended the **append** variant (`export PATH="$PATH:$HOME/npm/bin"`) so npm's bundled `node`/`npm` don't shadow system ones.
- 👤 Fixed PATH, ran `codex login` — **Codex authenticated ✅** (codex-cli 0.144.1).
- 👤 `gemini` login failed: *"This client is no longer supported for Gemini Code Assist for individuals → migrate to Antigravity"*.
- 🤖 Researched: **Google shut down Gemini CLI for personal accounts on 2026-06-18** (moved individuals to Antigravity CLI / paid API keys). User's old `~/.antigravity` symlinks are broken (IDE uninstalled). → **Designer-provider decision pending** (Antigravity CLI vs. paid API key vs. defer Designer role). Designer stage is optional & disabled by default, so MVP is not blocked.
- 👤 Asked for this work log; 🤖 created it and will append every session.
- 👤 Decided: **install Antigravity CLI** as the Designer provider (rather than paid Gemini API key or deferring the role).
- 🤖 Wrote **ADR-012** (Antigravity CLI replaces Gemini CLI); propagated the change across all six docs, `defaults.yaml` (provider `antigravity`, command `agy`), and tests. First real exercise of the provider-agnosticism goal: zero core-design changes needed.
- ⏳ Pending (user): install Antigravity CLI + sign in, then M1 starts.

## 2026-07-11 · Session 1 — Milestone M1: Provider Adapter Layer (T08–T15)

- 👤 Installed Antigravity CLI (`curl -fsSL https://antigravity.google/cli/install.sh | bash` → `agy` 1.1.1 in `~/.local/bin`) and signed in with Google — **Antigravity authenticated ✅**. All three providers now live: claude 2.1.207, codex 0.144.1, agy 1.1.1.
- 🤖 Starting M1: transport layer (T08), adapter ABC + registry (T09), three concrete adapters with recorded fixtures (T10–T12), plugin discovery (T13), `ai doctor` (T14), `ai ask` (T15).
- 🤖 T08–T09: headless transport (stdin prompts, structured timeout/missing-binary results) + `ProviderAdapter` ABC with registry. Adapters are pure (build/parse only, never spawn) → contract-testable against recorded fixtures.
- 🤖 T10 (ClaudeCodeAdapter): captured real fixtures from claude 2.1.207. **Field finding:** a permission-blocked headless run exits 0 with `is_error: false` — protocol-invisible; only a stage-level `git diff` check can catch it (validates ADR-007/T26 design).
- 🤖 T11 (CodexAdapter): captured real fixtures from codex-cli 0.144.1. **Better than expected:** `--json` JSONL carries thread_id (resumable) AND measured token usage; `-s read-only|workspace-write` sandbox maps directly to role write-access.
- 🤖 T12 (AntigravityAdapter): captured real fixtures from agy 1.1.1. **Field findings:** (1) no stdin prompt support — `-` taken literally → ADR-010 amended with an argv exception; (2) `--sandbox` is incompatible with print mode (exit 1) — never passed; (3) no session id or token usage in print mode → honest `None`s; (4) `--print-timeout` (default 5m) pinned to request timeout.
- 🤖 T13: entry-point plugin discovery, integration-tested against a real (unmocked) dist-info on sys.path; broken plugins warn and are skipped.
- 🤖 T14: `ai doctor` — live run shows all three providers healthy with role bindings (claude 2.1.207/coder, codex 0.144.1/planner+reviewer, agy 1.1.1/designer).
- 🤖 T15: `ai ask --role <role>` — first sanctioned token spend. Live round-trips through all three providers succeeded; usage line shows measured tokens/cost/session where available, nothing where not.
- ✅ **M1 complete:** 65 tests green (unit + contract + integration), one commit per task. Real fixtures recorded from all three CLIs.
- 👤 Asked for a persistent manual-testing reference; 🤖 created `docs/MANUAL_TESTING.md` (grows per milestone). Also clarified: the orchestrator is a general base, not Flutter-specific — Flutter enters via per-project context (`.ai/project.md`) and role prompt templates.

## 2026-07-11 · Session 1 — Milestone M2: Pipeline Engine (T16–T20)

- 👤 Confirmed the orchestrator must stay usable beyond Flutter (web/backend); gave go for M2.
- 🤖 Starting M2: routing engine (T16), pipeline engine (T17), fake provider harness (T18), two-stage integration test (T19), `ai "<request>"` wiring (T20).
- 🤖 T16: RoutingEngine — all stages resolved + every distinct active provider health-checked before stage 1; disabled stages' providers not checked.
- 🤖 T17: PipelineEngine — sequential fail-stop loop; every transition persisted before the next action; prompts and raw stdout/stderr saved per stage; JSONL events.
- 🤖 T18+T19: fake provider CLI (prompt-directive driven: `[[fail:…]]`, `[[sleep:N]]`, `[[output:…]]`) + adapter discovered via committed dist-info through the real entry-point mechanism; full-stack two-stage integration tests incl. failure variant — zero tokens.
- 🤖 T20: bare `ai "<request>"` (argv rewrite → `ai run`), `--with-designer`, dirty-git-tree warning, live per-stage progress, summary table with measured tokens.
- ✅ **M2 demo (real providers):** two-stage pipeline in a scratch repo — Codex planned (7s, 25.9k/171 tokens), Claude Code created `hello.py` (22s, 42.9k/519 tokens), file verified working. **Field finding:** the Planner attempted to create the file itself and was stopped only by its read-only sandbox — M2's naive prompt has no role boundaries; exactly what M3's role templates (T21) exist to fix.
- ✅ **M2 complete:** 82 tests green. MANUAL_TESTING.md updated with M2 commands.
- 👤 Pushed back on test-instruction complexity ("this is not the simplicity I wish to see") — right: the mkdir/cat/uv-run boilerplate was incidental, not the product. 🤖 Installed `ai` globally (`uv tool install --editable .` → `~/.local/bin/ai`); testing is now `cd anywhere && ai "..."` with zero setup (built-in defaults cover the config). MANUAL_TESTING.md simplified accordingly.
- 👤 Ran the first user-driven full pipeline (`/tmp/play`, run 2026-07-11_1252_0769): planner 9s (25.7k/173), designer skipped, coder 25s (41.7k/469), reviewer 17s (39.8k/380) — **run succeeded**. Note: user activated the repo venv first; unnecessary since the global `ai` install — plain `ai` works in a fresh terminal.

## 2026-07-11 · Session 1 — Doc sync after M2 (M3 deferred by user)

- 👤 Reviewed the hello-world results with 🤖: plumbing A (routing, sandbox enforcement, artifact flow, cross-vendor review — the reviewer even ran the script to verify), role discipline D (planner attempted the coder's job again; M3's exact scope). Token economics noted: ~107k in / ~1k out on a one-liner = worst-case overhead ratio; amortizes on real tasks; `ai ask` is the right tool for tiny ones.
- 🤖 Synced all docs to implementation reality: README rewritten (install, quickstart, trust model, doc index); TASKS.md T01–T20 marked ✅ with progress header; IMPLEMENTATION_PLAN milestones M0–M2 ✅; ARCHITECTURE adapter table replaced with *verified* CLI behavior + temp-placement notes (ROLE_DEFAULTS/prompt stub → M3); PROJECT_STRUCTURE matched to repo (run.py, fake_provider harness, M3+/M5+ markers); DECISIONS/MVP status lines updated.
- ⏸ Next: M3 (T21–T24) on user's go.

## 2026-07-11 · Session 1 — Milestone M3: Context Management (T21–T24)

- 👤 Gave go for M3.
- 🤖 Starting: role prompt templates (T21), context layers + contracts (T22), ContextManager replacing the naive prompt stub (T23), `ai init` (T24).
- 🤖 T21: role templates (`prompts/*.md`): explicit boundaries per role + self-contained-artifact rule (ADR-006) + a `_global.md` rules layer and `_generic.md` fallback for unknown roles.
- 🤖 T22: `context/contracts.py` (the ARCHITECTURE §5 table as data; moved out of core/routing.py) + `context/layers.py` (Global/Project/Agent/inputs). Layering enforced: context imports models only.
- 🤖 T23: `ContextManager` wired into `ai run`; integration test proves per-role contract enforcement in real run-dir prompts (reviewer never sees design.md) and project template overrides.
- 🤖 T24: `ai init` — starter config, project-profile skeleton, gitignore entry; idempotent, never clobbers.
- ✅ **M3 demo (real providers, greet.py):** planner produced a *real plan* (Goal/Approach/numbered Steps/Acceptance criteria — no more trying to write files itself), citing the project profile's conventions; reviewer followed its template (Verdict: APPROVE, verification section, actually ran the script). Coder's `greet.py` works. Role-discipline grade goes D → A-.
- ✅ **M3 complete:** 95 tests green. Docs synced (TASKS 24/35, milestone stamps, M2 temp notes removed, MANUAL_TESTING M3 section).
- 👤 Ran the M3 verification himself (`/tmp/ctx-test`, run 2026-07-11_1746_10dc, countdown.py): planner 15s (13.3k/582), coder 41s (79k/1407), reviewer 20s (44.4k/707) — run succeeded. Generated code quality notably higher than the request demanded (argparse, input validation, help text, main guard) — the role templates + project profile working as intended.
- 👤 Flagged confusion: `ai init`'s project.md skeleton name-dropped Flutter/Riverpod inside a Python project. 🤖 Root cause: static example text in the template (Flutter-flavored per original spec), no detection involved. Fix: examples made framework-neutral + `ai init` now auto-detects the stack from marker files (pubspec.yaml, package.json, pyproject.toml, go.mod, Cargo.toml, …) and pre-fills the Stack section ("Detected: Python (pyproject.toml)."). 97 tests green.
- 🤖 Docs synced for the init change (ARCHITECTURE command table, PROJECT_STRUCTURE, TASKS T24 note, MANUAL_TESTING detection test). M4 next on user's go.

## 2026-07-11 · Session 1 — Milestone M4: MVP (T25–T30)

- 👤 Gave go for M4.
- 🤖 Starting: designer gating tests (T25), coder hardening + git diff capture (T26), report.json (T27), Rich run UX (T28), MVP integration suite (T29), real acceptance run (T30).
- 🤖 T25: designer gating covered end-to-end (default off / --with-designer / config-enabled).
- 🤖 T26: workspace verification for edit-stages — `diff.patch` captured (tracked + untracked, orchestrator's own `.ai/` excluded), reviewer contract gains the diff, and the silent permission-block signature (success + zero changes) now fails the stage with guidance.
- 🤖 T27: Reporter — `report.json` with measured-only totals (null, never 0) and verdict parsed from review.md.
- 🤖 T28: run UX — spinner during stages, thousands separators, totals line, verdict line, failure block with exact stderr path.
- 🤖 T29: MVP suite — full 4-stage CLI runs on the fake provider; failure injected at every stage position via new role-scoped directives (`[[fail@coder:…]]`); report correctness asserted. Zero tokens.
- 🤖 T30 attempt 1 (2026-07-11): real acceptance on a fresh `flutter create` app. Planner ✓; **coder hit the user's Claude session limit after 3m42s / $1.60** → fail-stop worked exactly as designed in the wild: cause named, plan.md + partial work preserved, reviewer never ran. Strongest possible motivation for M5's `ai resume`.
- 🤖 T30 attempt 2 (2026-07-12, after limit reset): partial coder work already passed `flutter analyze`; re-ran the pipeline instructing verification/completion. **Run succeeded: verdict APPROVE WITH NOTES** — planner 68s (73.4k/3.3k), coder 160s (390k/9.4k), reviewer 90s (142.9k/3.7k), $1.35, 299 insertions across 9 files, diff.patch + report.json verified. `ai init` stack detection worked on the real repo ("Detected: Flutter/Dart (pubspec.yaml)").
- 📌 Honest gaps found by the acceptance run: (1) the coder wrote a biometric-gate widget test it couldn't execute in its sandbox — it fails on pumpAndSettle timeout, and the reviewer's suggestions flagged exactly this verification gap → the future Tester role's job description, written by the pipeline itself; (2) session-limit failures argue for `ai resume` (T33, next milestone).
- ✅ **M4 / MVP COMPLETE:** 113 tests green; MVP.md checklist ticked (9/9); TASKS 30/35.
- 👤 Verified M4 himself (`/tmp/m4-test`, run 2026-07-12_0544_2f4f, stopwatch.py): full pipeline, $0.79 measured, verdict APPROVE WITH NOTES. Reviewer caught a real edge-case bug (`format_duration(59.999)` → `00:00:60.00`) with file/line reference — cross-vendor review demonstrably earning its cost.

## 2026-07-12 · Session 2 — Milestone M5: Hardening (T31–T35)

- 👤 Asked whether total token use is too high. 🤖 Analysis from his own run's raw logs: of the coder's 222k "input tokens", 94% (208.5k) were cache READS at ~10× discount across 12 agentic turns — the honest metric is the measured $0.79. Levers available today: `ai ask` for small tasks, per-project stage trimming, `providers.claude.model: haiku`, short project.md. Structural fix = session persistence (post-MVP #1). Future polish noted: cache-aware token column.
- 🤖 Starting M5: `ai runs list/show` (T31), failure-path polish (T32), `ai resume` (T33), timeout/SIGINT/collision hardening (T34), README walkthrough (T35).
- 🤖 T31: `ai runs list/show` — history table with per-stage glyphs (✓✗○·), measured cost, verdict.
- 🤖 T33: `ai resume <run-id>` — re-enters at the failed stage, reuses all on-disk artifacts (planner never re-paid), `--from <stage>` for deliberate redo, refuses on pipeline-config drift; failure output now advertises the exact resume command.
- 🤖 T32+T34: failure-mode matrix fully tested via the fake provider (timeout, provider crash, missing binary, config error, silent no-change, Ctrl-C) with distinct exit codes (0/1/2); Ctrl-C persists a resumable failed state before propagating; run-id collision retry.
- 🤖 T35: README — everyday-commands table, cost-control guidance, exit codes; MANUAL_TESTING M5 section.
- ✅ **M5 COMPLETE — ALL 35 TASKS, ALL MILESTONES (M0–M5) DONE.** 123 tests green. Docs closed out across the board.
- 👤 Startled by "$0.79" for the stopwatch run — asked whether he pays it. 🤖 Clarified: the figure is Claude Code's own `total_cost_usd` (API-equivalent value); on his subscription plan runs consume quota, not money (his session-limit hit is that quota mechanism). Per his request, a standing cost note now appears wherever cost is shown: footnote in run summary / `ai ask` / `ai runs list`, and a `cost_note` field in report.json. README/MANUAL_TESTING/MVP/ARCHITECTURE updated to explain quota-vs-billing.

## 2026-07-12 · Session 2 — Published to GitHub

- 👤 Cleared up a misconception (stages DO explore existing codebases — each agent reads the repo itself; project.md is steering, not the sole knowledge); brainstormed existing-project onboarding improvements (ai init --generate, docs-aware templates, repo map, memory, session reuse) — queued pending field evidence.
- 👤 Asked to publish: private GitHub repo under a better name. 🤖 Named it **baton** — the conductor's baton (deterministic, zero-token coordination) + the relay baton (artifacts handed stage to stage).

## 2026-07-12 · Session 2 — Workspace Awareness (ADR-013)

- 👤 Asked for different behavior on existing vs new projects — specifically: read the project's MD files before working on existing projects; skip that for new ones. Approved the "Project Awareness" proposal; requested no commit/push until his code review.
- 🤖 Built ADR-013: `context/awareness.py` — deterministic established/greenfield detection (≥3 source files, noise dirs excluded), capped repo map (100 entries, depth 3), docs index (README/docs/*.md/CONTRIBUTING, 12 max, titles extracted) + capped README excerpt + read-first instruction; greenfield gets propose-structure guidance instead. New `$workspace` placeholder in all role templates; ContextManager computes the layer once per run. `ai run` in a non-git dir now tips that diff capture/safety checks are off.
- 🐛 Live sanity check caught a real bug before review: macOS case-insensitive filesystem listed README.md twice (README.md + readme.md) — fixed with inode-based dedupe.
- ✅ 134 tests green (11 new: detection heuristics, caps, dedupe, end-to-end prompt differences). Left uncommitted for user code review.
- 👤 **Reviewed and approved**; confirmed understanding of the two-step mechanism (Python indexes the docs, the agents read the relevant ones with their own tools). ADR-013 → Accepted; committed and pushed.
- 🤖 Added real-Flutter-project test walkthrough to MANUAL_TESTING (throwaway branch → free workspace-layer preview → ai init → one small real feature → judge plan against the project's own conventions); README status mentions ADR-013. Pushed.
- 🐛 **First field bug (thank you, charm_website):** user's real project — a plain HTML/CSS landing page — was misdetected as greenfield. Root cause: CODE_EXTENSIONS omitted `.html`/`.css`. Fix: web fundamentals added (+.htm/.scss/.sass/.less); stack-marker presence (pubspec.yaml, package.json, …) now also implies established (scaffold = conventions); marker list consolidated into awareness.py (init imports it); `CLAUDE.md` added to the docs index (AI-convention files are prime docs). Verified against the real project: now `established`, README + CLAUDE.md indexed. 137 tests green (3 new regression tests).
- 👤 Field tested on charm_website: pipeline without designer **worked** ($1.56, coder even updated the project's md files) but reviewer said NEEDS WORK; `--with-designer` run **failed** — designer timed out at 600s.
- 🐛 **Field bug #2 (designer/agy):** raw logs showed agy actively churning ~60 internal tasks and referencing a *different directory* (`~/Desktop/Projeler/aruvela-landing-page`) — its persistent cross-session "brain" (~/.gemini/antigravity-cli/) contaminated the run, then it went silent. Fix: `--new-project` now mandatory in AntigravityAdapter (isolated sessions verified on the real project: quality answer, <2 min, cited README line numbers). 137 tests green.
- 🔍 **Self-audit on user request.** Fixed: (1) worklog miscounted tests (said 138, was 137); (2) real gap — `ai resume` silently dropped the Designer when resuming a `--with-designer` run (flag now exists on resume too, regression-tested); (3) added GitHub Actions CI (ruff + full pytest on every push/PR — the suite was designed to run without AI access, now it does so automatically). Noted, not changed: `ai ask` bypasses the context system by design (escape hatch); no LICENSE (private repo — decide before ever going public); deep monorepos without marker files could still evade established-detection (markers cover realistic cases). 138 tests green (for real this time).

## 2026-07-12 · Session 2 — Publisher role (ADR-014)

- 👤 Pushed back that a prior "why not use CAO" claim felt unjustified, and posed a deeper question: how does the orchestrator decide which provider handles an action like git push, per-project, without wanting Claude Code specifically for that action?
- 🤖 Corrected the record: CAO evaluation and rejection (ADR-001) happened before any code was written and was explicitly approved by the user at project start; re-explained the reasoning. Then engaged the real question: proposed a new optional **Publisher** role — per-project opt-in, independently provider-assignable from the Coder, following the exact Designer pattern (no CAO/dynamic-supervisor needed — a static per-project config entry gives a *guarantee*, which a runtime LLM router cannot).
- 👤 Chose via AskUserQuestion: **prepare-only** — the stage drafts commit message + PR description, never runs git itself (extends the ADR-007 trust boundary consistently rather than escalating it).
- 🤖 Built ADR-014 + `publisher.md` template + contract (`context/contracts.py`) + `defaults.yaml` entry (opt-in, `enabled: false`) + `--with-publisher` flag on both `ai run` and `ai resume`. Updated 5 existing tests that hardcoded "4 stages"; added dedicated gating tests including cross-provider proof (new `FakeAltAdapter` fixture, `fake_alt` provider) showing Publisher and Coder can run on genuinely different providers by config alone.
- ✅ **Live-verified on real infrastructure**: `ai --with-publisher "add a default parameter..."` — Codex drafted a proper Conventional-Commits message + PR description citing the reviewer's APPROVE verdict; `git log` showed only the original commit — publisher touched nothing. 142 tests green.
- 👤 Asked to confirm/ensure Publisher (and git/GitHub operations generally) are disabled by default. 🤖 Verified: already true (defaults.yaml `enabled: false`, test passing) and already architecturally incapable of touching git regardless. Strengthened the docs so the guarantee is unmissable rather than buried: added a standing-guarantee callout to ADR-014 itself, a new bold paragraph in README's Trust Model section, a matching note in MVP.md §7, and reordered MANUAL_TESTING's Publisher section to lead with the safety guarantee before the motivation story.

## 2026-07-12 · Session 2 — Session Chaining (ADR-015): the founding token-savings feature, finally shipped

- 👤 Two pointed questions: (1) is a live back-and-forth between stages (Coder asks Codex a question mid-task) possible? (2) tokens are still too high — the whole reason for building this was to save tokens, and it doesn't feel like it's happening.
- 🤖 Answered honestly rather than defensively: (1) technically possible in a bounded form, but every round trip is a fresh invocation — likely the MOST expensive pattern, not a saving, and cross-provider rounds have zero session to resume; connected it directly to (2) since the two goals conflict. (2) Grepped the actual engine code live and found the real gap: both adapters already build correct `--resume` flags, but `core/engine.py` never threads a session id from one stage into the next — the roadmap's #1 item had never been wired up despite sitting there since M2.
- 🤖 Proposed two options: same-provider session chaining (recommended) vs. a "single-provider cheap mode." 👤 **Rejected single-provider mode outright and correctly**: "if we use only one provider, why use your orchestrator at all? I could type into Codex CLI directly." This is decisive — it's exactly why chaining (same providers, no change to which model does which job) is the right fix and single-vendor collapse is not.
- 👤 Instructed: push all existing work to `main` as a clean baseline first (cold start), then branch for this feature. 🤖 Verified `main` local/remote were already in sync (`fceb5ba`), created and pushed `feature/session-chaining`.
- 🤖 Implemented: `provider_sessions: dict[str, tuple[session_id, allow_edits]]` tracked per PROVIDER NAME (not stage adjacency) across a run, seeded from history on `ai resume`; chains only when the adapter reports `supports_resume` AND the prior session's `allow_edits` matches the current stage's. New `pipeline.session_chaining` config flag (default `true`, opt-out-able per project).
- 🐛 **Field bug found during live verification:** `codex exec resume` rejects `-s/--sandbox` outright ("error: unexpected argument '-s' found") — a resumed Codex session keeps the sandbox mode it was created with. Fixed in `CodexAdapter.build_invocation` (omit `-s` when resuming); this is exactly why the `allow_edits`-matching guard above was built, not left for later — it's what prevents a stage from silently inheriting the wrong write-access level.
- ✅ **Live-verified on real infrastructure** (`--with-publisher`, all 5 stages): `run.json` showed the **identical Codex session id** across Planner→Reviewer→Publisher — one continued conversation. Cached-token ratio *rose* through the chain (70% → 83% → 84%), meaning each later stage's fresh, full-price cost stayed roughly flat instead of re-paying for repo exploration from zero. 150 tests green (6 new unit tests incl. the mismatched-access regression + 1 new contract test).

## 2026-07-12 · Session 2 — ADR-016: Quota spread across three pools by task depth

- 👤 Clarified the real goal behind the token conversation: not reduction, *spread* — "it was once 10,000 tokens by Claude Code, presume — now 4,000 codex, 5,000 claude, 1,000 antigravity — same total, but separated. This is OK, they're all 10,000 in total." Proposed giving Antigravity the shallow, non-deep work (e.g. Publisher) specifically to draw from a third quota pool instead of piling onto Codex/ChatGPT.
- 🤖 Confirmed this matches the exact split already reasoned through: keep the chained Planner+Reviewer pair on Codex (they benefit from ADR-015's session continuity), keep Coder alone on Claude, and give the two shallow/bounded jobs — Designer (already there) and now Publisher — to Antigravity, a fully separate pool. Wrote **ADR-016**, changed `defaults.yaml` (publisher: codex → antigravity), verified no test hardcoded the old default.
- ✅ **Live-verified** (`--with-publisher`, real providers): `run.json` showed Planner and Reviewer sharing the identical Codex session id (chaining intact for the pair that benefits from it) while Publisher ran on Antigravity with no session tracked (by design — ADR-012's known limitation). Antigravity's actual draft was solid: proper Conventional Commits message + full PR description, correctly referencing a test file the Coder had proactively written. 150 tests still green (no test changes needed — none hardcoded publisher's provider).
- 📝 Updated living docs (ARCHITECTURE, MVP, MANUAL_TESTING) to describe the new default split; left ADR-015 and its worklog entries untouched as accurate historical record of the state *before* this change.

## 2026-07-13 · Session 2 — User guide (English + Turkish)

- 👤 Asked for a plain "how to use" guide, in English and Turkish, separate from the existing technical docs.
- 🤖 Wrote `docs/HOW_TO_USE.md` and `docs/HOW_TO_USE.tr.md` (natural Turkish, not machine-translated): what the tool is, prerequisites, install, first run, what you'll see, what's left behind, the cost/quota explanation (recurring point of confusion, restated clearly here), everyday commands table, the "never touches git" guarantee, per-project config recipes, resume-on-failure, and tips for good results. Linked from README's doc table as "Start here."

## 2026-07-13 · Session 2 — Honest reflection: "it's not like in my dreams..."

- 👤 Asked pointed questions about whether the orchestrator's results are really as good as using Claude Code directly: does Claude read the whole project, which models run, how much reasoning, is quality comparable.
- 🤖 Verified rather than asserted, from real run data: no file is ever inlined (Claude Code explores the actual repo with its own tools, same access as direct use); no model is ever pinned by the orchestrator (`model: null`/unset for all three providers) — a real coder run's raw JSON showed Claude Code itself mixing `claude-sonnet-5` and `claude-haiku-4-5` internally, exactly as it would unmanaged; Codex's `reasoning_output_tokens` field confirmed real reasoning happens at the CLI's own default effort, never throttled. Named the two honest, real differences from bare CLI use: (1) the Coder receives a plan first instead of the raw request, (2) it runs fully autonomous/unattended in one shot rather than supervised — no mid-task steering.
- 👤 Responded, unprompted: **"its not like in my dreams..."** — a genuine, vulnerable moment of reassessing the whole project after ~2 days of building.
- 🤖 Did not defend or rush to build. Asked what specifically was off. Named a hypothesis: the deterministic, no-agent-conversation architecture (ADR-001/004/006, chosen deliberately and approved early on) will always feel like a relay/handoff, not a team — that's inherent to decisions already made, not a bug. 👤 confirmed: **"both a bit"** — both the mechanics (handoff, not collaboration) and the payoff (token spend doesn't feel worth it) resonate.
- 🤖 Proposed a bounded, deterministic "fix-loop" as a candidate next feature: if the Reviewer's verdict isn't a clean APPROVE, give the Coder exactly one more turn with the specific findings, then stop regardless — closes the loop ("caught it and fixed it") without reopening the agent-conversation debate or losing cost predictability.
- 👤 Asked me to "think wisely" rather than just pick. 🤖 Went looking for real, already-existing evidence instead of speculating further: found that **`charm_website`'s run `2026-07-12_1140_0a83` already produced a real, unactioned `NEEDS WORK` verdict** — a genuine **blocker** finding (the Huawei AppGallery badge was wired to a text-only SVG placeholder instead of the official PNG asset the plan explicitly required) that has sat in `review.md` since 2026-07-12 with nothing done about it. This is concrete, first-party proof of the exact gap named above: the system caught a real, correctly-scoped problem and then nothing happened with that finding — directly validating (not just theorizing) that the fix-loop idea addresses a real, already-observed failure mode rather than a hypothetical one.
- ⏳ **Decision pending**: whether to build the fix-loop now (evidence-backed) vs. test on more real work first, or both. To be resumed.

## 2026-07-17 · Free/cheap alternatives for shallow tasks — evaluated, parked in IDEAS.md

- 👤 Asked whether "loop engineering" fits as a name/description for the app. 🤖 Answered no for now — the pipeline is a deterministic linear relay (that's why "Baton" fits); "loop engineering" only becomes earned if a bounded Reviewer→Coder fix-loop lands (which is exactly the ⏳ pending decision from 2026-07-13).
- 👤 Raised token cost of paid models on simple tasks; asked about free alternatives (repowise, opencode, aider) — evaluate only, don't implement. Ruled out local LLMs (no Ollama).
- 🤖 Premise-corrected first: git commit/push/branch cost zero tokens today (ADR-014 — no role runs git); the real targets are Publisher and `ai ask`. Evaluated all three: **opencode picked over aider** (scriptable `opencode run`, no git side effects; aider auto-commits and is the wrong shape for text drafting). Fetched and assessed **repowise** (github.com/repowise-dev/repowise): not a provider at all — a codebase-intelligence MCP server; index-only mode needs no LLM, so it's a token *reducer* attacking per-stage re-exploration overhead, complementary to ADR-015 chaining.
- 👤 Argued repowise helps the agent when starting a new project. 🤖 Nuanced: its intelligence derives from existing code + git history, so on greenfield it starts near-empty (ADR-013's propose-structure guidance covers that case); value ramps as the repo grows — init early is cheap, payoff is immediate only on established projects.
- 📝 Wrote **docs/IDEAS.md** (new doc: evaluated-but-not-decided ideas): opencode adapter for Publisher/`ask`, repowise as MCP context source, zero-LLM commit-message fallback, free-tier caveats (rate limits, data-training), suggested build order. Nothing implemented by request.

## 2026-07-21 · Shipped IDEAS.md build order steps 1–2: opencode + zero-LLM Publisher floor

- 👤 "so whats next? look at the MD under docs folder... usage repowise or free usage llms like opencode... think of it for future and token saving." Planned in plan mode; chose (via AskUserQuestion) the **full IDEAS.md roadmap** and, for the free-tier data-training risk, **confine opencode to shallow text only + document it**.
- 🤖 **Phase 1 — opencode adapter (ADR-017).** Probed the real CLI first (installed opencode 1.18.4): confirmed prompt rides in argv as a variadic positional (`run [message..]`), so pass it after a `--` separator (dash-leading prompts stay safe, shell=False); stdout is clean plain text, stderr is log noise; no tokens on stdout → honest-None usage; session id unreachable in default format → `supports_resume=False`. Wrote `providers/opencode.py` as a near-mirror of `antigravity.py`, registered it, added contract test + fixtures. Switched Publisher's default provider `antigravity → opencode` in `defaults.yaml`; `ai ask --role publisher` inherits it (provider is role-derived, no `ask.py` change). **Never** passes `--auto`/`--share`; the roles it serves are `allow_edits=False` by contract, so the shallow-text-only guardrail holds structurally, not just by advice.
- ✅ **Phase 1 live-verified:** `ai doctor` shows opencode healthy (1.18.4, used by publisher); `ai ask "Reply with exactly one word: PONG" --role publisher` routed through opencode and returned `PONG`.
- 🤖 **Phase 2 — zero-LLM Publisher floor (ADR-018).** Added a `deterministic` provider (`providers/deterministic.py`): conventional-commit message from `git diff HEAD --stat`, no model/quota/rate-limit. Stays inside the pure-adapter contract by delegating the git read to the transport; the stat→message transform (`message_from_diffstat`) is a pure function, unit-tested on fixtures. Infers type only where unambiguous (docs/test/chore), scopes to a common top-level dir (a repo-root file collapses it to no scope). Not a default — select per project: `roles: {publisher: {provider: deterministic}}`.
- ✅ **Phase 2 live-verified:** ran it through the real `HeadlessTransport` against this session's working tree → valid `chore: update 6 files` message, `usage=None`. It listed the 6 tracked/modified files and omitted the untracked new adapter files — the documented `git diff HEAD` floor limitation, behaving exactly as described.
- 📝 Wrote **ADR-017** and **ADR-018** in DECISIONS.md; graduated items 1 & 2 out of IDEAS.md (marked SHIPPED with pointers); added a free-tier caveat subsection to `HOW_TO_USE.md` + `.tr.md`. Full suite: **164 passed** (was 156; +8 new adapter tests). Deferred the opencode-fail → deterministic **auto-fallback** (needs engine retry plumbing).
- ⏳ **Phase 3 — repowise context reducer — not started.** It's the roadmap's largest item; its full MCP-backed form (3b) is gated on MCP context-provider support that the pipeline doesn't have yet (ARCHITECTURE §7.2). Near-term path 3a (inject `repowise distill` CLI output through the context layer, no MCP) is buildable next but involves a real external tool and a new context-injection pattern — left for a dedicated session.

## 2026-07-21 · Making baton conversational: `ai revise` + `ai publish` (ADR-019/020)

- 👤 Asked for a fundamentally different feel: not "send a message → it runs → done" but a back-and-forth — "make a correction, don't restart, then say push it. Should there be a chat?" 🤖 Named the fork honestly: a full `ai chat` mode would rebuild Claude Code weakly on top of the CLIs and dissolve baton's deterministic identity + quota-spread differentiator (and re-open ADR-001/004/006) — the same "handoff, not a team" nerve from 2026-07-13. Key reframe: **the conversational layer already exists — it's Claude Code driving baton**; what's missing is iterating on a run + a user-triggered publish.
- 👤 Asked "sence en mantıklı yol?" 🤖 Recommended **not** the chat rewrite: add two small commands (`revise` + `publish`), keep the chat in Claude Code. 👤 approved. Two design decisions settled via AskUserQuestion: `ai publish --push` stages **everything** (`git add -A`, with the file list shown before confirm); `ai revise` defaults to re-running **from the Coder** (`--from planner` to re-plan).
- 🤖 **`ai revise` (ADR-019).** New `PipelineEngine.revise` + a `carry_sessions` seed on `_run`: captures every succeeded stage's session id *before* the tail reset, so the re-run **Coder resumes its own Claude session** (`supports_resume=True`) and treats the correction as the next turn — while the Reviewer still re-chains to the Planner's Codex session. The correction is appended to `state.request` (the one channel that reaches the Coder, which doesn't get review.md by contract). New `revise.py` command (models resume.py) + `RunManager.latest_run_id()` + `RUN_REVISED` event; registered in app.py (incl. the load-bearing `_COMMANDS` argv-rewrite entry).
- 🤖 **`ai publish` (ADR-020).** New `publish.py`: preview-only by default (no git); `--commit`/`--push` are the **only git-writing code in the project** — a deliberate, user-triggered exception to ADR-014 (no *role* runs git; a human asks each time). Message precedence `-m` > last run's `commit_message.md` > fresh draft (publisher provider → deterministic fallback). Shows the file list + `typer.confirm` before writing; every git failure surfaced, never raised. Added `render_commit_draft`/`render_publish_plan` helpers.
- ✅ **Verified live + tests.** `ai revise` continues the same run-id (Coder resumed its own session; correction reached its prompt; app.py went x=1→x=2). `ai publish` preview touched nothing; `--commit --yes` committed and cleaned the tree; `--push` updated a bare remote; rejected confirmation committed nothing; not-a-repo → exit 2. **174 passed** (was 164; +2 engine revise, +3 revise CLI, +5 publish integration incl. a real remote).
- 📝 ADR-019 + ADR-020 in DECISIONS.md; HOW_TO_USE.md (+ `.tr.md`) gained a "correct it, then ship it" §8.1 and a reworded §9 (publish is the user-triggered git exception). This is the manual cousin of the still-parked "fix-loop".

