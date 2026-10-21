# Verify the saved F6 repair on Sandboxes

The fixed-scope path is prepared for the next real execution test. **No live
Sandbox resources have been created, and no new inference has been performed.**
The successful read-only `whoami` check confirmed permission flags, not credit
coverage or runtime behavior. The [published F6 evidence](demo/f6/index.html)
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

## Record actual coverage before running

Sandbox execution, image import, and storage coverage are still unconfirmed.
The user has been asked what the actual approval covers; no answer is recorded.
Do not infer $0 operation costs from `whoami`, permission flags, or reported
Token Factory credits. The official [Sandbox limits and usage](https://docs.tokenfactory.nebius.com/sandboxes/operate/limits-retention-and-usage)
and [billing documentation](https://docs.tokenfactory.nebius.com/other-capabilities/billing-new)
do not establish this project's grant coverage or protection against personal
charges.

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
runner refuses missing or unconfirmed coverage before making a network request.
No coverage record has been created on the user's behalf.

## Run the fixed verification

After recording factual coverage, explicitly load the key from its existing
private file outside the repository:

```sh
chmod 600 .docdrift/access/sandbox-coverage.json
set -a
. ~/.config/docdrift/nebius.env
set +a
.venv/bin/python scripts/verify_saved_f6_sandbox.py run
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
