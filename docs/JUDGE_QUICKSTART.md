# Judge quickstart: free local verification

This route uses the packaged owned fixture, a supplied manual repair, and local
Docker. It needs no Nebius account, provider key, or inference credits. It
demonstrates failure reproduction, patch limits, independent checks, healthy
preservation, and evidence export. It is not a live Nemotron repair service.
The submission's free live-agent access route is still pending.

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
```

Run the rejection challenge and synthetic provider contract:

```sh
uv run --no-sync docdrift challenge
uv run --no-sync docdrift sandbox-contract-demo
```

The challenge checks deliberately constructed bad patches, with no code
execution. The Sandbox contract command uses synthetic responses, not Nebius
runtime access. Neither command consumes provider credits.

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
Token Factory credits. Do not supply a paid personal account to try this local
demo. Actual Sandbox verification and free live judging access remain pending
provider approval and confirmed credit coverage.
