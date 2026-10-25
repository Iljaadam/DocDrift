# Judge quickstart: hosted repair, saved evidence, and local verification

## Run a fresh hosted repair

Open [DocDrift](https://iljas-vps.tail2832de.ts.net:8443) and enter username
`judge` with the passphrase supplied privately in the judging instructions.
No provider account, API key, local installation, or Tailscale account is needed.

Select **Run fresh repair**, wait for a terminal result, then open its review
and download the evidence ZIP. This generates a new Nemotron proposal and verifies
it on Nebius Sandboxes against the owned fixture's frozen contracts. Each fresh
attempt consumes one shared slot, including a failed attempt. Fifteen slots
remained when public HTTPS acceptance passed on October 25; the page displays
the current allowance. New admissions end after December 15.

The owner maintains the VPS and supplies service credentials. Saved evidence
below remains available without starting a new repair. Operator details are in
[the deployment guide](JUDGE_DEPLOYMENT.md).

## Browse the real model repair

Open [the saved F6 demo bundle](demo/f6/index.html) in a browser after cloning
the repository. It works from disk without a web server, Docker, credentials,
or model calls. Browse the strategy comparison, successful agent repair and
evidence ZIP, and rejected one-shot proposal.

This records one comparison on an owned supplemental development fixture:
live NVIDIA Nemotron generation through Nebius Token Factory, with local Docker
execution. Agent verified 1/1; one-shot verified 0/1 after static rejection.
Both detected the broken example; all strategies reported no drift on the one
unrelated healthy example. Total model usage was 6 calls / 8,781 tokens and
execution used 15 local snippet operations. The case was added after earlier
development results; it is not held out and establishes no general advantage.
See [feedback log F6](FEEDBACK_LOG.md#f6--source-inspection-development-case-separates-strategies-once-2026-10-15).

The bundle preserves both outcomes and explains its published-copy provenance.
Its saved evidence can be inspected without rerunning the model. The integrity
checker verifies archive contents and hashes; it does not attest their origin
or execution. This route provides evidence browsing, not a live repair service.

## Browse the separate Sandbox verification

Open the [Oct 21 Sandbox supplement](demo/f6-sandbox/index.html) without keys or
new execution. The unchanged saved F6 agent proposal passed actual Nebius
Sandbox verification: twelve verifier operations reproduced the original failure,
passed three repaired inputs and three healthy regressions, and preserved
protected hashes. Three separate runtime probes checked Python capability,
artifact-byte retrieval, and terminal cancellation. No new inference was performed.

The original failed image-import receipt was preserved; recovery used an
existing Python 3.12 slim image without another import. Billing remains
unverified. This saved-proposal verification is separate from the historical
Docker strategy comparison; it is not a new model evaluation or live service.

## Execute the free manual demo

This route uses the packaged owned fixture, a supplied manual repair, and local
Docker. It needs no Nebius account, provider key, or inference credits. It
demonstrates failure reproduction, patch limits, independent checks, healthy
preservation, and evidence export. It demonstrates a supplied manual repair.
The hosted route above provides fresh Nemotron generation separately.

The twenty-attempt hosted allowance includes acceptance testing and the reserved
held-out comparison, now completed with both strategies verifying 2/2. Browse
its [saved results and evidence](demo/held-out/index.html) without keys or execution.

## Set up

Use Git, Python 3.12, uv, and a running Docker daemon. From the checkout:

```sh
uv sync --extra dev --locked
uv run --no-sync docdrift demo --inspect-only
docker pull python:3.12-slim
```

Install dependencies and download the public Python image explicitly. DocDrift
does not pull images or provision cloud resources automatically. The commands
below run only the dependency-free owned fixture with guest networking disabled.

## Run and inspect

```sh
uv run --no-sync docdrift demo --image python:3.12-slim
```

Expect `status: completed` and `repair_verdict: behavior_verified`. The original
example calls a missing method. The supplied one-fence repair must pass three
varied target inputs and preserve three healthy-example checks. The verdict
covers those frozen contracts, not arbitrary inputs or an independent public bug.

Open the printed `review_path` in a browser. It contains the original failure,
colored diff, separate execution/behavior checks, regressions, provenance,
operation logs, and an adjacent evidence ZIP download. The ZIP includes the HTML,
source, checks, patch, and a SHA-256 manifest. The page labels the manual repair
and local Docker execution. No web server is required.

Regenerate a saved review without any execution:

```sh
uv run --no-sync docdrift review <run-id>
uv run --no-sync docdrift verify-evidence .docdrift/runs/<run-id>/evidence.zip
```

The integrity command checks ZIP members and manifest hashes without extraction
or execution. Success is not proof of origin or execution; see [evidence
boundaries](EVIDENCE.md).

Run the rejection challenge and synthetic provider contract:

```sh
uv run --no-sync docdrift challenge
uv run --no-sync docdrift sandbox-contract-demo
```

The challenge checks deliberately constructed bad patches, with no code
execution. The Sandbox contract command uses synthetic responses, not Nebius
runtime access. Neither command consumes provider credits.

Exercise the connected evaluation path without Docker:

```sh
uv run --no-sync docdrift evaluate --execution-backend sandbox-simulation \
  --strategies execution_only --output .docdrift/evaluations/sandbox-contract.json
```

This generates synthetic HTTP receipts from owned fixture contracts and runs no
guest code. Rows are explicitly unscored and establish no verified repairs.

## Compare recorded strategies

An existing evaluation JSON can be rendered without Docker, inference, or
provider calls:

```sh
uv run --no-sync docdrift review-evaluation /path/to/evaluation.json
```

The HTML shows strategy counts, denominators, token usage, backend, inventory
identity, case outcomes, and held-out scope. Unreproduced public candidates stay
unscored. Linked individual run reviews must be present in the selected state
directory; otherwise case outcomes remain visible without links. Synthetic
replays are labelled separately from live model results.

Live Nemotron generation uses `repair --live` or `evaluate --live` and consumes
Token Factory credits. No paid personal account is needed for the routes
above. The original model comparison uses local Docker; the separate saved
proposal verification uses Nebius Sandboxes. The free live-agent judging route
is tracked in [STATUS.md](../STATUS.md).
