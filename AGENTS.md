# Repository instructions for AI assistants

## Read first

Read `README.md`, `PROTOCOL.md`, `CONTRIBUTING.md`, `shared/OBJECTIVE.md`,
`shared/GLOBAL_STATUS.md`, and your workspace's `HANDOFF.md` before changing research code.
The original design is in `docs/project-plan.md`; executable capabilities are documented in README.

## Current phase and scope

- This branch contains ghj's calibrated research pipeline: all baselines, references, full-budget
  campaigns and reserved-stage gates are implemented. Read agents/ghj/HANDOFF.md and COMPLETION.json
  (when present) for actual executed activity; the protocol's phase field stays frozen for hash stability.
- Validate the full development loop with `uv run --locked --exact python scripts/validate_pipeline.py --prepare`.
  Round-capped infrastructure results never enter the scientific leaderboard.
- The current study's code, costs and method configurations are frozen. Shared-core changes require
  a protocol revision and rerunning affected controls; never retune from confirmation/test outcomes.
  A readiness check does not replace scientific evidence or another member's review.
- During candidate search, modify your own `agents/<name>/` directory. Propose shared-core changes
  separately; increment protocol version and rerun affected baselines before comparing results.
- There are four peer workspaces (`zzr`, `zzw`, `ghj`, `xyk`), with no permanent research assignments.
- A 12-hour autonomous session is an optional per-agent budget. This file does not authorize starting
  agents, long-running jobs, scheduled tasks, or external writes without a corresponding user task.

## Scientific integrity

- Optimize mean client Macro-F1 under one fixed **simulated** training time budget.
- Never replace unknown measurements with zero or fabricated scores; use JSON `null`.
- Data splits, costs, model/local training and evaluation rules are shared protocol inputs.
- Candidate policies only receive allowed device metadata and paid historical training feedback.
  They must not read validation/test labels or unselected clients' current loss.
- Search uses the 20-client open validation subset. The 10-client confirmation subset and final
  30-client tests are reserved for the frozen-candidate campaign.
- Keep complete failures and negative results. Do not silently delete unfavorable published records.
- `agents/*/runs/*.json` are immutable, finalized summaries. Correct an error with a new run and a
  `supersedes` reference. Large artifacts remain outside Git with a retrievable URI and checksum.
- Never hand-edit `shared/LEADERBOARD.md`, `shared/GLOBAL_STATUS.md`, or
  `shared/EXPERIMENT_INDEX.jsonl`; regenerate them using the local synchronization script.
- Champion promotion requires review of paired evidence. No script currently promotes automatically.

## Engineering and handoff

- All members must use uv 0.12.23 and the checkout-local `.venv`, with CPython 3.11.17.
  Run `uv sync --locked`, then run project commands with `uv run --locked --exact`.
  Read `docs/environment.md`; never install ad hoc packages into the shared experiment environment.
- Version changes require pyproject/lock/pin/policy consistency plus environment smoke and regression
  tests. Call `configure_cpu_runtime` before numerical work in future runners.
- Run `uv run --locked --exact python scripts/check_repo.py`, the unittest suite, and
  `uv run --locked --exact python scripts/sync_leaderboard.py --check` for relevant changes.
- Update docs when changing interfaces or commands. Generic collaboration tools use the standard
  library; research environment checks and smoke use the locked numerical dependencies.
- Save the runnable version, exact configuration, commit, evidence and next step in your HANDOFF.
- Do not overwrite other members' work or reset their branches. Shared integration happens through PRs.
- Do not commit credentials, raw data, model weights or large experiment logs.
- The initial scaffold is local pending the user's review. Push only after the user's authorization;
  later collaboration follows their standing authorization and `docs/collaboration.md`.
