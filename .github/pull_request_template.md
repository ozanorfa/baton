## What

<!-- one or two sentences: what changes and why -->

## Checks

- [ ] `uv run ruff check .` and `uv run pytest` pass locally (no provider CLI needed)
- [ ] a test covers the behaviour (unit / integration on the fake provider / contract fixture)
- [ ] docs updated where a user would notice (HOW_TO_USE en + tr, CHANGELOG *Unreleased*, an ADR if this is a design decision)
- [ ] no pipeline stage gained the ability to run git or reach a remote (ADR-014)
