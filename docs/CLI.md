# CLI guide

Use Python 3.12, Git, uv, and a running Docker daemon. From the checkout:

```sh
uv sync --extra dev --locked
uv run --no-sync docdrift --help
```

## Local demo

```sh
uv run --no-sync docdrift demo --inspect-only
docker pull python:3.12-slim
uv run --no-sync docdrift demo --image python:3.12-slim
```

Inspection needs no Docker. Execution uses the installed image and a supplied
manual repair, with no model or cloud calls. DocDrift never pulls images automatically.

Run artifacts live under `.docdrift/runs/<run-id>/`: the original and repaired
snippets, patch, frozen checks, logs, `review.html`, and `evidence.zip`.

## Review, export, and resume

```sh
uv run --no-sync docdrift review <run-id>
uv run --no-sync docdrift verify-evidence .docdrift/runs/<run-id>/evidence.zip
uv run --no-sync docdrift resume <run-id>
uv run --no-sync docdrift export <run-id>
uv run --no-sync docdrift review-evaluation saved-comparison.json
```

`review` and `review-evaluation` render saved results without execution or
inference. `verify-evidence` checks ZIP structure, coverage, CRCs, and SHA-256
hashes without extraction. `resume` reconciles saved operation IDs and keeps the
original deadlines and limits. Frozen input changes prevent resumption.

Review pages keep a section menu beside the evidence on desktop and at the top
on smaller screens. Use it to jump between the repair, checks, usage, and logs;
the selected section is highlighted. The menu also works with HTML opened from disk.

## A curated local repository

Commit the target repository first. Put its curator profile, independent checks,
and replacement outside the target repository; see the
[owned fixture](../fixtures/renamed_method/README.md) for the contract.

```sh
uv run --no-sync docdrift inspect /path/to/repository --ref HEAD --doc README.md
uv run --no-sync docdrift run /path/to/repository \
  --profile /path/to/profile.json --replacement /path/to/replacement.py \
  --trusted-local --image python:3.12-slim
```

Only committed files are used. Execution supports dependency-free source-tree
imports with a profile selecting one target and its healthy regression examples.
Use `--state-dir /path/to/state` before the subcommand to choose another ledger.

## Model repair and evaluation

```sh
uv run --no-sync docdrift repair --help
uv run --no-sync docdrift evaluate --help
uv run --no-sync docdrift evaluate --strategies execution_only
uv run --no-sync docdrift repair --strategy agent --replay saved-responses.json
```

`execution_only` runs local checks without a model. `--replay` uses labelled
synthetic responses. Real generation requires an explicit `--live --model <id>`
and your own `NEBIUS_API_KEY`; it may consume provider credits. Keep credentials
outside the repository. See [model repair and evaluation](MODEL_REPAIR.md) for
required arguments, frozen inventories, and recorded usage.

## Public inspection and offline contracts

```sh
uv run --no-sync docdrift inspect-github un33k/python-slugify \
  --ref fee5aa338d3bd7a9e36c269e33b496a7848edc44 --doc README.md
uv run --no-sync docdrift sandbox-contract-demo
uv run --no-sync docdrift challenge
```

Public inspection validates a pinned Git tree and inventories examples without
executing downloaded code. The contract demo uses synthetic HTTP responses;
`challenge` checks constructed bad patches statically. Neither establishes
provider execution. The [runtime challenge](VERIFICATION_CHALLENGE.md) separately
exercises the production verifier in real local Docker containers.

The ordinary CLI blocks live Sandbox mutations. The hosted service uses a
separate, bounded execution path; the completed saved-proposal run is documented
in [Sandbox verification](SANDBOX_VERIFICATION.md).

## Development

```sh
export UV_CACHE_DIR="$HOME/.cache/docdrift/uv"
uv run --no-sync pytest -o addopts=""
.venv/bin/python scripts/check_distribution.py --build \
  --dist-dir /tmp/docdrift-dist --cache-dir "$UV_CACHE_DIR"
```

The wheel includes its fixture and MIT license. The distribution check builds
and installs offline using a populated cache. CI runs only when dispatched
manually with its quota acknowledgement. Persistent services need a Python
installation outside temporary storage; see [deployment](JUDGE_DEPLOYMENT.md).
