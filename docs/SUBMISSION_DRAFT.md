# Submission draft (Devpost)

Draft only. Every number marked `TBD` must come from an actual recorded run.
All execution so far is local Docker. Every Nebius Sandbox claim below is
conditional on Sandbox access (see `STATUS.md`); reword it before submitting
if that access never arrives.
Video shot list: `ARCHITECTURE_PLAN.md` → "Competition and demonstration".

## Tagline

DocDrift repairs broken Python examples in documentation with NVIDIA Nemotron,
and proves the fix in a clean Nebius Sandbox before anyone has to trust it.

## Problem

Libraries rename methods, keywords, and return types; their README examples
silently rot. Maintainers learn from user issues. AI doc tools can rewrite the
text, but "it looks right" is not evidence that the example works.

## What it does

1. Pins a repository commit and inventories every fenced Python example,
   marking unsupported ones (IPython, secrets/services, sketches) instead of
   guessing.
2. Runs the selected example in an offline sandbox and reproduces the failure
   twice, alongside the healthy neighbouring examples.
3. A Nemotron agent reads the pinned source, tries code in the sandbox, and
   proposes a replacement for that one fence only.
4. Static policy rejects patches that delete the example, swallow exceptions,
   hardcode output, or touch source, tests, profiles, or checks.
5. A fresh pristine sandbox re-runs the repaired example against independent
   checks with varied inputs, and re-runs the healthy examples.
6. Output: a small Markdown diff plus a downloadable evidence archive (logs,
   hashes, commands, model transcript).

## How we built it

Python 3.12 CLI. Nebius Token Factory (Nemotron, OpenAI-compatible tool calls)
for the agent; Nebius Sandboxes for every execution, with durable operation
receipts so an interrupted run resumes without resubmitting work. SQLite run
ledger, SHA-256 manifests, ~450 offline tests.

## Evaluation

Frozen before running: 14 cases (4 owned broken incl. 2 held out, 3 healthy,
3 unsupported, 1 setup failure, 3 pinned public examples). Compared
execution-only checking, one-shot Nemotron, and the DocDrift agent with the
same verifier.

| Strategy | Drift detected | Verified repairs | False drift reports | Correct abstentions | Calls / tokens |
|---|---|---|---|---|---|
| Execution only | TBD | n/a | TBD | TBD | 0 |
| One-shot Nemotron | TBD | TBD | TBD | TBD | TBD |
| DocDrift agent | TBD | TBD | TBD | TBD | TBD |

Separate exploratory development result (Oct 15): after freezing an additional
owned source-inspection fixture, agent verified 1/1 and one-shot 0/1 (static
rejection), with 0/1 false drift reports for both on its unrelated healthy example.
Six live model calls used 8,781 tokens; execution was local Docker. This case was
added after the original development results, is outside the fourteen-case
inventory, and does not establish a general advantage. Details: feedback log F6.

Deliberately constructed bad patches (labelled as such, not model output):
16/16 rejected by static gates.

## Honest limits

Owned fixtures are curator-authored; public examples are labelled by
reproduction, not assumed broken. Small evaluation; one run per case is
exploratory. Behavior verification covers the frozen checks only.

## Testing instructions for judges

TBD: depends on the judge-access route (see `STATUS.md` checklist).

## Feedback for Nebius / NVIDIA

See `docs/FEEDBACK_LOG.md`.
