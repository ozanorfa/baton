# Manual Testing Guide

Commands you can run yourself to check the orchestrator, grouped by the milestone that introduced them. Grows with every milestone. All commands run from the project root:

```bash
cd ~/Desktop/ai/ai-agent-test
```

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

## Exit codes (for scripting)

| code | meaning |
|------|---------|
| 0 | success |
| 1 | a provider/stage failed |
| 2 | configuration or usage error |
