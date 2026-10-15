# Sandbox REST contract: offline simulation only

Reviewed against official documentation on October 14, 2026. No provider request,
credential check, live recording, compute operation, or inference call was made.
The fixtures in `tests/fixtures/nebius/` are **synthetic documented-shape responses**;
their IDs, outputs, timings, and resource values are invented. Their manifest
records provenance and hashes. They do not demonstrate remote access, actual
execution, credit coverage, or competition qualification.

## The $0 gate

`NebiusSandboxAdapter` permits live GET/HEAD requests only. All POST/DELETE
operations fail before transport and before a submission receipt is created.
There is no live execution override, account setup, automatic credential lookup,
model call, provisioning, or billing action. An explicitly selected
`httpx.MockTransport` with `offline_simulation=True` enables synthetic mutation
contracts. The adapter checks the actual transport again on every mutation and
rejects foreign mounted transports. The simulation flag is read-only.

Constructing a GET client still requires explicitly supplied credentials. The CLI
currently constructs only synthetic clients, with invented credentials. It does
not contact the provider or inspect the user's OS credentials.

The current provider billing page describes bank-card onboarding and automatic
charging; it does not establish an enforceable credit-only stop. Sandbox beta
status establishes neither free execution nor promotional-credit coverage. Live
execution therefore stays disabled while the Builder grant, coverage, expiration,
and protection against personal charges remain unconfirmed. Preserve NewsBias's
resources and any shared credit pool. See [current billing](https://docs.tokenfactory.nebius.com/other-capabilities/billing-new)
and [Sandbox limits and usage](https://docs.tokenfactory.nebius.com/sandboxes/operate/limits-retention-and-usage).

## Documented wire contract

The fixed base URL is `https://api.tokenfactory.nebius.com/sandboxes/v1/`.
Authorization and Project headers remain controller-side. Redirects and
environment proxy configuration are disabled. Exceptions contain bounded machine
codes rather than HTTP bodies, request objects, authorization headers, or keys.
Responses request identity encoding and reject compressed bodies or oversized
declared lengths before reading. JSON and artifact bodies use capped raw streams,
without automatic HTTP decompression; JSON also rejects duplicate keys and
nonfinite numbers.

| Method and path | Implemented purpose | Official reference |
| --- | --- | --- |
| `GET whoami` | Read permission and effective-limit maps | [Token information](https://docs.tokenfactory.nebius.com/api-reference/sandboxes/auth/get-current-token-information) |
| `GET inspect/{image_uuid}/` | Confirm a selected immutable image's identity | [Image inspection](https://docs.tokenfactory.nebius.com/api-reference/sandboxes/inspect/inspect-an-image) |
| `POST files` | Upload frozen raw bytes; check returned UUID, hash, and size | [File upload](https://docs.tokenfactory.nebius.com/api-reference/sandboxes/files/upload-a-file-to-the-server-the-body-must-be-a-file-content) |
| `POST instances` | Submit an explicitly bounded direct-executable operation | [Spawn](https://docs.tokenfactory.nebius.com/api-reference/sandboxes/instances/spawn-a-new-container-instance) |
| `GET operations/{operation_uuid}` | Poll operation and process results without requesting inflight streams | [Operation status](https://docs.tokenfactory.nebius.com/api-reference/sandboxes/operations/get-an-operation-status) |
| `DELETE operations/{operation_uuid}` | Request cancellation of an owned accepted operation | [Cancellation](https://docs.tokenfactory.nebius.com/api-reference/sandboxes/operations/cancel-an-operation) |
| `GET inspect/{result_image_uuid}/download?path=…` | Stream selected retained artifacts with a byte cap | [Artifact download](https://docs.tokenfactory.nebius.com/api-reference/sandboxes/inspect/download-a-file-from-image) |

`preflight(image_id=None)` performs identity/permission reads, without a code
probe. It does not claim that network isolation works, Python 3.12 is installed,
credits exist, or provider costs are covered.

`prepare({guest_path: frozen_bytes})` uploads files in simulation. Guest paths
must be canonical paths below `/work/docdrift/`, excluding credential/metadata
entries. At most 2,000 files and 50 MiB are accepted. Matching content reuses an
upload UUID inside one adapter; an ambiguous upload cannot be retried by that
instance. The execution bridge also persists upload attempts and accepted UUIDs
by content hash across restarts; ambiguous uploads stay blocked.

`RemoteExecutionRequest` contains a canonical immutable image UUID, direct
absolute executable, tuple of arguments, nonsecret `DOCDRIFT_INPUT`, injected
uploaded-file UUIDs, explicit `disposable` choice, timeout, and log limit.
Submission sends `shell=false`, `preserve_env=false`, `networking.enabled=false`,
closed stdin, nonroot IDs, and only controlled guest environment values. The
provider receives at most 30 seconds, 256 KiB per captured stream, and a 20 MiB
filesystem-layer limit. Each operation gets a unique working directory; the spawn
reference says absent working directories are created automatically. Ownership,
permissions, dependency setup, resource enforcement, and network denial still
require an authorized live probe.

## Persistence and recovery

`submit(request, on_accepted, *, run_id, phase)` commits a `SubmissionJournal`
receipt **before** its sole POST. It then commits a returned operation UUID
**before** the external callback. Callback failure leaves the accepted ID
available for recovery. A valid UUID from an unexpected successful HTTP status
is also retained before reporting a contract error.

Timeouts, transport errors, malformed/oversized acceptance responses without a
usable ID, HTTP 408/429, and every 5xx become uncertain. Definitive other 4xx
responses become rejected. No POST is retried automatically. A duplicate
run/phase is refused even after restart or with changed request bytes.

`recover(run_id, phase, expected_image_id=…, expected_disposable=…)` reads the
existing receipt and registers its known operation. Interrupted submissions
without IDs become uncertain. Recovery does not submit a replacement. The
execution bridge freezes expected image/retention and request identities outside
model-controlled inputs and supplies them during recovery. The journal retains
request digests rather than arbitrary request bodies.

`observe(id, timeout_seconds=30)` separates service state from process exit,
signal, and timeout. `SUCCESS` with exit 1 is a completed failing process. Missing
results, malformed captures, wrong known source images, or unconfirmed isolation
settings cannot pass execution. A client wait expiring sets
`observation_timed_out`; it does not invent a guest timeout or cancel the guest.
Cancellation acceptance likewise requires subsequent status reconciliation.

The documented uppercase service states are parsed strictly. Streams support
documented base64/ASCII envelopes, retain at most 256 KiB, and report truncation.
Unknown encoding/state shapes fail closed. Raw resource metrics, including
`cost`, keep their provider values with **unspecified cost units**; they are not
dollars or invoice estimates. No adapter field claims behavioral verification.

`cancel(id)` requires an owned accepted ID in simulation; resumed ownership can
be restored with `recover`. `download(id, paths)` requires a retained result image
and bounds all downloaded bytes to 20 MiB. Disposable runs provide no artifact
continuation image. Downloads do not execute or unpack returned content.

## Offline execution integration

`SandboxExecutionAdapter` connects this contract to final verification, evaluation
baselines, and model probes. Every method, including reads, requires an actual
`httpx.MockTransport` with no foreign mounts. The bridge cannot issue even a live
preflight request. It freezes bounded regular snapshot files and a separate
controller runner, injects them beneath `/work/docdrift/`, and requests an
immutable image UUID and direct Python executable. No code is executed by the
bridge or the fixture-response service.

The simulator persists uploads and operation envelopes in SQLite for recovery
across controller restarts. It matches registered code/input pairs and protected
package bytes. Responses are manufactured from curator contracts, not provider
recordings. Select `repair|evaluate --execution-backend sandbox-simulation`;
model strategies require synthetic replay. Outcomes remain unscored and never
become behavior-verified evidence.

Accepted IDs are durable before observation, including preliminary probes.
Interrupted callbacks recover their accepted receipts without another submit.
Client wait timeouts remain incomplete with IDs available to resume. Terminal
success is not cancelled implicitly. Explicit cancellation still requires
ownership and subsequent observation. Signals, missing evidence, wrong images,
failed service states, and timeouts cannot pass verification.

## Remaining live acceptance gates

Integration is exercised offline only. It does not import an OCI image, install
dependencies, prepare a pristine dependency
image, prove Python/network capability, manage image deletion or retention, or
reconcile ambiguous submissions through an operation-history search. Those
workflows remain gated by confirmed access and protection against personal
charges. The independently checked local Docker evidence remains local evidence;
the plan's remote milestone is unfinished. Actual Nemotron repairs have passed
local Docker verification (`docs/FEEDBACK_LOG.md` F3–F6).
