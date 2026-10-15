# Model repair and evaluation harness

Built offline on October 14, 2026, then exercised with live Nemotron inference
on Token Factory the same day (`docs/FEEDBACK_LOG.md` F1–F5). Synthetic scripted
responses and contract doubles remain separately labelled. All runtime
verification so far uses local Docker; live Sandbox access is unverified.

## Strategies (`src/docdrift/repair.py`)

| Strategy | What the model gets | Candidates |
|---|---|---|
| `one_shot` (baseline) | System prompt, the full Markdown document, the broken fence, the observed failure. One call, no tools. | 1 |
| `agent` | Same context plus tools: `list_files`, `read_file` (pinned snapshot only), `run_python` (isolated sandbox, first input), `submit_replacement`. | 2 |

The model never sees the profile, expected outputs, checks, or known repair.
For exit-zero drift it gets the observed stdout and a sentence saying the
output does not match the documentation, never the expected value.

Every submission passes `policy.apply_replacement` (same static gate as manual
repairs). The accepted replacement then goes through the unchanged engine:
original failure reproduction, healthy baseline, pristine final verification,
healthy regressions, evidence export. `repair.json` (outcome, candidates,
transcript, usage) is hashed into run metadata and added to the evidence ZIP.
The export also includes `review.html`, a self-contained page with provenance,
failure logs, diff, execution/behavior checks, regressions, and model usage.
Generate it for an existing run with `docdrift review <run-id>`; this reads saved
evidence without inference or execution and does not rescore the run.

Stop conditions, all recorded as `status`: `proposed`, `all_candidates_rejected`,
`budget_exhausted` (model calls or total tokens), `malformed_responses`,
`inference_error`. Defaults in `RepairBudget`: 8 calls, 2 candidates, 4 snippet
runs, 2 malformed responses, 2048 completion tokens per call, 60k total tokens.

## Live client

`TokenFactoryClient` posts OpenAI-compatible chat completions to
`https://api.tokenfactory.nebius.com/v1/chat/completions` with
`Authorization: Bearer $NEBIUS_API_KEY`, `temperature: 0`, and no automatic
retry. The model ID has no default; pass the exact Nemotron ID.

Verified live on October 14 (`docs/FEEDBACK_LOG.md` F1–F3): four Nemotron
models are listed; `nvidia/nemotron-3-super-120b-a12b` supports `tools` in the
standard OpenAI shape and reports `usage` (reasoning tokens count as completion
tokens). Its first agent repair of the renamed-method fixture verified in 5
calls. Context window, rate limits, and per-token price are still unknown.

## Evaluation (`src/docdrift/evaluation.py`)

`execution_only` flags drift only when the process fails. `one_shot` and
`agent` detect with the frozen observable checks, then repair. All share one
baseline observation per case and the same verifier. Held-out cases need
`--include-held-out`; public reference candidates stay `pending_reproduction`.
The report's `evidence` field is `no_model`, `synthetic_not_evidence`, or
`live_inference`.

## Commands

```bash
# Baseline, local Docker, no model:
uv run --no-sync docdrift evaluate --strategies execution_only

# Rehearse the pipeline with synthetic responses (not evidence):
uv run --no-sync docdrift repair --strategy agent --replay responses.json

# After credits are confirmed by the user:
NEBIUS_API_KEY=... uv run --no-sync docdrift repair --strategy agent --live --model <nemotron-id>
NEBIUS_API_KEY=... uv run --no-sync docdrift evaluate --strategies execution_only,one_shot,agent \
  --live --model <nemotron-id> --include-held-out
```

`evaluate --index` defaults to the checkout's `fixtures/evaluation/index.json`;
run it from a checkout. Execution is local Docker in both commands; the Nebius
Sandbox adapter is not wired into these paths yet.

## Observed so far (local Docker, no model, Oct 14)

`evaluate --strategies execution_only --include-held-out`: drift detected 3/4
broken (missed the exit-zero return-shape case, as predicted), 0/3 false drift
reports, 4/4 correct abstentions. Curator plumbing check, not a scored result.

A synthetic agent replay of the renamed-method known repair ran through real
Docker: 1 baseline + 1 agent snippet + 12 engine operations, `behavior_verified`.

## Verification contract for model repairs

Relaxed on October 14 from an exact known-repair AST match (decision D3 in
`STATUS.md`). A repair is `behavior_verified` when, for every frozen input, the
output JSON matches exactly, the required API call is present, and its return
value definitely reaches a top-level `print` (`profile.operation_reaches_output`).
`known_repair_ast_match` is still recorded per result for information.

The flow check is a must-analysis of straight-line top-level code:

- A name carries the result only if its latest top-level binding derives from
  the call or another carrying name. Bindings inside `if`, loops, `with`, `try`,
  `match`, or definitions clear the name; prints there do not count.
- `x if c else y` needs both arms to carry; `and` needs every operand; `or`
  needs its first operand (so `api() or {}` is fine).
- Calls pass positional arguments through only for builtins, imported names,
  receiver instances, and methods of a carrying value. Helpers defined in the
  example do not, and rebinding the receiver, `print`, or an import rejects.

Threat model: natural model shortcuts (dummy call beside a reimplementation,
conditional fallback, dead-branch print). Eleven constructed bypasses are
rejected in `tests/test_profile.py`. Not covered: in-place mutation of the
result, and deliberately obfuscated code (selecting from containers, `getattr`,
`exec`). The varied-input output checks remain the behavior oracle.

History: the first relaxed version (commit `89477a1`, Oct 14) let branch
assignments only add flow; it accepted all eleven bypasses and was replaced the
same day. All nine live model repairs made with it also pass the stricter
check, so no recorded verdict changed.
