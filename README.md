# DocDrift

DocDrift repairs one broken Python documentation example and produces evidence
of the original failure, the repaired behavior, and healthy-example preservation.

This initial implementation provides a **manual, trusted local vertical slice**.
It resolves a local Git revision to a full commit, inventories Markdown fences,
freezes an external curator profile, applies a supplied replacement to one code
span, and verifies in fresh offline Docker containers. It exports JSON, a unified
diff, logs, source snapshots, frozen checks, operation identities, and a checksum
ZIP. The included renamed-method example is an owned fixture.

The architecture is preserved in [ARCHITECTURE_PLAN.md](ARCHITECTURE_PLAN.md).
Live Nebius execution and the Nemotron repair loop remain pending. The CLI
offers no provider credentials, live execution switch, or spending options.
NewsBias infrastructure is separate.

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
and `evidence.zip` under `.docdrift/runs/<run-id>/`.

```sh
uv run --no-sync docdrift resume <run-id>
uv run --no-sync docdrift export <run-id>
uv run --no-sync pytest
```

If this workspace restricts uv's usual cache locations, set `UV_CACHE_DIR` and
`UV_PYTHON_INSTALL_DIR` to writable task-specific directories under `/tmp`.
Docker access may also require the workspace's execution approval mechanism.

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
behavior. The owned fixture checks exact JSON output across varied inputs and a
frozen AST covering the API operation and data flow. Those conservative checks
cover this declared fixture; they do not establish arbitrary semantic equivalence.
An AST policy difference alone does not constitute an original behavior failure.

Only the selected Markdown code span can change. Source, tests, manifests,
acceptance profiles, and healthy snippets retain their hashes. Deletion, relabeling,
inserted skips, swallowed exceptions, early exits, and obvious hardcoded output
are rejected. Unsupported and unprofiled examples remain in the inventory and
never enter the verified count. Incomplete checks, changed failure signatures,
timeouts, mismatched images, and truncated output prevent full verification.

Local containers use fresh snapshots, an immutable image, disabled networking,
read-only mounts, a nonroot user, resource limits, and bounded logs. The adapter
is for trusted development inputs. Arbitrary public execution, remote repository
downloads, remote dependency installation, actual model repairs, and a review
UI remain outside this slice.
