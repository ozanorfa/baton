# How to Use — AI Coding Orchestrator ("baton")

A practical, plain-language guide. For the technical design, see [ARCHITECTURE.md](ARCHITECTURE.md) and [DECISIONS.md](DECISIONS.md); for hands-on test commands, see [MANUAL_TESTING.md](MANUAL_TESTING.md). *(Türkçe için: [HOW_TO_USE.tr.md](HOW_TO_USE.tr.md))*

---

## 1. What is this?

A single command that turns a plain-English request into finished, reviewed code — by routing the work through several AI tools automatically, instead of you copy-pasting between them:

```bash
batonai "Add a dark mode toggle to the settings screen"
```

Behind that one line, four things happen in order: a **Planner** writes an implementation plan, a **Coder** implements it in your actual repository, a **Reviewer** checks the result against the plan, and everything is saved to disk for you to inspect. Each of these is a different AI (Codex, Claude Code) chosen for what it's good at — not one model doing everything.

**This tool never decides anything dynamically.** The order of stages, who does what, is fixed by a config file you can read. No hidden AI "supervisor" makes judgment calls about your workflow.

## 2. Before you start

You need, installed and logged in on your machine:
- `claude` (Claude Code)
- `codex` (Codex CLI)
- `agy` (Antigravity CLI)

Check all three at once:
```bash
batonai doctor
```
Every row should say `✓ healthy`. If one doesn't, fix that provider's login/install before continuing — the orchestrator does not work around a broken provider.

## 3. Install

```bash
git clone <this-repo>
cd <repo-folder>
uv tool install --editable .
```

This installs `batonai` as a command you can run from **any folder**, not just this one. (The package itself is called `ai-orchestrator` — that's the name to use with `uv tool list` or `uv tool uninstall`.) Because the install is "editable," future updates to this codebase apply automatically — no reinstalling needed.

## 4. Your first run

Go to your project and type the command by itself:

```bash
cd your-project              # any real project, ideally a git repo
batonai
```

That's the whole thing. `batonai` on its own opens a short guided session:

```
  baton — AI coding pipeline

  scanning your-project/ …
  ✓ providers  all healthy
  ✓ project    Python (pyproject.toml)
  ✓ git        clean
  ⚠ baton      not set up in this folder yet
  ✓ health     code hotspots found (repowise)
       src/core/engine.py — score 2.4/10, max complexity 26, nesting 4

  Set up baton in this folder? [Y/n]
```

It checks that your AI tools are working, figures out what kind of project this is, offers the one-time setup if it's missing, and only then asks what you want done. You don't need to remember any of the individual commands below — but they all still exist if you prefer typing them (§8).

**What it's telling you:**
- **providers** — your AI CLIs are installed and logged in. If one isn't, the session stops here and says which; nothing is asked or spent.
- **baton** — whether this folder has been set up yet. Answering yes creates `.ai/config.yaml` and `.ai/project.md` for you.
- **health** — the most complex/risky existing files, from a static analysis (no AI, no tokens). Every stage is told about them so it treads carefully there. If you don't have the `repowise` tool installed, this line simply doesn't appear — nothing breaks.

Press Ctrl-C at any question to back out; nothing is created or changed.

**One file worth your time afterward:** open `.ai/project.md` and add a few honest lines about your conventions — "we use Riverpod, not setState," "tests live in test/," anything an AI assistant tends to get wrong. Every stage reads it on every run, so a few good lines here pay off repeatedly.

*(Piping or running in CI? `batonai` with no arguments prints help instead of prompting, so scripts never hang.)*

## 5. What you'll see while it runs

```
run: your request here
planner → designer (off) → coder → reviewer → publisher (off)
  ✓ planner → plan.md in 20s
  ○ designer skipped (disabled)
  ✓ coder → changes.md in 45s
  ✓ reviewer → review.md in 15s
                    run 2026-...
┏━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━┓
┃ stage    ┃ provider ┃ duration ┃ tokens in/out ┃ status ┃
┗━━━━━━━━━━┻━━━━━━━━━━┻━━━━━━━━━━┻━━━━━━━━━━━━━━━┻━━━━━━━━┛
reviewer verdict: APPROVE
run succeeded · artifacts: .ai/runs/<run-id>/artifacts
```

A run typically takes 1–5 minutes and touches real files in your repository — the Coder stage genuinely edits code, the same as if you'd asked it directly.

## 6. What's left behind afterward

- **The actual code changes**, sitting uncommitted in your working tree — review them with `git diff`, same as any change you'd made yourself.
- **`.ai/runs/<run-id>/`** — everything about that run:
  - `artifacts/plan.md`, `changes.md`, `review.md` — what each stage produced, in plain English
  - `artifacts/diff.patch` — exactly what the Coder changed
  - `report.json` — the same summary as the terminal, as data
  - `prompts/` — the *exact* text each AI was given (useful if a result seems off)
  - `logs/` — raw output per stage, for debugging

**No pipeline run ever commits or pushes** — reviewing stays your job. Committing is too, unless you explicitly run `batonai publish --commit`/`--push` yourself (§8.1). See §9.

## 7. Understanding the cost/quota number

After a run you'll see something like:
```
totals: tokens 400,123/8,500 · measured cost $0.85*
* cost = provider-reported API-equivalent value; on subscription plans it consumes plan quota — no per-run charge
```

**If you're on a subscription** (Claude Pro/Max, ChatGPT Plus) — that dollar figure is **not a bill**. It's the API-equivalent value of the work, shown for reference; what actually happens is your plan's included usage quota goes down a bit, the same as any other conversation with that tool. You only pay real money if you're specifically using pay-per-token API keys.

A full run typically "costs" $0.20–1.50 of quota-equivalent — mostly fixed overhead (each AI re-familiarizing itself with your project), which barely grows with how big the actual task is. So this tool is not the right hammer for one-line changes — use `batonai ask` instead (§8) for anything trivial.

### The Publisher runs on a free client — a caveat

The optional Publisher stage (and `batonai ask --role publisher`) is wired to **opencode**, a free command-line client, to keep this shallow "draft a commit message from the diff" work off your paid plans entirely. opencode is a free *client*, but the model still comes from somewhere — you point it at a free tier (an [OpenRouter](https://openrouter.ai) `:free` model, a Google AI Studio free-tier key, or an opencode promo model) via opencode's own `opencode auth`. Two things to know:

- Free tiers are **rate-limited** and typically **may train on the data you send them**. That's fine for a commit message; it's why the Publisher only ever sees the *diff and the plan*, never gets pointed at your whole codebase — and why the code-reading stages (Coder, Reviewer) are never routed here.
- If you'd rather not use a free tier at all, override the Publisher's provider per project (e.g. `roles: {publisher: {provider: codex}}` in `.ai/config.yaml`).

## 8. Everyday commands

| Command | What it does |
|---|---|
| `batonai` | **The guided way in** (§4): scans the project, offers the setup it finds missing, asks what you want, runs it. Everything below, without having to know it |
| `batonai "<request>"` | Run the full pipeline |
| `batonai --with-designer "<request>"` | Also run the Designer stage (UI/UX planning) for this one run |
| `batonai --with-tester "<request>"` | Also run your project's tests after the Coder (zero tokens) and hand the result to the Reviewer — set the command with `providers: {testrunner: {command: "..."}}`, or let it auto-detect |
| `batonai --with-publisher "<request>"` | Also draft a commit message + PR description (never runs git itself — see §9) |
| `batonai --health "<request>"` | Tell every stage which existing files are code-health hotspots (complexity/nesting), so they tread carefully there. Needs the `repowise` tool installed; adds ~4s and a temporary index — off by default (ADR-025) |
| `batonai ask --role coder "<question>"` | One cheap, one-shot call to a single AI — no pipeline, no artifacts. Good for small questions or tiny edits |
| `batonai health` | Show which files baton considers code-health hotspots (the same text every stage receives). Free, no run needed — needs `repowise` installed |
| `batonai doctor` | Check that all providers are installed and logged in |
| `batonai init` | Set up `.ai/` in a project (safe to run again; never overwrites your edits) |
| `batonai config show` | See the full effective configuration and where every value came from |
| `batonai runs list` | See every past run in this project: status, cost, verdict |
| `batonai runs show <run-id>` | See one run's detail |
| `batonai resume <run-id>` | Continue a failed run from where it stopped — earlier successful stages are never redone or repaid |
| `batonai revise "<correction>"` | Iterate on the **last** run without starting over — the Coder picks up its own session and applies your correction, then the Reviewer re-checks (see §8.1) |
| `batonai review` | Send your current uncommitted changes to the Reviewer for a second opinion — no pipeline, changes nothing. `-m "focus on X"` to steer it |
| `batonai publish` | Show a drafted commit message (no git). Add `--commit` to commit, `--push` to commit + push — the only command that touches git, and only when you ask (see §8.1) |

## 8.1 The "correct it, then ship it" flow

The pipeline runs once and stops — but you rarely get everything right on the first pass. Two commands close that loop so you can work conversationally:

```bash
batonai "add a settings screen"          # 1. run it
git diff                            # 2. review what the Coder did
batonai revise "make the header sticky"  # 3. not quite right? correct it — same run, no restart
                                    #    (the Coder remembers its own work; --from planner re-plans)
batonai publish --push                   # 4. happy? commit everything and push (asks you to confirm first)
```

`batonai revise` continues the **last** run: it reuses the plan and re-runs from the Coder, which resumes its own session and treats your correction as the next turn — then the Reviewer looks again. Repeat as many times as you like. When you're satisfied, `batonai publish` drafts the commit message and — only with `--commit`/`--push`, and only after you confirm — actually commits (`git add -A`) and pushes.

**Want that first correction to happen automatically?** Add `--fix-loop` to the run: if the Reviewer's verdict comes back `NEEDS WORK` (a blocking problem), the tool runs **one** automatic fix pass — the same "re-run the Coder with the findings" that `batonai revise` does by hand — then stops. It's off by default (that extra pass costs quota); turn it on per run with `batonai --fix-loop "..."`, or per project with `pipeline: {fix_loop: true}` in `.ai/config.yaml`.

## 9. What this tool will never do (read this once)

- **No pipeline stage ever runs git.** The pipeline never commits, pushes, or touches GitHub on its own — not by default, not with any flag. Even the optional Publisher stage only *writes a text draft*. The **one** way git gets run is when **you** type `batonai publish --commit`/`--push` yourself — a separate, explicit command that shows you exactly what it will commit and asks you to confirm first (§8.1). Nothing reaches your history without you asking for it, each time.
- **The Coder stage edits your files without asking permission each time** (that's the whole point — otherwise you'd have to approve every change by hand). The safety net: start from a clean `git status` (the tool warns you if you don't), review the diff before committing, and let the Reviewer stage's findings guide you.
- If that trust level doesn't fit a particular project, use `batonai ask` instead — it only answers, it never edits anything.

## 10. Making it fit your project

Everything below goes in that project's own `.ai/config.yaml` — never requires touching this tool's code.

**Turn on the optional stages permanently** (instead of typing the flag every time):
```yaml
roles:
  designer: {enabled: true}
  publisher: {enabled: true}
```

**Use a smaller/cheaper Claude model** (for lower-stakes projects):
```yaml
providers:
  claude: {model: haiku}
```

**Skip stages you don't want** (e.g. no review step):
```yaml
pipeline:
  stages: [planner, coder]
```

**Change which AI does a job** — every role's provider is independent:
```yaml
roles:
  coder: {provider: codex}     # e.g. if you'd rather not use Claude for this project
```

## 11. When something fails

The run stops at the failed stage — nothing after it runs, nothing already done is lost. You'll see the cause and a suggested next step:
```
next steps: batonai resume <run-id> · batonai doctor
```
Run `batonai resume <run-id>` and it picks up exactly where it stopped, re-using everything that already succeeded — you never pay twice for the same work.

## 12. Getting good results

- Fill in `.ai/project.md` honestly — it's the single highest-leverage file for both quality and cost.
- Start every run from a clean `git status`.
- For small tasks, use `batonai ask`, not the full pipeline.
- Read `review.md` — it sometimes catches real bugs the Coder itself missed (that's the whole point of using two different models).
- If a run's plan or code looks confused, check `.ai/runs/<id>/prompts/` to see exactly what that stage was told — usually explains why.
