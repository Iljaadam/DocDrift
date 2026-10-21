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
- [x] Sandbox: one approved read-only `whoami` confirmed permission flags and effective limits (F7).
- [ ] Sandbox: credit coverage/billed units, image/Python capability, network isolation,
  execution, image reuse, cancellation timing, and artifact download.

## Entries

Account: same Token Factory key originally issued for the $1 trial; user reports
approximately $30 promotional credits on Oct 15 (balance/expiry unverified).
The user approved live calls on Oct 14 after
being asked to confirm no card and no auto top-up (reply: "yes go ahead"). Execution in
F3–F6 is local Docker. F7 is one separately approved live Sandbox access read;
it created no resources and performed no execution or inference.

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
  installed package exposes `count` instead"). One-shot never needs the source. (Python 3.12
  "Did you mean" traceback hints did not apply to these two cases; they do apply to the held-out
  renamed import: "Did you mean: 'TokenJoiner'?".)
- Suggestion (for us): neutral fixture prose and at least one case whose fix requires reading
  the source, before the scored held-out run.

### F5 — Neutral fixture prose; development rerun unchanged (2026-10-14)

- Change: the four broken fixtures' README prose no longer states the fix (fences byte-identical,
  manifests and index re-frozen). Source docstrings are unchanged (agent-visible only).
- Actual: `dev-live-2`, 41 s. one_shot 2/2 verified (1,453 tokens), agent 2/2 verified
  (9 calls, 12,701 tokens). Same one-line diffs.
- Effect on DocDrift: the remaining hint is realistic: each broken example's healthy neighbor
  in the same README already uses the current API (`.count(...)`, `descending=`). Development
  cases still do not separate one_shot from agent. The held-out return-shape case (needs the
  dict key from source or stdout) is the only case likely to.
- Suggestion (for us): to show the agent's value, add a case with no current-API neighbor and
  no traceback suggestion, so the fix requires reading the source.

### F6 — Source-inspection development case separates strategies once (2026-10-15)

- Product / API / model: Token Factory chat completions,
  `nvidia/nemotron-3-super-120b-a12b`; all execution is local Docker.
- Inputs: supplemental inventory `fixtures/development/index.json`, frozen in
  commit `7faa9e8` before inference. Index SHA-256:
  `24edc73aa852e887ae55269d760ce2404bea10e701390c8e66e044bbd3d2f19c`.
  One newly authored owned broken case plus one unrelated healthy example.
  The original fourteen-case inventory and both held-out cases are unchanged.
- Request: one comparison, `execution_only,one_shot,agent`, six-call agent cap,
  one one-shot call; no retries or fixture changes after observing the result.
- Actual: original `AttributeError` has no replacement-method suggestion.
  One-shot kept the missing method as `OccurrenceIndex.build(words)` and removed
  the constructor call; static policy rejected it (`meaningful operations cannot
  be removed`). It was not executed or counted as a repair. Agent read the package
  source and README, ran one probe, then submitted
  `OccurrenceIndex().positions(words, include_empty=True)`. Its repair passed all
  three frozen inputs and three healthy regression inputs; protected hashes match.
  Agent **1/1** behavior verified; one-shot **0/1**. Both detected the broken
  example; all strategies produced **0/1** false drift reports on the healthy case.
- Usage: one-shot 1 call, 520 prompt + 420 completion tokens; agent 5 calls,
  7,100 prompt + 741 completion tokens. Total **6 calls / 8,781 tokens**.
  **15 local snippet operations** (2 shared baselines, 1 agent probe, 12 verifier
  operations); Docker version preflights excluded. No billed dollar amount recorded.
- Evidence: `.docdrift/evaluations/source-only-live-1.{json,md,html}` and verified
  run `4fd82cb8be7a449e8815d5366665f4ac`. Both proposal transcripts are retained
  under `.docdrift/proposals/`, with IDs and SHA-256 hashes in the evaluation JSON.
- Effect on DocDrift: one exploratory example of source tools helping after the
  original development results. This case was added after those results and is
  reported separately; it is not a held-out result or a general superiority claim.
- Suggestion: retain the failed baseline alongside the success, and keep the
  frozen checks and budgets unchanged for subsequent evaluation.

### F7 — Read-only Sandbox access check succeeds (2026-10-16)

- Product / API: Sandbox `GET /sandboxes/v1/whoami` through the existing
  `NebiusSandboxAdapter`; one user-approved read-only request at
  **2026-10-16 14:37:10 UTC**. No image inspection or other provider request.
- Expected: permission and effective-limit maps without creating resources.
- Actual: the adapter returned successfully (`read_succeeded`). It accepts
  successful 2xx responses but does not retain the precise HTTP status, so no
  exact status code is claimed. Permission flags `import`, `spawn`,
  `spawn_disposable`, `list`, `cancel`, and `set_image_tag` were all `true`.
  The observed schema contained `token_uuid`, `token_expiration`, `permissions`,
  `operations_stat`, and `limits`; token identity, expiration, and raw response
  body were omitted from the saved record.
- Effective limits returned: `instance_max_timeout=3600`,
  `instance_max_concurrency=50`, `instance_max_layer_bytes=12884901888`,
  `images_import_max_concurrency=8`, `images_import_max_timeout=3600`.
- Latency / usage: **0.168 s** elapsed, **1 HTTP request attempt**, **0 compute
  operations**, **0 inference calls**. No billed amount was recorded; this read
  does not confirm promotional-credit coverage for Sandbox resources.
- Evidence: sanitized local record
  `.docdrift/access/sandbox-whoami-2026-10-16.json` (gitignored). It retains
  permission booleans, numeric limits, response field types, and the original
  response body's SHA-256; no credential or raw token identity is published.
- Effect on DocDrift: live permission discovery is confirmed for this project.
  Live mutations remain disabled. Image availability, Python capability,
  network isolation, execution, cancellation, artifact download, and credit
  coverage remain untested; this approval covered only the one access read.
  F6 remains live Nemotron generation with local Docker verification.
- Suggestion: make effective permissions easy to connect to credit coverage and
  billed-unit guidance so a successful access check can lead to a bounded,
  credit-funded execution test without assuming that access means free compute.

### F8 — Prepare saved-repair verification; reconcile documented wire variants (2026-10-16, offline)

- Product / API: Sandbox operation results; documentation review and synthetic
  contract tests only. No further authenticated Sandbox request was made.
- Finding: the official [networking-disabled recipe](https://docs.tokenfactory.nebius.com/sandboxes/cookbook/verify-with-networking-disabled)
  treats signal `-1` as no terminating signal and accepts `utf-8`/`utf8` output.
  Earlier DocDrift contracts covered nonnegative signals and ASCII/base64 only.
- Change: normalize that sentinel to `None`, preserve valid exit codes, accept
  the documented UTF-8 envelopes, and retain byte limits and truncation checks.
  Other negative signals and unknown encodings remain incomplete evidence.
- Effect on DocDrift: a separate fixed-F6 runner now freezes the saved proposal
  and twelve verifier phases, with bounded import/runtime probes and durable
  recovery. It reports zero new inference and separates prior generation usage.
  All runtime responses used in its tests are synthetic; no live execution or
  credit coverage is claimed. See [the prepared workflow](SANDBOX_VERIFICATION.md).
- Suggestion: keep stream encoding enums and no-signal semantics consistent
  between the runnable recipe and [operation reference](https://docs.tokenfactory.nebius.com/api-reference/sandboxes/operations/get-an-operation-status).

### F9 — Authorized activation blocked by local network policy (2026-10-21, no provider response)

- Scope: the user explicitly approved the saved-F6 verification while billing
  clarification is pending (D25). A separate scoped authorization records that
  permission without claiming free/grant coverage or a dollar spending cap.
- Attempt: one `GET /sandboxes/v1/whoami` through the existing read-only adapter
  before submitting any resource. It failed locally with `transport_error`;
  no provider response or HTTP status was received. A credential-free DNS lookup
  returned `gaierror` with errno `-3` (`EAI_AGAIN`).
- Execution environment: a DNS-only sandbox escalation was rejected by the
  workspace's granular policy because `sandbox_approval=false`. No matching
  Nebius connector was found in the plugin search results. This is not evidence
  of a Nebius outage, permission denial, API defect, or actual billed usage.
- Usage: one authenticated request attempt, zero successful provider responses,
  zero image imports/probes/verifier submissions, and zero new inference.
  No live session state exists and the operation allowance is unconsumed.
- Evidence: mode-600 local diagnostic record
  `.docdrift/access/sandbox-network-failure-2026-10-21.json`; actual permission in
  `.docdrift/access/sandbox-authorization-2026-10-21.json`. Neither contains the
  API key. The key remains in its existing private file outside the repository.
- Next: execute the prepared bounded command from a network-enabled environment
  under the already recorded user authorization. No additional billing approval
  is required for that fixed scope; actual coverage and charges remain unknown.
