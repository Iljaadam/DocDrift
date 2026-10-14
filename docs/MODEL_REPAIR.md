# Model repair and evaluation harness

Built offline on October 14, 2026, ahead of Token Factory access. No live
inference has run. Everything below was exercised with synthetic scripted
responses and contract doubles, plus local Docker for execution.

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

Relaxed on October 14 from an exact known-repair AST match. A repair is
`behavior_verified` when, for every frozen input, the output JSON matches
exactly, the required API call is present, and its return value reaches the
`print` (`profile.operation_reaches_output`). Top-level reassignment from a
value that does not carry the result removes the flow, so the dummy-call trick
still fails. Known gap: in-place mutation of the returned object is not
tracked; the varied-input output checks remain the behavior oracle.
`known_repair_ast_match` is still recorded per result for information.
