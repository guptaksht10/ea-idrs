## Summary
<!-- What changed, in 2–4 lines. -->

## Why
<!-- Problem or task this solves. -->

Closes #<!-- issue number -->

## Files changed
<!-- Main files/folders. Skip lockfile and generated noise. -->

## How it was tested
<!-- Paste the exact commands you ran and their actual result (pass/fail counts). -->
```
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
```
Result:

## Evidence
<!-- Run folder (runs/<id>), screenshot of the running app, metrics file path. Write N/A if none. -->

## Research-methodology impact
<!-- Does this change splits, preprocessing, labels, metrics or thresholds? If yes, explain and link the ADR. Otherwise write "None". -->

## Checklist
- [ ] Tests added or updated, and they pass locally
- [ ] CI is green
- [ ] No labels reach monitor / explain / model inference code (label firewall, ADR-0004)
- [ ] Split stays chronological; preprocessing is fitted on train only; test split stays sealed
- [ ] Tunable numbers come from `configs/`, not constants
- [ ] No dataset files, model binaries, run folders, secrets or notebook outputs committed
- [ ] Docs / ADR / checklist updated if behaviour or a decision changed
- [ ] Every number in the description comes from an actual run (no estimated or placeholder metrics)
- [ ] Reviewed by a team member other than the author
