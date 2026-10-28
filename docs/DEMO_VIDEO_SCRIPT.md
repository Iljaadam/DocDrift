# DocDrift demo video — 2:45

## Recording setup

AMD Software is suitable for this screen recording. Suggested settings:
**1920×1080, landscape 16:9, 30 FPS, AVC/H.264, MP4, 8–10 Mb/s**, with the
microphone enabled. These are practical defaults, not hackathon requirements.
A 2:45 recording at that bitrate is roughly 170–210 MB including audio.
Record a ten-second sample first and check voice volume and code readability.

The [official rules](https://nebiusglobalaihackathon.devpost.com/rules) call for
a video under three minutes, showing the software working, publicly visible on
YouTube, with English materials or an English translation. They list no specific
resolution, codec, or file-size cap; submit the YouTube link in Devpost.
YouTube recommends [MP4/H.264 and 8 Mb/s for 1080p at 30 FPS](https://support.google.com/youtube/answer/1722171?hl=en).
Use screen footage with English narration or captions; a face camera is optional.
Sign in before recording and keep passwords, keys, and notifications off screen.

## Footage and narration

Record this from the [committed F6 bundle](demo/f6/index.html) and separate
[Sandbox supplement](demo/f6-sandbox/index.html), opened from disk. Label the
original comparison **Oct 15 · owned development fixture · live Nemotron /
local Docker**, and the supplement **Oct 21 · saved proposal · actual Nebius
Sandbox verification · zero new inference**. This is saved evidence browsing;
do not stage a new model call or imply the historical comparison ran on
Sandboxes. Disclose cuts and time compression in recorded terminal footage.

| Time | Screen | Narration |
|---|---|---|
| 0:00–0:20 | Bundle landing page and provenance. | “A library changes its API, but its README example stays behind. DocDrift repairs one Python documentation example and exports the evidence a maintainer needs to review it. This is an owned development fixture: real NVIDIA Nemotron calls through Nebius Token Factory, verified in local Docker.” |
| 0:20–0:40 | Saved original snippet, `AttributeError`, pinned source/check identities. | “The saved run reproduces a missing method. Package source, acceptance checks, and healthy examples are frozen. The model can change only this Markdown code span. Exit zero alone does not count as a verified repair.” |
| 0:40–1:00 | Comparison and rejected one-shot proposal. | “Keep the failure visible. One-shot guessed a class-level `build` call and removed the constructor. Static policy rejected the proposal before execution. It receives zero verified repairs.” |
| 1:00–1:25 | Agent proposal transcript: source read, one probe, then diff. | “The agent reads the package source and README, tries one probe, and submits `positions` with `include_empty=True`. The diff changes the example while protected source and checks retain their hashes.” |
| 1:25–1:50 | Successful Docker review: target checks, healthy regressions, execution provenance. | “Fresh offline containers verify three frozen target inputs and three healthy regression inputs. Static data-flow checks require the API result to reach the printed output. The verdict covers those declared contracts, not every possible input.” |
| 1:50–2:05 | Historical F6 comparison counts and usage. | “Agent verified one of one; one-shot zero of one. Total: six model calls, 8,781 tokens, fifteen local snippet operations. Earlier comparisons tied. This case is exploratory, not held out.” |
| 2:05–2:25 | Separate Oct 21 Sandbox supplement: backend, saved proposal, checks and operation counts. | “We then verified the unchanged saved proposal on actual Nebius Sandboxes: twelve verifier operations, three runtime probes, zero new inference. The original still fails; repaired and healthy checks pass. Billing remains unverified.” |
| 2:25–2:45 | Evidence downloads, held-out comparison, hosted judge landing page. | “Download the evidence; its hashes check bytes, not authenticity. Both strategies also verified two of two reserved cases on live Sandboxes. Judges can try a fresh repair through the hosted app using the private login.” |

Before recording, check that every local link and download works from a fresh
checkout. Show the hosted app already signed in and keep credentials out of the
recording. Its landing page and existing completed review need no fresh attempt.
Use the review's section menu to jump between the failure, repair, usage, and logs.
Use the published copies and their provenance notes. The F6 source
inventory hash is
`24edc73aa852e887ae55269d760ce2404bea10e701390c8e66e044bbd3d2f19c`.
Exact usage and the earlier F4/F5 limitations are in [the feedback log](FEEDBACK_LOG.md).
Keep the Sandbox operation counts separate from the original comparison's
fifteen local operations. Its saved repair is the same model output; it is not
a second model evaluation.

The optional constructed bad-patch challenge is outside this 2:45 cut. If added,
label it **Deliberately constructed verification challenge** and trim another
segment to remain under three minutes. Never present its patches as model output.
