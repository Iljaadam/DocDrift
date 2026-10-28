# Constructed verification challenge

DocDrift checks deliberately bad proposals against the owned renamed-method
fixture. These are constructed inputs, not model-generated repairs.

## Recorded runtime result — October 28, 2026

| Check | Result |
|---|---|
| Bad proposals receiving behavioral verification | **0/16** |
| Bad code replacements entering the real engine | 7 |
| Invalid payloads rejected at submission gates | 9 |
| Good manual control | `behavior_verified` |
| Execution | 54 local Docker snippet operations |
| Model calls / Nebius operations / hosted attempts | 0 / 0 / 0 |

All 16 proposals fail the static challenge. Seven representable code replacements
also enter the production engine with real Docker execution. Whole-document
edits, protected-file edits, and non-text payloads are refused at the submission
boundary; no gate is bypassed to execute an invalid payload.

The most useful negative control keeps the API call but discards its result.
It exits zero on all three inputs and matches the expected JSON on one, yet
receives only `execution_passed`: varied-input checks and result data flow prevent
`behavior_verified`. The good control passes all three repaired inputs and all
three healthy regressions; protected hashes are preserved.

Read the [recorded cases and evidence](demo/challenge/README.md) or
[summary JSON](demo/challenge/report.json).

## Reproduce with local Docker

Use an already installed Python 3.12 image and a new state directory:

```sh
.venv/bin/python scripts/verify_challenge.py --execute \
  --image python:3.12-slim --state-dir .docdrift/my-verifier-challenge \
  --output /tmp/docdrift-challenge.json
```

The script records each case and its engine ledger. It refuses to overwrite an
existing state directory. It performs no inference, image pull, cloud execution,
or hosted admission. Rejected code can stop before candidate execution after
the real original-failure and healthy baselines have run.

## Static coverage

```sh
uv run --no-sync docdrift challenge
```

This separate command parses frozen bytes and Python ASTs without execution.
Its known manual control is `accepted_static`, never behavior-verified.
Cases cover deleting or relabeling a fence, swallowing exceptions, hardcoded
output, discarded API results, skips, NULs, fence injection, empty or non-text
replacements, and protected-file edits or additions.

The file-hash gate checks complete paths and the exact inventory. Only bytes
approved by the one-span replacement policy may change. Unit tests also cover
changes to an existing protected test file using a synthetic sentinel; the owned
fixture itself has no test directory.

Runtime results are actual local Docker evidence, separate from the saved model
comparisons and Nebius Sandbox runs. They cover the declared fixture contracts
and do not establish arbitrary semantic equivalence or cloud qualification.
