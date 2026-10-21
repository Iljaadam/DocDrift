# Verify the saved F6 repair on Sandboxes

The first real image-import operation was accepted on October 21, then failed
while the provider importer fetched the pinned Python image (HTTP 404).
**One import attempt is consumed; no image, runtime probe, verifier operation,
or new inference resulted.** The [published F6 evidence](demo/f6/index.html)
remains live Nemotron generation with local Docker verification.

## Prepare offline

From the checkout with its Python environment installed:

```sh
.venv/bin/python scripts/verify_saved_f6_sandbox.py prepare
```

This validates the committed F6 archive and proposal hashes and writes frozen
inputs plus `plan.json` under `.docdrift/sandbox-f6-plan/`. It performs no provider
requests, model calls, guest execution, or held-out evaluation. The plan permits
12 exact verifier phases and nine hash-allowed verifier upload payloads:

| Phase | Operations |
|---|---:|
| `baseline_target` | 1 |
| `confirm_original` | 1 |
| `healthy_baseline` | 3 |
| `final_original` | 1 |
| `final_repaired` | 3 |
| `healthy_regression` | 3 |

The original evidence and proposal remain unchanged. A new verification run
retains the saved proposal transcript and separates its historical generation
usage (5 calls / 7,841 tokens) from current inference usage (zero).

## Authorization records

On October 21 the user explicitly authorized the bounded run while awaiting the
billing answer (D25). The runner accepts that scoped permission separately from
confirmed credit coverage. Permission is not proof of free service, a dollar
cap, or actual $0 charges. Ordinary live adapters and CLI commands remain guarded.

### Confirmed credit coverage

Sandbox execution, image import, and storage coverage are still unconfirmed.
On October 21 the user supplied a Builder email promising $25 in Token Factory
credit in a separate email, plus partner credit offers. Receipt of that specific
$25 allocation and its Sandbox coverage are not established. The user is unsure
whether the current Sandbox beta is free; this is not a coverage confirmation.
Do not infer $0 operation costs from `whoami`, permission flags, or reported
Token Factory credits. The official [Sandbox limits and usage](https://docs.tokenfactory.nebius.com/sandboxes/operate/limits-retention-and-usage)
and [billing documentation](https://docs.tokenfactory.nebius.com/other-capabilities/billing-new)
do not establish this project's grant coverage or protection against personal
charges.

Public primary sources checked on October 21 explain the possible confusion:

- The [February 19 ConTree announcement](https://contree.dev/blog/contree-eap-announcement/)
  explicitly advertised a "free early access program."
- The [May 19 migration announcement](https://contree.dev/blog/contree-joins-token-factory/)
  moved the standalone program into Token Factory Sandboxes beta, but does not
  establish the current prices or continued free coverage.
- The [current ConTree FAQ](https://contree.dev/) says billing is managed through
  Token Factory. The current limits/usage page above gives no free-beta promise
  or invoice rates for execution, import, or retained images.

These sources confirm historical free access, not the current project's billing
terms. No zero-cost record should be derived from them or from API permissions.
The earlier approximately $30 balance and the newly quoted $25 offer must not
be added together without evidence that the latter is a distinct received grant.

Ready-to-send question for `contree@nebius.com` (draft only; not sent):

> For Token Factory project `aiproject-e00a0rb50jb0emajfv`, are Sandbox execution,
> private OCI image import, file transfer, and retained checkpoint-image storage
> currently free during beta? If any are billed, does the $25 AI Builder Program
> Token Factory credit cover them, and can usage stop at the credited balance
> with no personal charges? Are these terms expected to change before December 15?

Once there is an actual confirmation that all three categories are free or
grant-covered with no personal charges, record that fact in
`.docdrift/access/sandbox-coverage.json`, with mode `600`. This is the required
schema; the blank factual fields below intentionally make it an invalid record:

```json
{
  "kind": "docdrift_sandbox_credit_coverage",
  "project_id": "aiproject-e00a0rb50jb0emajfv",
  "personal_spend_limit": 0,
  "execution": "free_or_grant_covered",
  "image_import": "free_or_grant_covered",
  "storage": "free_or_grant_covered",
  "confirmation": "",
  "confirmed_at_utc": ""
}
```

Fill `confirmation` with the actual nonempty coverage/no-personal-charges
statement and `confirmed_at_utc` with its ISO timestamp in UTC. The template is
not evidence, a provider billing control, or an enforceable spending cap. The
runner refuses missing or invalid authorization before making a network request.
No confirmed-coverage record has been created on the user's behalf.

### Scoped permission with unverified billing

The user's instruction was: "We will wait for the answer but in the meantime
let's use it, i give permission." Its mode-600 record is
`.docdrift/access/sandbox-authorization-2026-10-21.json`, using this schema:

```json
{
  "kind": "docdrift_sandbox_scoped_authorization",
  "project_id": "aiproject-e00a0rb50jb0emajfv",
  "billing_coverage": "unverified",
  "source_run_id": "4fd82cb8be7a449e8815d5366665f4ac",
  "limits": {
    "image_imports": 1,
    "runtime_probes": 3,
    "verifier_operations": 12,
    "inference_calls": 0
  },
  "authorization": "We will wait for the answer but in the meantime let's use it, i give permission",
  "authorized_at_utc": "<actual UTC timestamp>"
}
```

The session binds the exact authorization bytes. Do not edit that record after
starting; resume the same state and accepted operation IDs. Reports and frozen
execution contracts record `credit_coverage_confirmed: false`,
`personal_spend_limit: null`, and `billing_coverage: unverified`. The billed
amount remains unknown until supported by billing records. This does not
authorize new model generation, held-out evaluation, additional imports/probes,
hosting, or general live execution.

## Current execution environment

The user ran the command from their normal terminal on October 21. Nebius
accepted image-import operation `01a15f6f-2d46-71c6-a692-ede648b18661` at
17:08:04 UTC; it reached `FAILED`. Its saved error reports HTTP 404 during the
registry pull. The response identifies no exact registry request URL or reason
for the 404. No result image was returned. This confirms an accepted provider
request, not runtime capability or billing coverage. See feedback F10.

The failed receipt, raw operation response, authorization binding, and runtime
report remain in `.docdrift/sandbox-f6/`. A rerun now returns the saved terminal
failure immediately without another provider request. Do not delete state,
change the registry binding, or select a different state directory to bypass
the consumed import allowance.

Earlier in this agent session, an authorized read-only access attempt failed locally with
`transport_error`; a credential-free DNS diagnostic returned `gaierror` /
`EAI_AGAIN`. The workspace's granular approval policy rejected a DNS-only sandbox
escalation because `sandbox_approval=false`. That local attempt received no
provider response. Its diagnostic record is
`.docdrift/access/sandbox-network-failure-2026-10-21.json`.

### Next: discover an existing Python image without importing

In the same normal terminal with `NEBIUS_API_KEY` still loaded, run:

```sh
.venv/bin/python scripts/verify_saved_f6_sandbox.py images
```

This makes one [public-image listing GET](https://docs.tokenfactory.nebius.com/api-reference/sandboxes/images/list-publicly-available-images)
filtered to `python` tags, saves a mode-600 timestamped inventory under
`.docdrift/access/`, and prints only UUID/tag pairs plus request counters.
It creates no resource, chooses no image, and leaves the failed run untouched.
Tags are discovery hints; Python 3.12 capability is not established by a tag.

The next recovery option is an already available immutable Python image, if one
is listed. Its selection/provenance and runtime capability still need a concrete
recovery implementation; the current runner correctly requires a successful
import receipt before binding an image. No public-image fallback or replacement
import is enabled automatically. [Nebius documents existing-image references](https://docs.tokenfactory.nebius.com/sandboxes/guides/prepare-and-reuse-environments)
as an alternative to OCI import without preparation compute.

## Run the fixed verification

The original invocation below is retained for reference and completed/pending
operation recovery. With the current terminal failed import, it returns that
saved failure rather than submitting another import. Explicitly load the key
from its existing private file outside the repository:

```sh
chmod 600 .docdrift/access/sandbox-authorization-2026-10-21.json
set -a
. ~/.config/docdrift/nebius.env
set +a
.venv/bin/python scripts/verify_saved_f6_sandbox.py run \
  --authorization .docdrift/access/sandbox-authorization-2026-10-21.json
```

The runner does not discover credentials automatically. Keep the key outside the
repository and never print or copy it into evidence.

The default image is the immutable Linux amd64 Python manifest found in public
Docker Hub metadata on October 16, 2026:

```text
docker://docker.io/library/python@sha256:2b4f19dae3a777dfc3b76730bda1e82e1f66ab2a2686fa93ca78edbfb4f04ffe
```

This is a registry pin for the remote run, separate from this aarch64 host's
local Docker image. The bounded scope is:

- One private image import, with a 120-second limit.
- Three fixed runtime probes: Python 3.12/nonroot execution with no guest
  network interface beyond `lo`; exact-byte download of one retained fixed
  artifact; and cancellation with a recorded terminal outcome.
- The 12 frozen verifier operations above, each limited to 30 seconds, with
  networking disabled. There is no model call or held-out evaluation.

Durable receipts are saved before submissions and accepted operation IDs before
observation. Interrupted runs reuse known IDs; uncertain submissions are never
retried. If a receipt cannot be saved after acceptance, the runner prints any
known operation and attempt UUIDs beside the error code for manual reconciliation
and saves them in `runtime-report.json` under `error_context` when the report is
writable. Preserve the state directory when a step is incomplete. Runtime
capabilities and the repair's new behavior verdict remain unestablished until
the corresponding recorded checks actually pass.

The cancellation probe can finish as `CANCELLED` before an instance image is
assigned. A matching saved terminal receipt lets the runner resume that outcome
without repeating the cancellation or creating another instance. This recovery
case is covered by synthetic documented-shape tests; it has not been observed
live. Successful execution probes and verifier phases still require the pinned
image identity.

The default state directory is `.docdrift/sandbox-f6/`. Inspect
`runtime-report.json` for probe outcomes and the new verification run ID; that
run's report, HTML review, and evidence ZIP live under `runs/<run-id>/`. A
successful archive is also checked for integrity. These are new artifacts;
the saved October 15 generation and local Docker evidence are preserved.

The ordinary CLI and synthetic Sandbox contract commands retain their existing
restrictions. This dedicated fixed-case runner introduces no generic `--live`
switch for arbitrary execution.
