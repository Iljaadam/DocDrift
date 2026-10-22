# Submission draft (Devpost)

Draft based on recorded development runs. The historical model comparisons use
local Docker. A separate Oct 21 run verifies the saved F6 agent repair on Nebius
Sandboxes without new inference. Scored held-out evaluation, track eligibility,
and free live-agent access through December 15 remain open in
[STATUS.md](../STATUS.md). The [original demo](demo/f6/index.html),
[Sandbox supplement](demo/f6-sandbox/index.html), and
[2:45 video script](DEMO_VIDEO_SCRIPT.md) can be reviewed without new inference.

## Tagline

DocDrift repairs a broken Python documentation example with NVIDIA Nemotron
and exports evidence of its behavior against frozen checks.

## Problem

Libraries rename methods, keywords, and return types while their README examples
fall behind. A plausible rewrite leaves maintainers with another task: establish
whether it works, preserves healthy examples, and changes only documentation.

## What it does

1. Pins a repository commit and inventories fenced Python examples, keeping
   unsupported and unprofiled examples visible without counting them as verified.
2. Reproduces a selected failure and checks healthy examples using a frozen
   curator profile, package source, and acceptance inputs.
3. Gives a bounded Nemotron agent source-reading and execution tools, then
   accepts a replacement for one Markdown code span.
4. Rejects patches that remove meaningful operations, swallow exceptions,
   hardcode output, or touch protected source, tests, profiles, and checks.
5. Verifies the candidate in fresh offline environments with varied inputs,
   checks that the required API result reaches the printed output, and rechecks
   healthy examples. Model comparisons used local Docker; the saved F6 agent
   proposal also passed a separate bounded Nebius Sandbox verification.
6. Exports a Markdown diff, self-contained HTML review, model proposal transcript,
   logs, source/check snapshots, and a manifest-covered evidence ZIP.

The [real demo](demo/f6/index.html) shows the failed one-shot proposal alongside
the successful agent repair, with the same final verifier for both strategies.

## How we built it

Python 3.12 CLI, live Nebius Token Factory chat completions using
`nvidia/nemotron-3-super-120b-a12b`, a bounded tool loop, local Docker execution,
a SQLite run ledger, and SHA-256 manifests. Durable operation records support
interruption recovery. An offline Nebius Sandbox adapter exercises synthetic
HTTP request/recovery contracts; those responses execute no guest code and are
explicitly unscored. A separate fixed runner performed actual Sandbox execution
on October 21. The private image import failed with registry HTTP 404 (F10);
recovery preserved its receipt and selected an existing Python 3.12 slim image
without another import. Three runtime probes and twelve verifier operations
completed with zero new inference. Sandbox billing remains unverified.

An offline test suite and installed-wheel smoke checks cover the CLI, verifier,
evidence integrity, recovery, and synthetic provider contracts. The archive
integrity checker verifies bytes and member coverage without extraction or
execution; its unsigned manifest is not an origin or execution attestation.

## Evaluation

The original inventory contains 14 cases: four owned broken fixtures (two
reserved as held out), three owned healthy examples, three unsupported examples,
one setup failure, and three pinned public candidates. Public candidates are
inspected inputs, not reproduced upstream bugs. Recorded model evaluations use
the development split; scored held-out results remain **TBD**.

The original development results did not separate the model strategies:

| Recorded comparison | One-shot verified | Agent verified | One-shot calls / tokens | Agent calls / tokens |
|---|---|---|---|---|
| F4, Oct 14: fixture prose stated the fix | 2/2 | 2/2 | 2 / 1,603 | 9 / 12,534 |
| F5, Oct 14: neutral prose; healthy neighbors still showed the current API | 2/2 | 2/2 | 2 / 1,453 | 9 / 12,701 |

For both comparisons, execution-only, one-shot, and agent each detected 2/2
broken examples, made 0/2 false drift reports on healthy examples, and correctly
abstained on 4/4 cases. Execution-only proposes no repairs. The broken-fixture
prose was neutralized and inventories re-frozen before the F5 rerun; these are
development observations, not held-out scores.

F6 (Oct 15) is one separate exploratory comparison on an additional owned
source-inspection fixture and one unrelated healthy example. Its supplemental
inventory was frozen in commit `7faa9e8` before inference; the original
fourteen cases stayed unchanged. There were no retries or fixture changes after
observing the result.

| F6 strategy | Drift detected | Verified repairs | False drift reports | Model calls | Prompt / completion tokens |
|---|---|---|---|---|---|
| Execution-only | 1/1 | n/a | 0/1 | 0 | 0 / 0 |
| One-shot Nemotron | 1/1 | 0/1 | 0/1 | 1 | 520 / 420 |
| DocDrift agent | 1/1 | 1/1 | 0/1 | 5 | 7,100 / 741 |

One-shot retained the missing API as `OccurrenceIndex.build(words)` and removed
the constructor call. Static policy rejected that proposal before execution.
The agent read source and README, ran one probe, and submitted
`OccurrenceIndex().positions(words, include_empty=True)`. The replacement passed
three frozen target inputs and three healthy regression inputs; protected hashes
matched. The agent had a six-call cap and iterative tools; one-shot had one call.

F6 used **6 model calls / 8,781 tokens** and **15 local snippet operations**:
2 shared baselines, 1 agent probe, and 12 verifier operations, excluding Docker
version preflights. No billed dollar amount was recorded. This case was added
after the original development results. It shows one instance of source tools
helping; it is not held out and supports no general superiority claim.
See [feedback entries F4–F6](FEEDBACK_LOG.md).

On Oct 21, the unchanged saved F6 agent proposal was separately re-verified on
Nebius Sandboxes. Run `cb10f48b57264526ada5e04d12bb7641` reproduced the original
failure and returned `behavior_verified` after all three target inputs and all
three healthy regressions passed; protected hashes were preserved. Its twelve
verifier operations and three runtime probes are additional cloud execution,
with **zero new model calls**. This is verification of one saved proposal, not
a new strategy comparison or held-out evaluation. Browse the
[Sandbox supplement](demo/f6-sandbox/index.html). The historical F6 counts and
Docker provenance above remain unchanged; no billed dollar amount is confirmed.

Separately, a deliberately constructed bad-patch challenge rejected 16/16
patches with static gates. Those patches are constructed, not model output,
and the challenge does not establish behavioral verification.

## Honest limits

Owned fixtures are curator-authored. These small, single-comparison development
results are exploratory. Behavior verification covers the frozen inputs and
static policy; it does not establish arbitrary semantic equivalence. Public
repository downloads support inspection only, and arbitrary public execution
and remote dependency installation remain outside this slice.

The original demo uses live Nemotron inference and local Docker execution.
The Sandbox supplement records actual execution of the saved agent repair and
keeps its provenance separate. Synthetic Sandbox contracts are labelled
separately. Neither saved evidence bundle is a functional live-agent service.

## Testing instructions for judges

Open the [saved demo bundle](demo/f6/index.html) from the checkout without keys,
Docker, inference, or a web server. It includes both model outcomes and the
successful repair's downloadable evidence.
The [Sandbox supplement](demo/f6-sandbox/index.html) separately shows the saved
repair's cloud verification without a provider account or new execution.

Follow the [judge quickstart](JUDGE_QUICKSTART.md) to execute a supplied manual
repair locally with no provider account or inference credits. This exercises
failure reproduction, frozen checks, healthy preservation, and evidence export.
It is a separate route from the recorded model repair.

**Unresolved before submission:** a free functional live-agent route maintained
through December 15, and confirmation that the recorded owned-fixture evidence
meets the chosen track's requirements. Saved evidence browsing and the manual
local demo do not resolve that delivery dependency.

The fixed-case private controller and bounded live worker are now implemented
and tested offline, with a twenty-attempt deployment allowance approved by the
owner. Public HTTPS activation, one actual end-to-end acceptance attempt, and
the final held-out comparison are pending. Do not describe the route as
available until those activation checks have been recorded.

## Feedback for Nebius / NVIDIA

[Feedback log](FEEDBACK_LOG.md): model discovery, standard tool-call support,
reasoning-token accounting, development results, and the failed one-shot
proposal are recorded with requests, usage, effects, and concrete suggestions.
