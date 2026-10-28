# Try DocDrift

Choose a fresh hosted repair, browse recorded evidence, or verify a supplied
repair locally.

## Fresh hosted repair

1. Open [DocDrift](https://iljas-vps.tail2832de.ts.net:8443).
2. Sign in as `judge` with the passphrase supplied privately in the submission.
3. Select **Run fresh repair**, wait for the result, then open its review or
   download the evidence ZIP.

This generates a new Nemotron proposal and verifies it on Nebius Sandboxes.
You need no provider account, API key, Tailscale account, or local installation.
The example is curator-owned. Each attempt uses one shared slot, including a
failed attempt; the page displays the current allowance. Fifteen remained on
October 28. New admissions end after December 15.

For an access check, open an existing completed review or download instead of
starting another repair. Deployment details are in the [operator guide](JUDGE_DEPLOYMENT.md).

## Recorded evidence

Clone the repository, then open these HTML files in your browser. They work from
disk without credentials, Docker, a web server, or new execution.

| Bundle | What it shows |
|---|---|
| [Development demo](demo/f6/index.html) | Live Nemotron generation with local Docker checks: agent 1/1 verified, one-shot 0/1 after static rejection. |
| [Sandbox supplement](demo/f6-sandbox/index.html) | The unchanged saved agent proposal verified on actual Nebius Sandboxes, with zero new inference. |
| [Held-out comparison](demo/held-out/index.html) | Fresh live Nemotron/Sandbox runs: both strategies verified 2/2 reserved cases. |
| [Constructed verifier challenge](demo/challenge/README.md) | No bad proposal behavior-verified; good manual control verified in real local Docker. |

These are small owned fixtures. The development result is exploratory; the
held-out result shows no repair-rate advantage. Evidence manifests validate
bytes, not authenticity. Each bundle records its provenance and coverage.

## Local verification

Requires Git, Python 3.12, uv, and a running Docker daemon:

```sh
git clone https://github.com/Iljaadam/DocDrift.git
cd DocDrift
uv sync --extra dev --locked
uv run --no-sync docdrift demo --inspect-only
docker pull python:3.12-slim
uv run --no-sync docdrift demo --image python:3.12-slim
```

This applies a supplied manual repair with no provider account or inference
credits. It reproduces the missing-method failure, checks three repaired inputs,
and preserves three healthy inputs in fresh offline containers. It should return
`behavior_verified`. Open the printed `review_path` to inspect the patch,
checks, logs, and downloadable evidence.

Check the resulting ZIP without extraction or execution:

```sh
uv run --no-sync docdrift verify-evidence .docdrift/runs/<run-id>/evidence.zip
```

See the [CLI guide](CLI.md) for saved-run review, recovery, and curated inputs.
