# DocDrift — agent entrypoint

Shared by Claude Code (`CLAUDE.md` imports this file) and Codex. Edit only
this file.

## Goal

Place well in the Nebius Global AI Hackathon, **Coding and Agentic
Engineering** track. DocDrift is a Python CLI that repairs one broken
documentation example with an NVIDIA Nemotron model (Nebius Token Factory),
verifies the repair in Nebius Sandboxes, and exports evidence.

- **Submission deadline: October 30, 2026, 17:00 UTC.**
- Judges must be able to test it for free through **December 15, 2026**.
- Judging weighs implementation, design, impact, and idea equally.

This is a pet project: skip ceremony, optimise for a working, honest,
demo-able submission.

## Read order for a new session

1. This file.
2. `STATUS.md` → the **Checklist** at the top tells you what to do next.
3. `ARCHITECTURE_PLAN.md` only as needed, by section (grep `^## `). It holds
   the full milestone criteria, the 14-case evaluation, video script, and
   the order to cut scope.
4. `docs/*.md` for details. `docs/MODEL_REPAIR.md` covers the Nemotron repair
   loop and evaluation harness; `docs/SUBMISSION_DRAFT.md` and
   `docs/FEEDBACK_LOG.md` are the submission drafts.

## Hard rules

- **$0 personal spend.** Only granted free credits.
  - Inference: approved by the user on 2026-10-14 for the $1 Token Factory
    trial key (`--live` on `repair`/`evaluate`). On 2026-10-15 the user reported
    promotional credits already on the account, approximately $30 (exact balance
    and expiry unverified). Keep runs small and log token use.
  - Sandboxes: user approved one read-only `GET whoami` on 2026-10-16; it
    succeeded (feedback log F7). Further live calls require scoped approval.
    Resource creation/execution is not approved, credit coverage is unverified,
    and live Sandbox mutations have no enable switch on purpose.
- Never claim more than happened: label owned fixtures as fixtures, the
  constructed bad-patch challenge as constructed, synthetic API fixtures as
  synthetic. No invented results.
- Don't touch NewsBias (`/home/ubuntu/news-bias-tracker`), its timers,
  containers, or ports 80/443/8501. Host is aarch64.

## Commands

```bash
uv sync --extra dev --locked
uv run --no-sync pytest -o addopts=""      # plain -q hides the summary line
uv run --no-sync docdrift demo --inspect-only
uv run --no-sync docdrift demo --image python:3.12-slim   # local Docker slice
uv run --no-sync docdrift sandbox-contract-demo           # offline, no creds
uv run --no-sync docdrift challenge                        # bad-patch rejection
.venv/bin/python scripts/check_distribution.py --build --dist-dir /tmp/docdrift-dist --cache-dir /tmp/docdrift-uv-cache
uv run --no-sync docdrift evaluate --strategies execution_only    # baseline, local Docker
uv run --no-sync docdrift repair --strategy agent --replay r.json # synthetic rehearsal
uv run --no-sync docdrift review <run-id>                    # saved evidence, no execution
uv run --no-sync docdrift review-evaluation saved.json       # saved comparison, no execution
uv run --no-sync docdrift verify-evidence evidence.zip       # offline hashes, no extraction
uv run --no-sync docdrift evaluate --execution-backend sandbox-simulation # synthetic HTTP only
```

Run state lives in `.docdrift/` (gitignored).

Commits: no git identity is configured on this machine. Reuse the repo's author:
`git -c user.name=Iljaadam -c user.email=64214807+Iljaadam@users.noreply.github.com commit ...`

Token Factory key: `~/.config/docdrift/nebius.env` (mode 600, outside the
repo; same key, user reports about $30 credits on 2026-10-15). Load with
`set -a; . ~/.config/docdrift/nebius.env; set +a`.
Never print it, commit it, or copy it into the repo.

## Handoff protocol (end of every session)

1. Tick/adjust items in the `STATUS.md` checklist.
2. Add one dated line to `STATUS.md` → **Session log**: what changed, what
   is next, anything blocked.
3. Make sure the test suite passes, then commit with a descriptive message.
4. Record new decisions in `STATUS.md` → **Decisions** (who, when, what).
