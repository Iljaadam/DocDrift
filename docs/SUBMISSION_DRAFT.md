# Submission draft (Devpost)

Draft based on recorded development runs. The historical model comparisons use
local Docker. A separate Oct 21 run verifies the saved F6 agent repair on Nebius
Sandboxes without new inference. On October 22 both model strategies verified
2/2 reserved held-out cases using live Sandbox execution. Public HTTPS judge
access passed acceptance on October 25. Video, repository publication, final
submission, and judging-period availability remain tracked in
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
   healthy examples. Historical development comparisons used local Docker;
   the saved F6 proposal and fresh October 22 acceptance/held-out runs passed
   separate bounded Nebius Sandbox verification.
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

The private judge service uses a single worker and durable global allowance.
Its startup capability and fresh local HTTP acceptance repair passed on October
22, followed by the reserved live Sandbox comparison. Public HTTPS authentication
and evidence downloads passed on October 25 using that completed job, without
new inference or Sandbox operations.

An offline test suite and installed-wheel smoke checks cover the CLI, verifier,
evidence integrity, recovery, and synthetic provider contracts. The archive
integrity checker verifies bytes and member coverage without extraction or
execution; its unsigned manifest is not an origin or execution attestation.

## Evaluation

The original inventory contains 14 cases: four owned broken fixtures (two
reserved as held out), three owned healthy examples, three unsupported examples,
one setup failure, and three pinned public candidates. Public candidates are
inspected inputs, not reproduced upstream bugs. Historical development results
and the once-only held-out comparison below are reported separately.

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

On October 22 the two originally reserved owned broken fixtures were each run
once under both model strategies, using the same final verifier and live Nebius
Sandboxes. The inventory and controller were frozen before the four jobs;
there were no retries or fixture changes after observing results.

| Held-out strategy | Verified repairs | Model calls | Prompt / completion tokens | Sandbox operations |
|---|---|---|---|---|
| One-shot Nemotron | 2/2 | 2 | 995 / 479 | 20 |
| DocDrift agent | 2/2 | 10 | 12,843 / 1,611 | 23 |

These two small cases show no verified-repair advantage for the agent. The
comparison used 12 model calls / 15,928 tokens and 43 disposable Sandbox
operations. The separate fresh deployment acceptance used four calls / 6,313
tokens and fourteen operations, plus one global startup capability operation.
Browse the [held-out reviews and archives](demo/held-out/index.html) and
[feedback F13/F14](FEEDBACK_LOG.md). No billed dollar amount is confirmed.

Separately, a deliberately constructed bad-patch challenge rejected 16/16
patches with static gates. Those patches are constructed, not model output,
and the challenge does not establish behavioral verification.

## Honest limits

Owned fixtures are curator-authored. The development comparisons are exploratory,
and the once-only held-out comparison has only two broken cases. Behavior
verification covers the frozen inputs and
static policy; it does not establish arbitrary semantic equivalence. Public
repository downloads support inspection only, and arbitrary public execution
and remote dependency installation remain outside this slice.

The original demo uses live Nemotron inference and local Docker execution.
The Sandbox supplement records actual execution of the saved agent repair and
keeps its provenance separate. Synthetic Sandbox contracts are labelled
separately. Saved evidence browsing does not start a live-agent service.

## Testing instructions for judges

Open [the hosted judge](https://iljas-vps.tail2832de.ts.net:8443) using username
`judge` and the passphrase supplied privately in the testing instructions. Select
**Run fresh repair**, wait for its result, and download the review/evidence ZIP.
No provider account, API key, Tailscale account, or local installation is needed.
The hosted fixture is curator-owned; each fresh attempt uses a shared slot,
including failures. Fifteen remained at acceptance on October 25; new admissions
end after December 15. The owner maintains the VPS through judging.

Open the [saved demo bundle](demo/f6/index.html) from the checkout without keys,
Docker, inference, or a web server. It includes both model outcomes and the
successful repair's downloadable evidence.
The [Sandbox supplement](demo/f6-sandbox/index.html) separately shows the saved
repair's cloud verification without a provider account or new execution.
The [held-out bundle](demo/held-out/index.html) separately includes all four
October 22 model outcomes and downloadable evidence.

Follow the [judge quickstart](JUDGE_QUICKSTART.md) to execute a supplied manual
repair locally with no provider account or inference credits. This exercises
failure reproduction, frozen checks, healthy preservation, and evidence export.
It is a separate route from the recorded model repair.

**Unresolved before submission:** review the recorded owned-fixture evidence
against the chosen track's requirements, publish the licensed repository,
record and upload the video to public YouTube, and finalize submission.
Maintain the hosted route and granted-credit funding through December 15;
Sandbox billing coverage remains unverified. The shared fifteen-attempt allowance
needs reconciliation with the official rules' unrestricted free testing
requirement; acceptance of that limit has not been established.

The fixed-case private controller and bounded live worker are running on the
owner's VPS. Startup, a fresh local HTTP acceptance repair, and the once-only
held-out comparison are complete. Five of the twenty approved attempts are
used; fifteen remain for judges. Public HTTPS authentication, status, assets,
and downloads passed on October 25 over verified TLS through a public Funnel IP,
reusing the completed acceptance job. No interactive external-browser session is
claimed. Its private acceptance record is retained by the operator.

## Feedback for Nebius / NVIDIA

[Feedback log](FEEDBACK_LOG.md): model discovery, standard tool-call support,
reasoning-token accounting, development results, and the failed one-shot
proposal are recorded with requests, usage, effects, and concrete suggestions.
