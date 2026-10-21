# Evaluation — does the pipeline beat a single session?

**Status:** Protocol defined 2026-10-21 (ADR-036) · **no results yet** · results are appended below as they are produced, never edited after the fact.

This project claims that routing work through a Planner → Coder → Reviewer pipeline on two different models produces better, safer code than one model in one session. Until this page has data, that is a hypothesis. Nothing on the roadmap is worth building before it is tested.

## The question

For a typical mid-size task on a real project, compared with plain Claude Code in a single interactive session:

1. Does the Reviewer catch **real defects** the Coder left behind?
2. Is the result **more often committable as-is** (your judgement, after reading the diff)?
3. What does it **cost** in quota and wall-clock time?

## Protocol

**Project.** A real repository you know well, with a test suite that runs. Start every task from a clean `git status` on a dedicated branch.

**Tasks.** Four or five, each touching one to three files and finishable in one sitting. Cover the shapes real work has:

| # | Shape | Example |
|---|---|---|
| 1 | Feature | add a settings toggle with persistence |
| 2 | Bug fix | a reported crash with a reproducible input |
| 3 | Refactor | extract a widget / split a 300-line function, behaviour unchanged |
| 4 | Tests | add tests for an existing untested module |
| 5 | (optional) Cross-cutting | rename a concept across the codebase |

**Two arms per task, same wording, same starting commit.**

- **A — single session:** Claude Code interactively, your normal way of working. Note the API-equivalent cost it reports and the time.
- **B — batonai:** `batonai "<same request>"` with `providers: {claude: {allow_commands: true}}` in `.ai/config.yaml` so the Coder can run the tests (ADR-034). Do not intervene; if the verdict is NEEDS WORK, run **one** `batonai revise` and count both runs.

Run the arms in alternating order across tasks (A then B, B then A, …) so neither benefits from you having seen the problem already.

**Record per arm.** Arm B's numbers come from `batonai runs export` (a Markdown row per run: wall time, tokens, cost, verdict, findings by severity, files and lines changed). Arm A's you note by hand from the session.

| Field | Meaning |
|---|---|
| tests | pass / fail after the arm finished, with the project's own suite |
| diff | files changed, +/- lines |
| cost | API-equivalent $ the tool reported (quota on subscription plans) |
| time | wall-clock from request to usable result |
| reviewer findings | B only: blocker / major / minor counts, and **how many were real** after you checked each |
| verdict | B only |
| commit as-is? | yes / with small edits / no — your call after reading the diff, blind to which arm if you can arrange it |

## Results

*(append one block per task; keep the raw `runs export` rows)*

### Task 1 — …

| arm | tests | diff | cost | time | reviewer findings (real/claimed) | commit as-is? |
|---|---|---|---|---|---|---|
| A single session | | | | | — | |
| B batonai | | | | | | |

Notes:

## Reading the outcome

- Reviewer findings that were **real** and that arm A shipped: the pipeline's whole justification. Count them.
- B costs more per task by construction (two models, fixed per-stage overhead). The question is whether what it buys is worth it, not whether it is free.
- If after five tasks the Reviewer found nothing real and "commit as-is" is a tie, say so here and let the roadmap follow: baton is then a quota spreader with good bookkeeping, which is a smaller product and an honest one.
