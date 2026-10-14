# Installed distribution validation

The owned renamed-method fixture is packaged under
`docdrift/data/renamed_method/`. Its original source stays in
`fixtures/renamed_method/`; Hatch includes only its nine frozen files. The CLI
uses packaged data after wheel installation and the source fixture during
checkout development. Profiles, independent checks, repair, fixture license,
and manifest retain the same bytes in both archives.

The distribution checker catches a bug that editable development installs hid:
the original wheel lacked the fixture, while `demo` looked outside the installed
package for a checkout-only path. Validation installs a real wheel in a fresh
temporary virtual environment and executes the CLI from outside the checkout.

With the locked development environment and a populated uv cache, run:

```bash
.venv/bin/python scripts/check_distribution.py --build \
  --dist-dir /tmp/docdrift-dist --cache-dir /tmp/docdrift-uv-cache
```

Use a clean output directory containing one wheel and one source archive. Omit
`--build` to check existing artifacts, or add `--artifacts-only` to inspect archive
contents without installing them. Every uv command in the checker uses offline
mode. A missing cached backend or dependency stops validation; it does not enable
downloads. Dependency acquisition for a new development environment is a separate
`uv sync --locked --extra dev` step.

The check validates frozen fixture inventory and SHA-256 hashes, source and wheel
licenses, the console entry point, wheel RECORD hashes, and package-source parity.
It installs the wheel with runtime dependencies exported from `uv.lock`, then
checks console help, `demo --inspect-only`, `sandbox-contract-demo`, and the static
`challenge` command.
The installed smoke strips provider credentials and Python checkout paths,
blocks socket connections, and permits only local Git subprocesses. It runs no
Docker command, target snippet, inference, or provider request. The synthetic
Sandbox demo remains contract evidence rather than remote execution evidence.

## Manual CI and the $0 limit

The GitHub Actions workflow has only a `workflow_dispatch` trigger. Pushes and pull
requests do not schedule its hosted jobs. GitHub may still validate a pushed
workflow definition and create a validation or failed-run record without starting
any jobs. Its quota-confirmation input defaults to false, so a manual dispatch
with that default also skips the job before a runner starts. Do not enable the job
until the repository owner has confirmed unused included Actions minutes and
protection against paid overage. The workflow does not verify billing settings or
enforce an account-level spending cap itself.

The initial pushed definition was rejected before scheduling because
`runner.temp` is unavailable in a job-level `env` expression; that validation
record had **zero jobs**. The cache now uses the literal
`/tmp/docdrift-uv-cache` path. A focused regression check covers this context error
and the manual-only spending gate. Full workflow validation uses `actionlint`;
local lint and regression results do not establish that a hosted job ran.
[GitHub's context availability reference](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#context-availability).

For private repositories, GitHub meters hosted runners against the owner's
included quota and charges usage beyond it when billing permits. This repository's
quota and payment settings remain unconfirmed. Local checks are the current
validation route. [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

If later enabled within confirmed free limits, the workflow uses standard Ubuntu,
Python 3.12, the existing dependency lock, automated tests, and the distribution
smoke. It has read-only repository permissions, pinned actions, no stored checkout
credentials, no provider secrets, no deployment, and no cache/artifact uploads.
Tool and package downloads during initial runner setup are separate from the
offline artifact checks. No hosted job was dispatched or executed to implement
these checks. The initial rejected validation record is separate from actual
hosted execution.

Build and install behavior follows [uv's package guide](https://docs.astral.sh/uv/guides/package/).
Packages built here are local test artifacts; nothing is published to PyPI,
GitHub Releases, hosting, or another external service.
