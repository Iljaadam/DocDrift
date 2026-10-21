# Hosted judge demo — implementation brief

Status: selected by the user on October 21; design and decisions, not a deployed
service. Live admission stays disabled until its separate allowance and funding
policy are recorded. The completed F6 allowance and private state are preserved.

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
Run this service separately from NewsBias infrastructure.

The existing F6 remote binds a saved proposal and exact operation hashes. It
cannot authorize new model proposals. Add a separate fixed-fixture judge adapter
with explicit deployment/run allowances, frozen source/check bindings, offline
guest operations, and fresh final verification. Preserve the default CLI's live
mutation guards and the completed `.docdrift/sandbox-f6/` state.

Reuse `evaluate_fixture`, the bounded agent, deterministic verification,
durable remote receipts, review rendering, and evidence export. Do not port the
Python engine into a separate frontend runtime. The Sites runtime supports
web interfaces but does not directly host this existing Python/SQLite worker;
a separate compatible controller host is still needed.

## Proposed allowance for user decision

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
The default remains $0 personal spending unless the user explicitly records a
new bounded exception for judging.

## Access, artifacts, and operations

Keep provider credentials in the selected host's server-side secret settings,
outside Git, frontend responses, guest requests, and exported artifacts. Prefer
a dedicated judge key if available; using the existing key/project is a user
decision. Generate the judge passphrase and provide it privately with testing
instructions. Apply authentication to job creation, status, and downloads.

Keep private durable receipts for recovery, and publish only sanitized review
and archive copies. The manifest checks bytes, not authenticity or execution
attestation. Do not include judge credentials, bearer headers, or account secrets
in downloadable evidence. Preserve results through judging; decide subsequent
retention with the owner rather than promising provider-side deletion behavior.

Before deployment, confirm a compatible host, durable storage, availability
through December 15, funding/expiry, live allowance, and an owner able to respond
to an outage. A free host's cold starts or ephemeral filesystem must be evaluated
against these requirements; no free or always-on hosting is assumed.

## Work that can proceed without live calls

Build queue admission/idempotency, authentication, expiration, quota accounting,
worker recovery, the fixed-fixture adapter boundary, artifact sanitization, and
the minimal interface using synthetic provider responses. Add container/runtime
configuration, health checks, and exact deployment/testing instructions.

Validate those behaviors offline. Keep deployment activation visibly
unconfigured until the missing decisions are resolved. The reserved held-out
evaluation, video recording, public repository release, and final submission
remain separate deliverables; the hosted demo is not evidence that they occurred.
