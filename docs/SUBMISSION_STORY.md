## Inspiration

An outdated README example can make a working library feel broken. A renamed
method, changed keyword, or different return value can turn a developer's first
interaction with a project into a debugging session.

We wanted documentation repairs to come with a clear basis for review: the
original failure, a focused patch, and evidence that the repaired example
behaves as expected. That led us to build DocDrift around independent
verification and a portable evidence trail.

## What it does

DocDrift repairs **one broken Python documentation example at a time**.
It pins a repository revision, reproduces the failure, and gives a bounded
Nemotron agent tools to inspect source and try small probes. The agent proposes
a replacement for one Markdown code span.

In one owned development fixture, the agent inspected the implementation and
produced this change:

```diff
-result = OccurrenceIndex().build(words)
+result = OccurrenceIndex().positions(words, include_empty=True)
```

The keyword matters: the documented contract requires empty strings to remain
in the result. A method-name change alone would miss that behavior.

The verifier checks the candidate against frozen inputs and expected outputs,
requires the meaningful API operation and its result flow, and reruns healthy
examples. Source files, acceptance checks, and neighboring examples stay
protected. Unsupported examples remain visible without entering the verified count.

Maintainers receive a diff, a self-contained HTML review with section navigation,
and an evidence ZIP containing source snapshots, checks, observed outputs, model
usage, and hashes. The report distinguishes `execution_passed` from
`behavior_verified`, making the coverage of the verdict visible.

## How we built it

The core is a **Python 3.12 CLI** using NVIDIA
`nvidia/nemotron-3-super-120b-a12b` through **Nebius Token Factory**. We built a
custom tool loop around file listing, source reading, isolated Python probes,
and replacement submission, with limits on calls, candidates, tokens, and execution.
The acceptance profile and known repair remain outside the agent's accessible
repository.

The hosted service verifies fresh repairs on **Nebius Sandboxes**. Docker
provides local execution. Verification uses fresh snapshots and offline guest
execution, while SQLite records run phases and accepted operation IDs for
recovery. An uncertain provider submission is not automatically repeated.

The hosted interface uses HTML, CSS, vanilla JavaScript, and Python's standard
HTTP server. Provider credentials remain on the server. Exported reviews work
from disk without JavaScript, API keys, or new inference.

The current MVP supports trusted, dependency-free Python snapshots with curator
profiles. Public GitHub inspection is available separately from execution.

## Challenges we ran into

**Defining success was harder than generating a plausible patch.** A snippet
can exit zero after swallowing an exception or printing a hardcoded answer.
We combined varied-input checks, protected-file hashes, operation-preservation
rules, and static analysis of whether the API result reaches the output.

Our original exact-AST requirement was too restrictive for equivalent rewrites.
Relaxing it required stronger result-flow checks; constructed bypass cases helped
expose weaknesses in the first implementation. The final checks cover declared
contracts rather than arbitrary semantic equivalence.

Cloud integration also produced real failures. Our first Sandbox image import
failed with a registry HTTP 404. We retained its receipt and recovered using an
existing image without repeating the import. Keeping proposal generation,
execution, and recovery separately recorded made those failures reviewable.

## Accomplishments that we're proud of

We completed a working path from real Nemotron generation to actual Sandbox
verification, a hosted judging interface, and downloadable evidence.

We also kept the evaluation outcomes visible, including ties and rejected proposals:

| Recorded comparison | One-shot verified | Agent verified | Execution |
|---|---|---|---|
| Original development cases | 2/2 | 2/2 | Local Docker |
| Supplemental source-inspection case | 0/1 | 1/1 | Local Docker |
| Two reserved held-out cases | 2/2 | 2/2 | Fresh live Nebius Sandboxes |

The supplemental case was exploratory and curator-owned; its unchanged agent
proposal was later reverified separately on actual Sandboxes with zero new
inference. The agent has iterative tools and a larger call allowance. These
small comparisons do not establish a general repair-rate advantage.

A separate **deliberately constructed challenge** withheld behavioral
verification from all 16 bad proposals. Seven code replacements entered the
real Docker engine; nine invalid payloads stopped at submission gates. The
positive manual control verified. The discarded-result proposal exited zero on
all three inputs and matched one expected output, but still failed behavioral
verification.

The project has **1,027 passing automated tests**, a public MIT-licensed
repository, and saved evidence that can be inspected without provider credentials.
Unsigned archive hashes establish internal integrity, not execution authenticity.

## What we learned

Verification needs to be designed before the repair agent starts optimizing.
Protecting the checks and preserving healthy examples gave us a clearer target
than process exit status alone.

We also learned to measure what tools contribute. Source inspection and a probe
helped on one development case, while the original development and held-out
comparisons tied. That makes identifying when iterative tools help an important
question for broader evaluation.

Finally, recovery behavior and review design belong in the product. Stable
operation IDs, retained failures, and readable evidence help maintainers assess
both the proposed change and the limits of its verification.

## What's next for DocDrift

Our next priorities are to reproduce an independent upstream documentation
failure, add support for pinned dependency environments, and evaluate a broader
set of repository changes against strong baselines.

A later step is an opt-in pull-request workflow that presents the patch alongside
its verification evidence, giving maintainers a clear basis for deciding whether
to merge it. We want broader coverage while keeping the scope and evidence of
each repair explicit.
