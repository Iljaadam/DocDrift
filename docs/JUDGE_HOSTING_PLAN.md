# Hosted judge demo — implementation brief

Status: implemented and tested offline after the user's October 22 answers;
not yet a deployed or live-accepted service. The user approved this VPS, the
existing key/project, private shared access, and the bounded allowance below.
See [the activation instructions](JUDGE_DEPLOYMENT.md). The completed F6
allowance and private state are preserved.

## Judge experience

A judge opens an HTTPS address, enters a private passphrase, and selects **Run
fresh repair**. The page explains the owned development fixture and shows queued,
running, and terminal states. A completed run exposes the original failure,
fresh model proposal, patch, frozen behavior checks, healthy regressions, usage,
and a sanitized review/evidence download. Saved F6 evidence remains separately
labelled and available when new runs cannot be admitted.

Use the existing source-inspection development fixture, current Nemotron model,
and recorded existing Python image. Judges supply no code, repository URL,
custom prompt, or provider credential. Use the existing DocDrift presentation
style and a generated HTTPS hostname. No purchased domain is required.

## Controller and worker

Prepare one portable Python/container service with a persistent SQLite volume,
a small HTTP interface, and one separate worker using the existing engine.
HTTP handlers admit and inspect jobs; they do not execute repairs themselves.
The user selected the current VPS. Use separate DocDrift units and state without
changing NewsBias services, containers, listeners, or configuration.

The existing F6 remote binds a saved proposal and exact operation hashes. It
cannot authorize new model proposals. Add a separate fixed-fixture judge adapter
with explicit deployment/run allowances, frozen source/check bindings, offline
guest operations, and fresh final verification. Preserve the default CLI's live
mutation guards and the completed `.docdrift/sandbox-f6/` state.

Reuse `evaluate_fixture`, the bounded agent, deterministic verification,
durable remote receipts, review rendering, and evidence export. Do not port the
Python engine into a separate frontend runtime. The current VPS is selected
for the Python/SQLite controller; no additional frontend hosting provider is needed.

## User-approved allowance (October 22, D31)

- Twenty admitted fresh attempts total, including deployment acceptance tests.
- One active worker; a bounded queue; no concurrent model or guest operations.
- Per attempt: at most eight model calls and seventeen disposable guest
  operations: one initial observation, at most four exploratory snippets, and
  twelve final verifier operations.
- One separately reserved runtime capability operation before activation.
- No image imports; use only the recorded existing Python image.
- Stop new admissions after December 15; preserve downloadable results.

Reserve run/operation/model-call attempts transactionally before requests.
Count failed and uncertain submissions against the allowance. Persist accepted
operation IDs and reconcile them; never automatically repeat an ambiguous POST.
An interrupted worker must not reset limits or silently create another run.

The existing reported-token threshold is checked before subsequent model calls;
the final call may take usage over that threshold. Neither that threshold nor
run counts establish a guaranteed dollar cap. Raw Sandbox resource `cost` is
diagnostic; account billing and credit coverage require separate confirmation.
The owner explicitly approved proceeding and will inspect usage personally,
while stating granted-credit funding as the intended policy. The $30.98 balance
is a user report for Token Factory only. That permission does not establish
Sandbox credit coverage, no personal charges, or a guaranteed financial ceiling.

## Access, artifacts, and operations

Keep provider credentials in the selected host's server-side secret settings,
outside Git, frontend responses, guest requests, and exported artifacts. The
user selected the existing key/project. Generate the judge passphrase and provide it privately with testing
instructions. Apply authentication to job creation, status, and downloads.

Keep private durable receipts for recovery, and publish only sanitized review
and archive copies. The manifest checks bytes, not authenticity or execution
attestation. Do not include judge credentials, bearer headers, or account secrets
in downloadable evidence. Preserve results through judging; decide subsequent
retention with the owner rather than promising provider-side deletion behavior.

The owner selected this VPS and will operate it through judging. Before public
activation, confirm its HTTPS route and actual service startup in the normal
terminal. No external hosting account or paid hosting allocation is assumed.

## Implementation and actual activation

Queue admission/idempotency, authentication, expiration, quota accounting,
worker recovery, the fixed-fixture adapter boundary, artifact sanitization, and
the minimal interface are covered with synthetic provider responses. Separate
resource-limited user units, secret preparation, health checks, and deployment
instructions are prepared. Web authentication, store concurrency, crash
accounting, fresh engine verification, and secret rejection are checked offline.

On October 22 the startup capability operation succeeded and a fresh local
HTTP acceptance repair returned `behavior_verified`. Both user services are
enabled and running; the web process has no provider key. The original two
reserved held-out fixtures were then run once under each strategy: one-shot
2/2 verified and agent 2/2 verified. Five attempts are used and fifteen remain.
Saved results and actual usage are in [feedback F13/F14](FEEDBACK_LOG.md) and
the [held-out bundle](demo/held-out/index.html).

Public HTTPS acceptance still awaits the owner's one-time Tailscale Funnel
account enablement. Local success is not proof of an external-browser session.
Video recording, public
repository release after final review, and final submission
remain separate deliverables; the hosted demo is not evidence that they occurred.
