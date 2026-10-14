# Nebius / NVIDIA feedback log

Required for the submission. Start at the first live call; record failures as
well as successes. One entry per finding. Never paste API keys.

## Entry template

```markdown
### F<n> — <short title> (YYYY-MM-DD)

- Product / API / model: <Token Factory chat completions | Sandboxes ... >, model ID, SDK/version
- Request: <minimal reproduction; input hashes instead of large payloads>
- Expected:
- Actual: <status code, error text, response excerpt>
- Latency / usage: <ms; prompt/completion tokens; billed units if shown>
- Effect on DocDrift:
- Suggestion:
```

## Questions to answer at the first live probe

- [x] Nemotron model IDs available to this account (F1); context window still unknown.
- [x] `tools` / `tool_choice` support and tool-call response shape (F2).
- [x] Usage fields in responses (F2); how credits are drawn still unchecked in the console.
- [ ] Sandbox: permission, offline execution, image reuse, cancellation timing, artifact download, billed units.

## Entries

Account: Token Factory $1 trial key (no card, per user). Execution in these
entries is local Docker, not Nebius Sandboxes.

### F1 — Model listing works; four Nemotron models (2026-10-14)

- Product / API / model: Token Factory `GET /v1/models`
- Request: bearer key, no body
- Expected: OpenAI-style model list
- Actual: 200 in 73 ms, 25 models. Nemotron: `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`,
  `nvidia/Nemotron-3_5-Lightning`, `nvidia/Nemotron-3-Ultra-550b-a55b`,
  `nvidia/nemotron-3-super-120b-a12b`. Entries carry only id/created/owned_by.
- Effect on DocDrift: picked `nemotron-3-super-120b-a12b` as the default working model.
- Suggestion: include context length, tool-calling support, and price per model in
  `/v1/models`; the public endpoints page renders client-side and is not machine-readable.

### F2 — Tool calling works in standard OpenAI shape (2026-10-14)

- Product / API / model: chat completions, `nvidia/nemotron-3-super-120b-a12b`
- Request: one user message asking to call a single `read_file` tool; `tool_choice: auto`, `temperature: 0`, `max_tokens: 300`
- Expected: one tool call
- Actual: `finish_reason: tool_calls`, one call with valid JSON arguments, empty content.
  Message also carries `reasoning_content`. 1.23 s.
- Latency / usage: 368 prompt, 90 completion tokens (63 reasoning).
- Effect on DocDrift: no text-protocol fallback needed. Reasoning tokens count against
  `max_tokens`, so the 2048 per-call cap must leave room for reasoning.
- Suggestion: document tool-calling support and reasoning-token accounting per model.

### F3 — First live agent repair verified (2026-10-14)

- Product / API / model: `docdrift repair --strategy agent --live --model nvidia/nemotron-3-super-120b-a12b`, owned renamed-method fixture (development split)
- Actual: 5 model calls, 6,514 prompt + 466 completion tokens, 13 s wall clock. The agent called
  `list_files`, `read_file drift_demo/__init__.py`, ran one probe in the sandbox with its own
  input, then answered with raw unfenced code (counted as malformed, nudged), then called
  `submit_replacement`. Diff: `tally` → `count`, one line. Independent verification:
  `behavior_verified` on all 3 inputs, healthy example preserved on 3 inputs, and the code
  matches the known-repair AST. Run `a600c26588e8428198b1c69987a329d0` in the local `.docdrift` store.
- Effect on DocDrift: milestone 2 shown on one development case.
- Suggestion (for us): accept a final unfenced answer that parses as Python as a candidate,
  or say so more explicitly in the prompt.

### F4 — Live development-split evaluation: all strategies verify (2026-10-14)

- Product / API / model: `docdrift evaluate --strategies execution_only,one_shot,agent --live --model nvidia/nemotron-3-super-120b-a12b` (development split; held-out excluded)
- Actual: 43 s, 54 local Docker operations. Both development broken cases (renamed_method,
  changed_keyword) `behavior_verified` under one_shot (2 calls, 1,603 tokens) and agent
  (9 calls, 12,534 tokens, 2 sandbox probes). Diffs were the minimal one-line fixes and matched
  the known-repair AST. 0/2 false drift reports, 4/4 correct abstentions for every strategy.
  Report: `.docdrift/evaluations/dev-live-1.json` (local, gitignored).
- Effect on DocDrift: model plumbing works end to end. But the evaluation does not separate
  one_shot from agent, because every owned fixture README states the fix in prose (e.g. "The
  installed package exposes `count` instead"), and Python 3.12 tracebacks add "Did you mean"
  hints for renamed names. One-shot never needs the source.
- Suggestion (for us): neutral fixture prose and at least one case whose fix requires reading
  the source, before the scored held-out run.
