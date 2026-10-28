# DocDrift

Repair a stale Python documentation example and keep the evidence.

DocDrift uses **NVIDIA Nemotron on Nebius Token Factory** to inspect source,
try a repair, and propose a change to one Markdown code block. Independent
checks verify the result and recheck healthy examples. You get a diff, an HTML
review, and a downloadable evidence ZIP.

## Try it

- **Run a fresh repair:** open the [hosted demo](https://iljas-vps.tail2832de.ts.net:8443).
  Judges use the login supplied privately in the submission. No provider account
  or local setup is needed; the page shows the shared run allowance.
- **Explore saved results:** clone this repository and open
  [the recorded demo](docs/demo/f6/index.html) in your browser. It works from disk
  without credentials, Docker, or model calls.
- **Verify a supplied repair locally:** follow the commands below or the
  [judge quickstart](docs/JUDGE_QUICKSTART.md).

## Run locally

Requires Git, Python 3.12, [uv](https://docs.astral.sh/uv/), and Docker.

```sh
uv sync --extra dev --locked
uv run --no-sync docdrift demo --inspect-only

docker pull python:3.12-slim
uv run --no-sync docdrift demo --image python:3.12-slim
```

This local demo applies a supplied manual repair to an owned fixture. It
reproduces the failure, verifies three repaired inputs, and checks three healthy
inputs. It makes no model or cloud calls. Open the printed `review_path` to see
its diff, checks, logs, and evidence download.

For model generation, your own curated repository, saved-run review, and
recovery commands, see the [CLI guide](docs/CLI.md).

## How it works

1. **Freeze:** pin a repository revision, the selected example, and independent checks.
2. **Repair:** give Nemotron source-reading and execution tools within a fixed budget.
3. **Verify:** reproduce the original failure and test the candidate in fresh,
   offline environments. Source, checks, and healthy examples stay protected.
4. **Review:** export the patch, observed results, model usage, and evidence hashes.

The hosted demo generates fresh proposals and verifies them on **Nebius
Sandboxes**. The local CLI uses Docker; its Sandbox simulation mode is explicitly
synthetic and never counts as behavioral verification.

## Recorded results

| Comparison | One-shot verified | Agent verified | Execution |
|---|---|---|---|
| [Source-inspection development case](docs/demo/f6/index.html) | 0/1 | 1/1 | Local Docker; saved agent proposal later reverified on Sandboxes |
| [Two held-out cases](docs/demo/held-out/index.html) | 2/2 | 2/2 | Fresh live Nebius Sandbox runs |

These are small, curator-owned fixtures. The development case shows one instance
of source tools helping; the held-out cases show no repair-rate advantage.
Public repository examples are inspected candidates, not confirmed upstream bugs.
Full counts, provenance, and limitations are in the [evaluation notes](docs/MODEL_REPAIR.md)
and [feedback log](docs/FEEDBACK_LOG.md).

## Verification limits

A successful process exit is insufficient. A verified repair must produce the
expected JSON across the frozen inputs, preserve the required API operation,
and pass static checks that its result reaches the output. This verifies the
stated contracts, not every possible input or semantic equivalence.

Only the selected Markdown span may change. Execution supports trusted,
dependency-free snapshots with curator profiles; arbitrary public repository
execution is outside this release. Evidence hashes check file integrity, not
authenticity. See the [verification challenge](docs/VERIFICATION_CHALLENGE.md)
and [security review](docs/SECURITY_REVIEW.md).

## Documentation

- [Judge quickstart](docs/JUDGE_QUICKSTART.md) — hosted access, saved evidence, and local verification.
- [CLI guide](docs/CLI.md) — commands and curated repository setup.
- [Documentation index](docs/README.md) — evaluation, evidence, provider contracts, and deployment.

[MIT license](LICENSE).
