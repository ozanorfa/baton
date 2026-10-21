# Contributing to batonai

Thanks for looking. This is a small project with strong opinions written down; the
fastest way to a merged change is to read two things first:

- [docs/DECISIONS.md](docs/DECISIONS.md) — every design choice and *why*. If your
  change contradicts an ADR, open an issue to discuss before writing code; a new ADR
  may be the right first step.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — layers and the dependency rules
  between them (provider adapters are pure, the transport knows nothing about AI,
  the engine routes from config and never from a model).

## Workflow

`main` is protected: nothing lands without a pull request and green CI.

```bash
git clone https://github.com/ozanorfa/baton && cd baton
uv sync
git switch -c my-change

uv run ruff check .    # lint
uv run pytest          # 348 tests; needs NO AI access, NO provider CLI, NO network
uv build               # packaging must stay valid
```

Open the PR against `main`. CI runs the same three commands on Ubuntu and macOS.

## What a good PR has

- **A test for the behaviour.** Engine/routing/config changes → `tests/unit`;
  anything a user can trigger → `tests/integration` on the fake provider
  (`tests/integration/fake_provider/`, driven by `[[directives]]` in the prompt);
  adapter changes → `tests/contract` against a *recorded real* CLI output.
- **No real provider in tests.** A fixture that resolves to a real CLI passes on a
  machine that has it installed and fails everywhere else (it happened — see
  WORKLOG 2026-10-21). If a fixture touches `publish`, pin
  `roles: {publisher: {provider: deterministic}}`.
- **Docs that match.** User-visible behaviour → `docs/HOW_TO_USE.md` *and*
  `docs/HOW_TO_USE.tr.md`; a design decision → a new ADR in `docs/DECISIONS.md`;
  a release-worthy change → a line under *Unreleased* in `CHANGELOG.md`.
- **The trust model intact.** No pipeline stage may ever run `git commit`,
  `git push` or any remote operation (ADR-014). `batonai publish` is the one
  user-invoked exception (ADR-020). PRs that weaken this will not be merged.

## Adding a provider

Adapters are plugins (ADR-009): a `ProviderAdapter` subclass registered under the
`ai_orchestrator.providers` entry-point group. Built-ins live in
`src/ai_orchestrator/providers/`; `claude.py` and `codex.py` are the reference
implementations. Record a real `--version` and one real run of the CLI as fixtures
under `tests/contract/fixtures/<name>/` so `parse()` is tested without a subprocess.

## Reporting a bug

Include the run directory's `report.json` and the relevant `logs/*.stderr` from
`.ai/runs/<run-id>/` — they contain no secrets, only the provider's raw output —
plus `batonai --version` and `batonai doctor`.
