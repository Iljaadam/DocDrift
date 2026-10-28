# DocDrift — submission draft

- **Track:** Coding and Agentic Engineering
- **Code:** https://github.com/Iljaadam/DocDrift
- **Demo:** https://iljas-vps.tail2832de.ts.net:8443
- **Video:** add the public YouTube URL after recording.

## Tagline

Repair stale Python documentation with Nemotron. Review the patch and the evidence.

## Inspiration

A library changes its API, but its README example stays behind. A plausible
rewrite leaves maintainers with another job: prove that it works and preserves
neighboring examples. DocDrift combines a bounded repair agent with independent
verification and a portable review.

## What it does

DocDrift pins a repository revision, reproduces one broken Python example, and
freezes its source, acceptance checks, and healthy examples. A Nemotron agent
can read source and run small probes before proposing a replacement for one
Markdown code span.

The verifier rejects misleading shortcuts, tests the repair against varied
inputs in fresh offline environments, and reruns healthy examples. Exit zero
alone is insufficient. The result is a Markdown diff, an HTML review, and an
evidence ZIP containing the source, checks, observed outputs, model transcript,
usage, and hashes.

## How we built it

Python 3.12, NVIDIA `nvidia/nemotron-3-super-120b-a12b` through the Nebius Token
Factory inference API, a bounded tool loop, SQLite recovery records, and isolated
execution. The hosted demo makes fresh model calls and verifies on Nebius
Sandboxes. The local CLI uses Docker.

The agent has source-reading, file-listing, execution, and replacement tools.
It sees the observed failure but cannot change or inspect the independent
acceptance profile. Limits bound calls, candidates, tokens, and execution.
Durable receipts prevent automatic repetition of uncertain provider requests.

## What we measured

| Recorded comparison | One-shot verified | Agent verified | Scope |
|---|---|---|---|
| Original development cases | 2/2 | 2/2 | Owned fixtures; local Docker |
| Supplemental source-inspection case | 0/1 | 1/1 | One exploratory owned fixture; local Docker |
| Reserved held-out cases | 2/2 | 2/2 | Two owned cases; fresh live Sandbox execution |

On the supplemental case, one-shot guessed a missing class-level `build` method
and failed static policy. The agent read source, tried a probe, and submitted
`OccurrenceIndex().positions(words, include_empty=True)`. Three repaired inputs
and three healthy inputs passed. The comparison used six model calls and 8,781
tokens. The unchanged proposal was later verified separately on actual Nebius
Sandboxes with zero new inference.

The once-only held-out comparison used twelve model calls, 15,928 tokens, and
43 Sandbox operations. Both strategies verified both cases. These small results
show one instance of source tools helping, not general agent superiority.

A separate deliberately constructed challenge withheld behavioral verification
from all 16 bad proposals. Seven code replacements entered the real Docker
engine; nine invalid payloads stopped at submission gates. A dummy API call
followed by hardcoded output exited zero but failed behavioral verification.
The good manual control verified. This challenge used 54 local snippet operations,
with no inference, cloud operations, or hosted judge attempts.

Browse the [development demo](demo/f6/index.html),
[Sandbox supplement](demo/f6-sandbox/index.html),
[held-out results](demo/held-out/index.html), and
[constructed challenge](demo/challenge/README.md). Detailed usage and failures
are retained in the [feedback log](FEEDBACK_LOG.md).

## Challenges and lessons

The first private Sandbox image import failed with a registry HTTP 404.
We preserved its receipt and recovered with an existing image instead of
repeating the import. We also separated process success from behavioral success:
a snippet can exit zero while silently producing the wrong answer.

The publication audit found an outdated certificate trust bundle and upgraded
it. Model requests now reject redirects, ignore environment proxies, and omit
provider error bodies from saved errors. See the [security review](SECURITY_REVIEW.md).

## Limits and next steps

This release handles trusted, dependency-free Python snapshots with curator
profiles. The original inventory has 14 cases; public candidates were inspected,
not established as upstream bugs. Owned fixtures and two held-out cases cannot
establish broad accuracy. Frozen checks cover their declared inputs rather than
arbitrary semantic equivalence, and unsigned evidence hashes do not attest origin.

Next steps are a reproduced upstream drift case and broader dependency support.
Synthetic provider fixtures remain labelled and never count as execution.

## Testing instructions

Open the hosted demo and sign in as `judge` with the passphrase provided in the
private testing instructions. Select **Run fresh repair**, then inspect its
review and evidence ZIP. No provider account, API key, Tailscale account, or local
installation is needed. The app shows the remaining shared attempt allowance.

The [judge quickstart](JUDGE_QUICKSTART.md) also offers saved evidence and a free
manual Docker verification route. Maintain hosted access through December 15.
Before submission, resolve whether the fixed shared allowance satisfies the
rules' unrestricted testing requirement and confirm granted-credit funding;
Sandbox billing coverage remains unverified.

## Nebius / NVIDIA feedback

Nemotron's standard tool calls supported the source-reading and execution loop.
A concrete improvement would be clearer Sandbox image-import errors and an
explicit statement of promotional-credit coverage for Sandbox execution and
storage. The [feedback log](FEEDBACK_LOG.md) includes successful calls, failures,
usage accounting, and reproduction details.
