# Supplemental development inventory

This additive inventory was authored on October 15, 2026, after the original
development evaluation. It contains one new owned broken example and its
unrelated healthy neighbor. It is not part of the original fourteen-case
inventory; the files and held-out splits in `fixtures/evaluation/` are unchanged.
Report its results separately from the earlier 2/2 development results.

The source-only fixture documents token positions but calls an obsolete API.
The README does not expose the replacement API. The authoritative method and
empty-token option are available in the package source, which the agent can
inspect with tools. A one-shot model may guess the repair; this fixture tests
the usefulness of source access and does not guarantee an agent advantage.

The repository contains only the README, library, project metadata, and MIT
license. External profiles, independent expectations/checks, manual repair, and
curator provenance must stay outside model context. See
[source_only/README.md](source_only/README.md) for its contract.

Run only this supplemental inventory, with local Docker and no inference:

```sh
uv run --no-sync docdrift evaluate --index fixtures/development/index.json \
  --strategies execution_only --output .docdrift/evaluations/source-only-baseline.json
```

For a small, approved live comparison, use the same index with
`--strategies execution_only,one_shot,agent --live --model <nemotron-id>`.
This consumes Token Factory credits; model calls and tokens are recorded.
Every execution still uses local Docker. Do not add `--include-held-out`.

The index's `not_run` values record the state at fixture freeze. Subsequent
observations belong in run reports and the feedback log, rather than rewriting
the frozen inputs to look like results. `manifest.json` freezes the index and
all fixture artifacts, including the fixture's own manifest. New evaluation
reports identify their inventory by its index SHA-256 and selected case IDs.
