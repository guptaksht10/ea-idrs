# Contributing to EA-IDRS

This is a research repository. Every result we present has to trace back to a
commit, a config and a run folder, so the workflow below is strict on purpose.

## 1. Set up (once)

```bash
# Install uv: https://docs.astral.sh/uv/  (Windows: winget install astral-sh.uv)
uv python install 3.12
uv sync --all-groups          # creates .venv from uv.lock (exact versions)
uv run pytest                 # must pass before you start
```

There is no `make` on our Windows machines, so every task is a plain `uv run` command.

| Task | Command |
|---|---|
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format .` (CI runs `--check`) |
| Types | `uv run mypy` |
| Architecture contracts | `uv run lint-imports` |
| Tests + coverage | `uv run pytest --cov` |
| All CI checks | `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest` |

Add a dependency only when it is needed, with `uv add <pkg>` (or `uv add --group dev <pkg>`),
and say why in the PR. Commit both `pyproject.toml` and `uv.lock`.

## 2. Branches (GitHub Flow)

- `master` is the default branch and must always pass CI. Never commit to it directly.
- One short-lived branch per issue, named `<type>/<issue-number>-<short-description>`:
  - types: `feat`, `fix`, `exp`, `docs`, `chore`, `refactor`, `test`
  - examples: `feat/12-cicids-data-pipeline`, `exp/20-baseline-xgb-lgbm`, `docs/31-data-card`
- Keep branches to 3–4 days at most. Split big work into several PRs.

## 3. Commits (Conventional Commits)

```
<type>(<scope>): <imperative summary>
```

Examples: `feat(data): add chronological split`, `fix(data): handle Infinity in Flow Bytes/s`,
`test(data): add split leakage tests`, `docs(research): record class-by-day audit`.
Scopes we use: `data`, `features`, `model`, `explain`, `dashboard`, `tracking`, `ci`, `docs`, `research`.

## 4. Pull requests

1. Open the PR early as a **draft**, then mark it ready when CI is green.
2. Fill in every section of the PR template. Paste the **actual** test output.
3. At least **one other member** must approve. Never approve your own PR.
4. Reviewers respond within 24 hours on weekdays.
5. Merge with **squash merge**. The PR title becomes the commit message, so it must follow
   Conventional Commits.
6. Delete the branch after merging.

## 5. Research rules (non-negotiable)

- **Chronological splits only.** No random train/test split, not even "just to try".
- **Fit on train only.** Any fitted transformer, threshold or reference statistic uses the
  training split (thresholds and model selection: validation split).
- **The test split is sealed.** Do not load it until the test protocol is approved.
- **Label firewall.** Monitoring and alerting code never receives true labels (ADR-0004).
- **No invented numbers.** A metric appears in docs or slides only if a run folder in `runs/`
  produced it. Until then write `PENDING`. Results on fixtures or subsets are labelled
  *synthetic* or *smoke test*.
- **Record failures.** Failed or discarded runs go in `docs/experiment-log.md` too.
- **Never commit** datasets, model binaries, run folders, `.env` files or notebook outputs.

## 6. Notebooks

Notebooks are for exploration only (`notebooks/NN_initials_topic.ipynb`). Clear outputs before
committing. Anything reused moves into `src/eaidrs/` with a test.
