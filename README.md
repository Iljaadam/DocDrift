# DocDrift

DocDrift repairs one broken Python documentation example and produces evidence
of the original failure, the repaired behavior, and healthy-example preservation.

The CLI supports **model repairs and a manual, trusted local vertical slice**.
It resolves a local Git revision to a full commit, inventories Markdown fences,
freezes an external curator profile, applies a supplied replacement to one code
span, and verifies in fresh offline Docker containers. It exports JSON, a unified
diff, logs, source snapshots, frozen checks, operation identities, and a checksum
ZIP, plus a self-contained HTML review. The included renamed-method example is an owned fixture.

The architecture is preserved in [ARCHITECTURE_PLAN.md](ARCHITECTURE_PLAN.md).
[STATUS.md](STATUS.md) records completed work and remaining delivery gates.
Open the [saved real demo bundle](docs/demo/f6/index.html) from a fresh clone:
it includes a live Nemotron agent repair, the rejected one-shot proposal, a
strategy comparison, and downloadable evidence. No credentials, inference,
Docker, or web server are needed to browse it. This is one exploratory owned
development fixture, generated with live Token Factory calls and verified in
local Docker. A [separate Oct 21 Sandbox verification](docs/demo/f6-sandbox/index.html)
reuses the saved agent proposal and verifies its behavior on Nebius Sandboxes
with no new inference. Neither result is held out or a live repair service.
The [Oct 22 held-out comparison](docs/demo/held-out/index.html) separately records
fresh Nemotron/Sandbox runs on two reserved owned cases: one-shot 2/2 verified
and agent 2/2 verified. It includes four reviews, evidence archives, and usage.
For a free local test with no provider credentials, follow the
[judge quickstart](docs/JUDGE_QUICKSTART.md).
The Nebius REST contract and durable submission journal can now be exercised
offline with synthetic responses. Live Nemotron inference is connected to repair
and evaluation. The historical model comparison uses local Docker; the separate
Sandbox run verifies the unchanged saved repair. Remaining delivery work is
tracked in [STATUS.md](STATUS.md).

The private judge service is implemented with one fixed owned fixture, fresh
Nemotron/Sandbox verification, a durable twenty-attempt allowance, and sanitized
downloads. Open [the hosted judge](https://iljas-vps.tail2832de.ts.net:8443) with
the privately supplied shared credentials; judges need no provider account.
Public HTTPS authentication and downloads passed on October 25 using the existing
completed acceptance repair. Fifteen fresh attempts remain in the shared allowance
as of that check; new admissions end after December 15. See the
[judge quickstart](docs/JUDGE_QUICKSTART.md) and
[deployment instructions](docs/JUDGE_DEPLOYMENT.md). The completed F6 evidence
above remains separate from fresh judge attempts.

## Run from a checkout

Requires Git, Python 3.12, [uv](https://docs.astral.sh/uv/), and a usable local
Docker daemon for execution. Inventory does not require Docker.

```sh
uv sync --extra dev --locked
uv run --no-sync docdrift demo --inspect-only
```

Download a public Python image explicitly; DocDrift never pulls an image itself.
The adapter resolves the installed image to an immutable ID before execution.

```sh
docker pull python:3.12-slim
uv run --no-sync docdrift demo --image python:3.12-slim
```

The demo pins its owned fixture, reproduces the missing `tally` method, and uses
the supplied one-method replacement. It requires the frozen word-count and
summary checks to pass for all three inputs. A successful run prints
`behavior_verified`, with its explicit coverage recorded in `report.json`.
This describes local fixture checks and does not establish Nebius runtime use.

The checkout defaults to `.docdrift/`, which is excluded from Git. Each run stores
its report, patch, original/repaired snippets, profile, source snapshots, ledger,
`review.html`, and `evidence.zip` under `.docdrift/runs/<run-id>/`.

```sh
uv run --no-sync docdrift resume <run-id>
uv run --no-sync docdrift export <run-id>
uv run --no-sync docdrift review <run-id>
uv run --no-sync docdrift verify-evidence .docdrift/runs/<run-id>/evidence.zip
uv run --no-sync pytest
```

Open the printed `review_path` in a browser. The page shows the original failure,
diff, separate execution and behavior checks, healthy regressions, provenance,
bounded operation logs, and recorded model usage. It labels manual patches,
synthetic replays, and live model proposals separately. Its download link uses
the adjacent `evidence.zip`; the ZIP also includes the HTML in its SHA-256
manifest. `review` regenerates saved evidence without executing code or making
model/provider requests. A saved review is evidence browsing, not a live repair service.
`verify-evidence` checks ZIP structure, member coverage, CRCs, and SHA-256 hashes
without extracting or executing anything. `integrity_verified` does not prove
origin or substantiate saved execution claims. See [evidence boundaries](docs/EVIDENCE.md).

The CLI wheel includes its frozen owned fixture and license, so inspection,
synthetic contracts, and the static challenge also work outside a checkout.
See [installed distribution validation](docs/DISTRIBUTION.md) for offline build
and installation checks. Hosted CI is manual-only and its runner is disabled by
default while the repository's included Actions quota remains unconfirmed.

If this workspace restricts uv's usual cache locations, set `UV_CACHE_DIR` and
`UV_PYTHON_INSTALL_DIR` to writable task-specific directories under `/tmp`.
Docker access may also require the workspace's execution approval mechanism.

## Model repair and evaluation

`docdrift repair` and `docdrift evaluate` run the Nemotron one-shot baseline,
the bounded tool-using agent, and an execution-only baseline over the frozen
inventory, verifying every proposal through the same engine. They run offline
with synthetic `--replay` responses; `--live --model <id>` sends real Token
Factory requests (approved on 2026-10-14; the user reports approximately $30
promotional credits on 2026-10-15, exact balance and expiry unverified). See
[docs/MODEL_REPAIR.md](docs/MODEL_REPAIR.md).

Evaluations write JSON, Markdown, and a self-contained HTML comparison with
strategy counts, tokens, scope, and links to saved run evidence. Render an
existing evaluation without inference or execution:

```sh
uv run --no-sync docdrift review-evaluation .docdrift/evaluations/dev-live-2.json
```

The original fourteen-case inventory remains frozen. The separate
[supplemental development inventory](fixtures/development/README.md) adds a
source-inspection case and an unrelated healthy neighbor. Select it explicitly
with `evaluate --index fixtures/development/index.json`; its results must be
reported separately. New reports identify the inventory by its index SHA-256.

## Offline contracts and recorded Sandbox verification

Inspect a public GitHub snapshot without authentication or code execution:

```sh
uv run --no-sync docdrift inspect-github un33k/python-slugify \
  --ref fee5aa338d3bd7a9e36c269e33b496a7848edc44 --doc README.md
```

The resolver freezes a full commit SHA once, validates the recursive tree and
every downloaded Git blob, then inventories the selected Markdown. It rejects
unsafe archives, submodules, links, LFS requirements, incomplete trees, and
oversized inputs. Inspection reports `execution: not_run` and
`behavior_verified: false`. The chosen upstream commit is an inspected candidate;
this command establishes no documentation failure or verified behavior.
See [public snapshot boundaries](docs/GITHUB_SNAPSHOTS.md).

Exercise the documented Sandbox request and recovery contract locally:

```sh
uv run --no-sync docdrift sandbox-contract-demo
```

Every provider response, stream, and resource value in this command is synthetic.
It performs no network calls, inference, or repository execution and needs no API
key. It exercises frozen uploads, offline requests, an interruption after durable
acceptance, recovery of the same ID, refusal to repeat an ambiguous submission,
nonzero process status despite service success, cancellation, and artifact bytes.
The resulting labeled report is saved under `.docdrift/contracts/<run-id>/`.
See [the REST contract and live-access gaps](docs/NEBIUS_CONTRACT.md).

The same adapter is connected to `repair` and `evaluate` in explicit simulation:

```sh
uv run --no-sync docdrift evaluate --execution-backend sandbox-simulation \
  --index fixtures/development/index.json --strategies execution_only \
  --output .docdrift/evaluations/sandbox-contract.json
```

This manufactures synthetic HTTP responses from supplied owned fixture contracts.
It needs neither Docker nor credentials and executes no guest code. Rows stay
unscored with `evidence: synthetic_not_execution`; successful mock repairs are
`synthetic_contract_passed`, never `behavior_verified`. `repair` accepts this
backend with `--replay`; `--live` is rejected before client construction.
Interrupted final verification resumes saved operation IDs using the saved
backend. Unresolved uploads and submissions are not retried.

The default Sandbox adapter rejects live mutations; its synthetic mutation path
requires an explicitly selected `httpx.MockTransport`. A separate
[fixed-F6 verification runner](docs/SANDBOX_VERIFICATION.md) supports reuse of
the saved live model proposal with zero current inference: one private image
import, three runtime probes, and 12 verifier operations. It leaves the ordinary
CLI and mocked bridge restrictions unchanged and requires explicitly supplied
credentials plus confirmed coverage or a distinct scoped user authorization.
The user authorized the bounded run while billing is unverified (D25).

The Oct 21 run completed with `behavior_verified`. Its first image import failed
with registry HTTP 404; recovery preserved that receipt and used the existing
`python:3.12-slim` UUID without another import. Three runtime probes checked
Python 3.12 under a nonroot user with only the loopback interface, artifact-byte
retrieval, and terminal cancellation. Twelve verifier operations reproduced the
original failure, checked all three repaired inputs, and preserved all three
healthy checks and protected hashes. Current inference calls: zero.

The [saved Sandbox supplement](docs/demo/f6-sandbox/index.html) is separate from
the historical F6 model comparison and its local Docker metrics. It verifies
only that owned fixture's frozen contracts. Sandbox billing remains unverified;
no confirmed-coverage record has been created. The $0 personal-spend default
retains D25's narrow exception for this bounded run.

Check deliberately constructed bad patches without executing them:

```sh
uv run --no-sync docdrift challenge
```

The static challenge rejects deletion, relabeling, exception swallowing, skipped
checks, hardcoded output, and protected-file edits. Its known manual control is
accepted by static policy only; the report never counts this as behavioral
verification. See [challenge coverage](docs/VERIFICATION_CHALLENGE.md).

The [fourteen-case frozen inventory](fixtures/evaluation/README.md) now includes
the remaining owned import, keyword, return-shape, healthy, unsupported, and setup
contracts. Two broken cases are held out for later model evaluation. Public
candidates and setup reproduction remain unresolved. Local supplied-patch smoke
runs are recorded separately from model-generated repairs and scored evaluation.

## Curated local repository

Only committed snapshot files are inspected; working-tree changes are excluded.
Repository code runs in containers. The current setup recipe supports
dependency-free source-tree imports with an external profile and check file.
The profile explicitly selects one target and its healthy regression examples.
Use the [owned profile](fixtures/renamed_method/profile.json) and
[fixture contract](fixtures/renamed_method/README.md) as the schema example.

```sh
uv run --no-sync docdrift inspect /path/to/local/repository --ref HEAD --doc README.md
uv run --no-sync docdrift run /path/to/local/repository \
  --profile /path/outside/repository/profile.json \
  --replacement /path/to/replacement.py \
  --trusted-local --image python:3.12-slim
```

Use `--state-dir /path/to/state` **before** the subcommand to choose a ledger.
One execution holds that ledger's lock at a time. An interrupted run reconciles
its accepted operation IDs and completed results before continuing. It preserves
the original whole-run deadline and operation limits. Changed frozen inputs are
refused.

## Verification boundary

Execution status and behavior status are distinct. Exit zero alone cannot verify
behavior. Behavior verification requires exact JSON output across varied
inputs, the required API call, and that call's result reaching the printed
output (a static must-flow check of straight-line code). Equivalent rewrites of the known
repair verify; whether the code matches the curator's known-repair AST is
recorded for information only. These checks cover the declared fixture; they
do not establish arbitrary semantic equivalence.

Only the selected Markdown code span can change. Source, tests, manifests,
acceptance profiles, and healthy snippets retain their hashes. Deletion, relabeling,
inserted skips, swallowed exceptions, early exits, and obvious hardcoded output
are rejected. Unsupported and unprofiled examples remain in the inventory and
never enter the verified count. Incomplete checks, changed failure signatures,
timeouts, mismatched images, and truncated output prevent full verification.

Local containers use fresh snapshots, an immutable image, disabled networking,
read-only mounts, a nonroot user, resource limits, and bounded logs. The adapter
is for trusted development inputs. Public repository downloads support inspection
only. Arbitrary public execution and remote dependency installation remain
outside this slice.
