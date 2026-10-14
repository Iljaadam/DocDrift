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

- **$0 personal spend.** Only granted free credits. No live Nebius call
  (inference or Sandbox) until the user confirms credits are granted and
  personal charges are impossible. Live Sandbox mutations have no enable
  switch on purpose. Inference has a `--live` flag (`repair`, `evaluate`):
  never pass it without that confirmation.
- Never claim more than happened: label owned fixtures as fixtures, the
  constructed bad-patch challenge as constructed, synthetic API fixtures as
  synthetic. No invented results.
- Don't touch NewsBias (`/home/ubuntu/news-bias-tracker`), its timers,
  containers, or ports 80/443/8501. Host is aarch64.
- Don't build the HTML review page before a real model repair passes
  independent checks.

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
```

Run state lives in `.docdrift/` (gitignored).

Token Factory key: `~/.config/docdrift/nebius.env` (mode 600, outside the
repo; $1 trial). Load with `set -a; . ~/.config/docdrift/nebius.env; set +a`.
Never print it, commit it, or copy it into the repo.

## Handoff protocol (end of every session)

1. Tick/adjust items in the `STATUS.md` checklist.
2. Add one dated line to `STATUS.md` → **Session log**: what changed, what
   is next, anything blocked.
3. Make sure the test suite passes, then commit with a descriptive message.
