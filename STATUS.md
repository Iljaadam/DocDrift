# DocDrift implementation status

Deadline: **October 30, 2026, 17:00 UTC**. Entry point for agents: `AGENTS.md`.

## Checklist

Token Factory: key in `~/.config/docdrift/nebius.env`; live inference approved (D5).
Builder Program approval received, per user Oct 21 (D22). This confirms access;
the Builder email promises $25 Token Factory credit in a separate email (D24).
Receipt of that specific allocation, expiry, and Sandbox billing terms remain
unverified; do not add it to the earlier reported balance without reconciliation.
User reports granted credits already on the account, approximately $30 (Oct 15,
D10); exact balance, expiry, and Sandbox coverage have not been checked.
On Oct 22 the user reported **$30.98 in Token Factory credit**; this is not a
balance for partner services or evidence of Sandbox billing coverage (D31).
Tavily, LangSmith/LangGraph/LangChain, Toloka, and Tandem remain unused.
Nebius project ID (user-supplied): `aiproject-e00a0rb50jb0emajfv`.
Sandboxes: access confirmed by one user-approved read-only `GET whoami` on
Oct 16 (F7). The existing bearer key plus this project ID in the `Project` header
returned import, spawn, disposable-spawn, list, cancel, and image-tag permissions.
The user's normal-terminal run created one import operation on Oct 21 (F10),
which failed with a provider-side registry-download HTTP 404 and no result image.
Recovery using an existing public image subsequently completed (F12): three
runtime probes and twelve verifier operations, with the saved repair
`behavior_verified` and no new inference. Billing remains unverified.
The original F3–F6 model comparisons used local Docker; F12 separately verifies
the saved F6 agent proposal on Nebius Sandboxes. The user explicitly authorized
the prepared fixed-F6 Sandbox run while billing clarification is pending (D25).
This supersedes D20's coverage-before-run condition for that bounded run only;
it does not confirm coverage or any dollar spending cap. Default adapters/CLI
still block mutations.
The Oct 21 access-read attempt failed locally (`transport_error`); DNS resolution
returned `gaierror` / `EAI_AGAIN` and the workspace policy rejected a DNS-only
sandbox escalation (`sandbox_approval=false`). No provider response, resource
submission, or live session state was produced by that earlier agent attempt.
The later normal-terminal run reached Nebius (F10). Read-only discovery then
listed existing `python:3.12-slim` UUID `4fa16c8f-62a9-35a4-a4ea-07b7e8cd44ae`
(F11). Its fixed recovery under D27 completed on Oct 21 (F12). Preserve the
consumed operation allowance and receipts; continue with saved evidence.

**Access (milestone 0)**
- [x] Owned renamed-method fixture and independent contract frozen
- [x] Builder Program approval received, per user Oct 21 (D22)
- [x] Token Factory $1 trial key received; live inference approved by user (D5)
- [x] Token Factory promotional credits received, per user Oct 15: approximately $30
  (initially described as $25). Exact balance, expiry, and grant/form route unverified.
  The own-spend restriction discussed on Oct 14 applies to cloud compute, not Token Factory.
- [x] Live Nemotron tool-call response recorded (`docs/FEEDBACK_LOG.md` F2)
- [x] Sandbox access application submitted Oct 15; permission confirmed Oct 16
  by one approved read-only `whoami` (F7)
- [x] Sandbox offline execution, existing-image reuse, result parsing, terminal
  cancellation, and exact-byte artifact download checked live under D25 (F12)

**Manual vertical slice (milestone 1)**
- [x] Local Docker slice: original failure, repaired checks, healthy neighbors, export, resume
- [x] Pinned public GitHub snapshots; offline Nebius REST/receipt contracts
- [x] Prepare dedicated bounded Sandbox re-verification of the saved F6 model
  output: frozen offline plan, pinned official Python OCI manifest, durable
  import/probe/verification receipts, and separate historical/current model usage
- [x] Prepare fixed existing-image recovery after the first import failed:
  pinned discovered UUID, preserved failed receipt, no additional import
- [x] Same saved repair on Nebius Sandboxes: existing-image prep, original
  reproduction, pristine re-verification, operation reconciliation (F12)

**Model repair (milestone 2)**
- [x] Tool loop, one-shot baseline, Token Factory client built and tested offline (`docs/MODEL_REPAIR.md`)
- [x] Safe stop on malformed proposals and budget limits (tested with synthetic responses)
- [x] First live call: `nvidia/nemotron-3-super-120b-a12b`; `tools` supported (F1, F2)
- [x] Live Nemotron repair passes independent checks on renamed_method (F3; local Docker execution)
- [x] Exact-AST check relaxed to outputs + required call + must-flow (D3; hardened after the
  first version accepted 11 constructed bypasses, `docs/MODEL_REPAIR.md`)

**Verification challenge (milestone 3)**
- [x] 16 constructed bad patches rejected by static gates
- [ ] Same challenge run through the live verifier

**Evaluation and review (milestone 4)**
- [x] 14-case inventory frozen; two held-out broken cases reserved
- [x] Execution-only and one-shot baselines + `docdrift evaluate` harness
- [x] Wire `repair`/`evaluate` through offline Sandbox bridge with persistent synthetic
  responses; live Sandbox transport remains disabled, outcomes unscored
- [x] Live development-split run: one_shot 2/2, agent 2/2 verified (F4)
- [x] Fixture prose made neutral and re-frozen (F5); dev rerun still 2/2 for both strategies
- [x] D9 approved Oct 15: frozen supplemental source-inspection development fixture
  and unrelated healthy neighbor (`fixtures/development/`); original 14 cases unchanged
- [x] Single live supplemental comparison: agent 1/1 verified, one_shot 0/1 static
  rejection; 8,781 tokens, local Docker only (F6). No general advantage claimed.
- [x] Scored held-out run, once (D8): one_shot 2/2 and agent 2/2 on live Sandboxes (F14)
- [x] Self-contained HTML review in evidence ZIPs; `docdrift review <run-id>` renders
  saved live Nemotron repairs without inference/execution or rescoring (Oct 15)
- [x] HTML strategy comparison with inventory fingerprints and `review-evaluation`
- [x] Offline `verify-evidence` validates ZIP structure, manifest coverage, CRCs,
  and hashes without extraction or execution; no origin/execution attestation
- [x] Free credential-free local judge quickstart (`docs/JUDGE_QUICKSTART.md`);
  demonstrates a manual repair, so free live-agent access below remains unresolved
- [x] CLI wheel with fixtures, offline install check

**Submission (milestone 5)**
- [x] Package a sanitized demo from saved real Nemotron/Docker F6 evidence:
  `docs/demo/f6/index.html`, both proposals, comparison, repair review, evidence ZIP,
  original hashes/redaction disclosure, and deterministic offline packaging script
- [x] Package separate actual Sandbox verification of the same saved proposal:
  `docs/demo/f6-sandbox/`, review, evidence ZIP, runtime record, and disclosed
  redactions; original local Docker comparison preserved
- [x] Implement private fixed-case judge service with durable global quota,
  single worker, fresh model/Sandbox path, sanitized artifacts, and VPS setup
- [ ] Activate and accept the private judge URL on this VPS through Dec 15;
  keep DocDrift units/state/route separate from NewsBias (D31)
- [ ] Record video under 3 minutes (2:45 saved-F6 script in `docs/DEMO_VIDEO_SCRIPT.md`)
- [x] Record Nebius/NVIDIA API feedback and actual failures/successes (F1–F12 in
  `docs/FEEDBACK_LOG.md`); no external message sent
- [ ] Finalize Devpost write-up and submit (`docs/SUBMISSION_DRAFT.md` now records
  actual F4/F5/F6 results; held-out results and free live-agent access remain open)

**Decision dates**
- Oct 22 access fallback is no longer triggered: permission confirmed Oct 16;
  actual Sandbox runtime verification completed Oct 21 (F12). Credit coverage
  and formal track qualification remain unconfirmed.
- Sandbox access after ~Oct 26: swap only the final verification onto Sandboxes; keep the rest.
- Keep inference bounded and log tokens: the approximately $30 balance is user-reported,
  not an independently verified budget (first repair ~7k tokens).

**Next:** the owner needs to enable Tailscale Funnel once in their existing
account; the enablement link was requested asynchronously. Then the agent can
finish public HTTPS authentication and artifact-download checks against the
already completed acceptance job, without another fresh attempt. Both DocDrift
services are running and enabled. Five of D31's twenty attempts are used and
fifteen remain for judges. Do not repeat activation or the held-out comparison.
After HTTPS acceptance, record the under-three-minute video, finish the Devpost
write-up, and review repository publication. Billing clarification remains open.

## Resume handoff — October 22, 2026

Host access is now verified: DNS, GitHub SSH, the user service manager, and
Tailscale are reachable. The VPS's exact HTTPS origin is
`https://evipeer-box.tail113e81.ts.net:8443`; Tailscale initially had no Serve or
Funnel routes and DocDrift ports 8765/8443 were unused. The Funnel command is
waiting for the owner's account enablement. No public HTTPS or external-browser
acceptance is claimed yet. Do not change another route or NewsBias service.

Private login configuration is in `~/.config/docdrift/judge.env`; the generated
password is only in `~/.config/docdrift/judge-password.txt`, both mode 600. The
username is `judge`. Never put the password into chat, Git, evidence, or a video.
Both dedicated user services are active and enabled, user lingering was already
on, and the web process binds `127.0.0.1:8765`. Only the worker has the provider
key. Actual HTTP checks reject missing authentication and foreign origins and
serve the saved and fresh evidence. Installed systemd units parse cleanly after
fixing `EnvironmentFile=` whole-path quoting; parser warnings now fail the
regression test, including paths with spaces and percent characters.

The one reserved startup capability operation
`01a164f6-c09a-768c-84fc-b299158aa936` succeeded: Python 3.12, UID 65534, and only
loopback in the guest. Local HTTP acceptance job
`04afd40e6053471d91bd321cd93993dd` returned `behavior_verified` with four model
calls / 6,313 tokens and fourteen disposable Sandbox operations. Downloaded
review/ZIP and repeated-request idempotency passed without a second attempt.
Its run ID is `5bcab3132c714a1280bc92d53e4b3bd5`.

The four reserved held-out jobs are complete, once each: one_shot 2/2 verified
and agent 2/2 verified on `renamed_import` and `changed_return_shape`. They used
12 model calls / 15,928 tokens and 43 disposable Sandbox operations, with the
original inventory and controller frozen. There is no verified-repair advantage
for the agent on these two cases. See F13/F14 in `docs/FEEDBACK_LOG.md` and the
portable sanitized bundle at `docs/demo/held-out/index.html`.

Together, this deployment has used five attempts, sixteen model calls / 22,241
tokens, and 58 Sandbox operations including the startup check. Fifteen public
attempts remain; billing/credit coverage is still unverified. The quota database,
external binding record, and completed F6 state must remain intact. Worker
failures/interruption pause later jobs and never automatically retry uncertain
requests. Existing expiration remains December 16, 00:00 UTC.

Durable private deployment records and downloaded acceptance artifacts are in
`.docdrift/judge/deployment/`; the original jobs and provider receipts remain
under `.docdrift/judge/jobs/`. `.docdrift/judge/held-out-comparison.json` is the
actual completed comparison. The four public presentation ZIPs passed unsigned
manifest integrity checks; they are not origin or execution attestations.

Validation: **1,015 tests pass** after the systemd path fix. Earlier offline
package/installed-wheel and JavaScript checks passed; no later runtime source
change was made. The prepared service and fix were pushed to private
`origin/main`, followed by the deployment/result documentation and evidence at
`217f064`. The original worktree's 211 files were checked against that exact
prepared commit, then its Git metadata was fast-forwarded without changing any
worktree byte or private state. Normal Git delivery now works from this checkout.
The GitHub repository remains private. No Tavily, LangSmith, Toloka, Tandem, or
paid hosting account was used.

## Previous resume handoff — October 21, 2026

Builder access is now user-confirmed (D22); actual Sandbox execution, import,
and storage coverage with no personal charges remains unconfirmed. The user
provided the $25 Builder credit offer and is unsure whether the current beta is
free (D24). Public research found an explicitly free February ConTree early-access
announcement, followed by a May migration into Token Factory without a current
free-price commitment. Sources and an unsent provider question are saved in
`docs/SANDBOX_VERIFICATION.md`; ask the provider rather than repeating the same
coverage question to the user. D25 now authorizes the fixed-F6 run while that
answer is pending; its mode-600 scoped record is saved and validated at
`.docdrift/access/sandbox-authorization-2026-10-21.json`. No confirmed-coverage
record was invented. The runner now accepts this separate authorization schema
and records billing as unverified in runtime reports, preflight, frozen execution
contracts, and exported evidence.
Tavily and
LangChain credentials were supplied but have not been used or saved. No extra
service integration is needed for the prepared F6 verification.

The offline plan was revalidated against the unchanged published evidence.
Fixed two recovery gaps before activation: a requested cancellation that finishes
before image assignment now resumes from its matching completed receipt, and
known operation/attempt UUIDs survive acceptance-persistence failures in both
the runtime report and stderr. Stderr keeps those IDs even when the report cannot
be written. Regression cases use synthetic responses/failures with networking
blocked; they are not new provider results. Default live-execution restrictions,
the one-import/three-probe/twelve-verification scope, and both frozen inventories
are unchanged.

The user subsequently ran the command from their regular terminal. Nebius
accepted the private import at 17:08:04 UTC on Oct 21; it failed while fetching
the digest-pinned Python image with HTTP 404. The saved operation contains no
exact failing registry URL or evidence of the underlying 404 cause. No image,
probe, verifier run, or inference resulted. The one import attempt is consumed.
Raw response SHA-256:
`c9eaa5d1fd3e121f87c47c75b75951a6288dfdf8765735b6f78783b348fd1ab5`.

The runner now returns saved terminal failed/cancelled imports immediately
without another GET or POST, retaining operation/attempt IDs and unchanged
receipts. New read-only `images` discovery makes one filtered public-image GET,
saves sanitized UUID/tag pairs separately, and neither selects an image nor
changes the live state. The user ran discovery at 17:16:44 UTC and supplied its
15-image inventory (F11), including the immutable Python 3.12 slim reference.
Inventory SHA-256:
`6cf75fc2ca61dab5732d4016586f0296218dd154923ef0f7c5fbbc094c116250`.

D27's recovery is now implemented and prepared. Its separate mode-600 record at
`.docdrift/access/sandbox-f6-existing-image.json` pins the exact selected UUID,
inventory bytes, failed operation ID, and failed response bytes. It requires the
unchanged original terminal failed receipt/session before any upload, probe, or
verifier ledger, then adds an immutable recovery binding without replacing that
identity or receipt. A narrowed image inspection precedes selection; saved
selection survives restarts without another inspection or import. Further
imports and reads that would overwrite the frozen failed response are blocked.
Provenance names the existing image separately from the failed OCI source;
billing remains unverified. Before activation, the recovery record was validated
offline, with no request or session change. Pre-recovery report/session copies were saved under
`.docdrift/access/sandbox-f6-before-image-reuse-{runtime-report,session}.json`.

The user completed recovery on **Oct 21** (F12); durable execution receipts span
approximately 17:43:32–17:43:55 UTC. The displayed 17:53:11–17:53:12 runtime
report describes a later completed resume, not the original execution duration.
The Python probe reported Python 3.12, effective UID 65534, and only `lo`;
the retained artifact downloaded with exact matching bytes. The cancellation
operation is terminal `CANCELLED`; the resume report's already-cancelled
observation does not establish a measured cancellation race or latency.
Run `cb10f48b57264526ada5e04d12bb7641` reproduced the original `AttributeError`,
verified three repaired target cases and three healthy regression cases, and
preserved source/check hashes. Its twelve verifier operations are separate from
the three probes and historical failed import. Current inference is zero;
historical generation remains five calls / 7,841 tokens. The unsigned original
archive SHA-256 is
`f94b30506afc437476c2a74784c7c71187ffb8e8951d76fb8a330d18042be275`.
The public supplement at `docs/demo/f6-sandbox/` preserves separate cloud
provenance without changing the original local Docker comparison or claiming
held-out results, signed attestation, formal qualification, or confirmed billing.

Validation: **824 tests pass**, including synthetic recovery lifecycle, restart,
source-binding, and receipt-preservation checks. Separately, two deterministic
offline bundle builds match byte-for-byte; the public archive verifies 39 payload
members, 35 of 40 total original ZIP members are unchanged, and 73 checked local
links resolve. Its SHA-256 is
`ec8d789ded0c343dae4c9197893002389613cf42566ac4b80bb72d66062dd97c`.
Tests and packaging make no new provider request or execution claim.

The attempted access read could not reach Nebius: local DNS failed and the
workspace's granular policy refused sandbox escalation. No matching connector
was found in the plugin search results. The local failure record is
`.docdrift/access/sandbox-network-failure-2026-10-21.json`; it contains safe error
codes and counts, not the key. The later normal-terminal run created
`.docdrift/sandbox-f6/`; keep its failed receipt, session identity, runtime report,
and raw operation response intact.

Next: use the saved supplemental bundle and updated video script. Do not reset
state or edit the bound inventory, authorization, or recovery record. No new
inference or cloud verification is needed for F12.
The held-out run (D8), funded free live-agent judge access through Dec 15,
and video recording remain open. The user's completed live run is recorded
separately from the agent's offline evidence audit and packaging; the latter
make no provider request, inference, deployment, external message, or push.

## Previous resume handoff — October 16, 2026

The saved real F6 demo is packaged at `docs/demo/f6/index.html`. A fresh clone can
browse its comparison, successful agent repair, failed one-shot proposal, and
downloadable evidence ZIP without `.docdrift/`, credentials, Docker, or a server.
README and the judge quickstart link it. The submission draft now uses actual
F4/F5/F6 counts and usage, and `docs/DEMO_VIDEO_SCRIPT.md` is a concrete 2:45
saved-evidence script linked from the architecture plan. The video is not recorded.

The bundle contains 16 files (about 152 KB). Only two distinct private path values
were redacted from report/ledger copies; the four JSON pointers and original
value hashes are disclosed in `docs/demo/f6/provenance.json`. HTML and the unsigned
ZIP manifest were regenerated; model proposals, comparison JSON/Markdown, source,
checks, snippets, and logs retain their original bytes. All 50 saved input files
remain unchanged. Both frozen inventories remain unchanged. Packaging made no
inference, snippet execution, live Sandbox call, deployment, or push. A separate
approved access check is recorded below.

Published ZIP SHA-256:
`ac8bd589d9455a897563e4cac1afab27ebd219d2ccb98c933ebde6a6a185944b`.
The original ZIP hash remains the October 15 value below. Offline integrity
verification checks all 39 manifested files. All 28 local HTML links/anchors
resolve; repeated builds match byte-for-byte. These are unsigned integrity
checks, not execution or origin attestations.

Rebuild only when original saved inputs are available:
`.venv/bin/python scripts/package_demo.py`. A fresh clone already contains the
published bundle; it need not rebuild. The script pins the original input hashes
and refuses different evidence. Verify the published archive with
`.venv/bin/docdrift verify-evidence docs/demo/f6/agent/evidence.zip`.

User approved one read-only `GET whoami` on Oct 16 (D19); it succeeded at
14:37:10 UTC in 0.168 seconds. All six returned permissions are true: `import`,
`spawn`, `spawn_disposable`, `list`, `cancel`, `set_image_tag`. Reported limits:
instance timeout 3,600 seconds, concurrency 50, layer 12,884,901,888 bytes;
image import concurrency 8 and timeout 3,600 seconds. These are API-reported
limits, not exercised capabilities or a budget. Filtered response/schema record:
`.docdrift/access/sandbox-whoami-2026-10-16.json` (mode 600, gitignored). Token
identity/expiration were omitted; the key remains outside the repo.

This was the first live Sandbox call: one access GET, zero compute operations,
zero inference. The six permission booleans match the adapter's expected schema.
Credit coverage, image/Python availability, network denial, execution, image
reuse, cancellation, artifact download, and recovery remain unverified. The
follow-up request to proceed authorizes the planned bounded verification once
the $0 spending constraint is established (D20). Historical F6 execution stays
local Docker. D8 and free functional live-agent access through December 15 remain
unresolved. No new model evaluation is needed to browse the demo or record its
video.

**Sandbox step prepared, not run:**
`scripts/verify_saved_f6_sandbox.py prepare` now freezes the committed evidence,
proposal, original source, checks, and exact twelve verifier phases into
`.docdrift/sandbox-f6-plan/`. It works offline without the original `.docdrift/`
run or its deleted temporary Git repository. The dedicated `run` path permits
one private digest-pinned Python import (120-second limit), three fixed runtime
probes (Python 3.12/nonroot/network interfaces, retained-artifact download, and
cancellation), and twelve verifier operations (30 seconds each). It saves
submission receipts before requests, resumes accepted IDs without another POST,
and refuses uncertain retries or changed plan/project/image/coverage bindings.
Default simulation and CLI guards are unchanged.

The new run preserves the original model transcript and identifies it as a
saved live proposal; current inference usage is zero, with prior generation
shown separately. Provider `signal=-1` is normalized to no terminating signal,
and documented UTF-8 stream aliases are accepted. These compatibility changes
and the runner are tested locally with synthetic HTTP responses, not real
Sandbox execution. Published F6 files still reproduce byte-for-byte.

No coverage record was invented or created. The actual Sandbox approval's
billing terms were requested from the user and remain unanswered. Public usage
and billing docs do not establish this project's free/grant coverage. Preparation
consulted public documentation and made one credential-free public Docker Hub
tag lookup to pin the Linux amd64 manifest; no further live Sandbox API request,
new inference, resource creation, deployment, or push occurred. To resume, read
`docs/SANDBOX_VERIFICATION.md`; establish actual coverage first, then use the
prepared runner. Preserve `.docdrift/sandbox-f6/` if any future submission is
incomplete; do not delete receipts and resubmit uncertain work.

## Previous resume handoff — October 15, 2026

The user is waiting for agent usage limits to reset and requested this handoff.
This turn prepares notes only. **Resume with the real demo bundle, not another
core implementation pass or fresh evaluation.** Local demo preparation follows
the user's intent to continue; deployment, a new live service, and standing
automatic pushes have not been authorized.

**Current state:** all implementation is pushed through `5b83540` on origin/main
(feature commit `1a1bf4b`). 644 tests pass; installed-wheel smoke includes the
synthetic repair and integrity checker with sockets and non-Git subprocesses
blocked. A real local Docker demo still passed 12 operations. The handoff update
itself will be a subsequent local documentation commit unless separately pushed.
Keep both frozen inventories unchanged: `fixtures/evaluation/` has the original
14 cases; `fixtures/development/` is the separate two-case addition. No held-out
case has been supplied to a live model, and no live Sandbox call has occurred.

**First deliverable:** a small committed sample that a fresh clone can browse
without `.docdrift/`, credentials, inference, or a web server. Include the real
source-only comparison, its successful agent repair and evidence ZIP, and its
failed one-shot proposal. Make local links work and clearly label owned fixtures,
live Nemotron generation, and local Docker execution. Preserve original saved
evidence. Inspect copied artifacts for secrets and identifying paths; disclose
any redaction, regenerate affected manifests/links, and run `verify-evidence`
on each published evidence ZIP. Never replace failed baseline evidence with a
success or present synthetic Sandbox output as real execution.

**Existing inputs on this machine (gitignored; do not regenerate them):**

- `.docdrift/evaluations/source-only-live-1.json`, `.md`, and `.html`: F6,
  one exploratory comparison on the additional owned development case.
- `.docdrift/runs/4fd82cb8be7a449e8815d5366665f4ac/`: real agent repair;
  `review.html`, `report.json`, `repair.json`, `repair.patch`, and `evidence.zip`.
  Original ZIP SHA-256:
  `3edb8afb8716de4be73d1472b2a65c04ef990ce745f70c10869fabaac802e346`;
  all 39 manifested members and loose files checked at this handoff.
- `.docdrift/proposals/34303fa5d21f4213bccec9827b0e28cf.json`: failed one-shot
  (`OccurrenceIndex.build(words)`, static rejection: constructor removed).
- `.docdrift/proposals/d718ad233d6a4bf2b393b2e45d591522.json`: successful agent
  source reads/probe and `positions(words, include_empty=True)` submission.
- `.docdrift/evaluations/dev-live-2.json`: earlier original development results;
  both model strategies 2/2, reported separately from F6. The old report predates
  inventory fingerprints; do not silently add today's inventory identity.

F6: agent 1/1 verified, one-shot 0/1 static rejection, no false drift reports on
one unrelated healthy example; 6 calls / 8,781 tokens / 15 local snippet
operations. This case was added after the earlier development results and is
not held out; no general superiority claim. Exact provenance and usage are in
`docs/FEEDBACK_LOG.md` F6. Its frozen index SHA-256 is
`24edc73aa852e887ae55269d760ce2404bea10e701390c8e66e044bbd3d2f19c`.

**After the bundle:** link it from README and the judge quickstart, update
`docs/SUBMISSION_DRAFT.md` using actual development results (its conditional
Sandbox wording and old test count still need reconciliation), and turn
`ARCHITECTURE_PLAN.md` → Competition and demonstration into the final short
video script. At that historical handoff, scored held-out results were TBD;
the once-only comparison is now complete in F14. A free
functional live-agent route through Dec 15 is still a delivery dependency;
the existing credential-free quickstart demonstrates a manual local repair.

If the next agent is on a different machine, the saved `.docdrift/` inputs will
not come from Git. Locate or request transfer of the existing artifacts before
making a real-run demo; do not invent them or silently spend credits rerunning.
For checks use `UV_CACHE_DIR=/tmp/docdrift-uv-cache` if uv's normal cache is
restricted. Docker and Git metadata writes may need workspace escalation;
use the repo's documented commit identity. No more feature work is required to
start packaging the demo.

## Decisions

Who decided what, and when. Don't reverse one without the user.

- D1 (user, Oct 14): Pet project. Optimise for a working, honest, demo-able submission;
  skip ceremony. `AGENTS.md` plus this file are the cross-agent handoff.
- D2 (user): $0 personal spend; only granted free credits.
- D3 (user, Oct 14): A repair is behavior-verified when every frozen input gives the exact
  expected JSON, the required API call is present, and its result definitely reaches the
  printed output. The known-repair AST match is recorded, not required. Rules and threat
  model: `docs/MODEL_REPAIR.md`.
- D4 (agent, Oct 14): Per-case repair budget: 8 model calls, 2 candidates, 4 sandbox runs,
  2 malformed responses, 2048 completion tokens per call, 60k tokens total; temperature 0;
  no automatic retry.
- D5 (user, Oct 14): Live inference approved on the $1 Token Factory trial key. The user
  was asked to confirm no card and no auto top-up and replied "yes go ahead".
  Sandbox calls were not approved then; D19 later approves one access GET only.
- D6 (agent, Oct 14): Working model `nvidia/nemotron-3-super-120b-a12b`: tool calling
  verified (F2). The other Nemotron IDs are listed in F1.
- D7 (user, Oct 14): Broken-fixture README prose neutralised and re-frozen before any
  held-out model run (F4, F5).
- D8 (proposed by agent, awaiting user): run the held-out split once, after Sandbox wiring.
  If there is no Sandbox by Oct 22, run it on local Docker and label it so.
- D9 (user-approved Oct 15, "go for it"; originally proposed by agent): add a
  source-inspection development fixture with no current-API neighbor or intended
  traceback hint. Test whether source tools help; one-shot guessing remains possible
  and no agent advantage is guaranteed. Keep original held-out cases unchanged.
- D10 (user, Oct 15): Token Factory credits are already on the account; user estimates
  approximately $30 after initially saying $25. Record this as user-reported receipt,
  not an exact verified balance or evidence of Sandbox coverage. The $0 personal-spend
  limit and separate Sandbox approval requirement continue to apply.
- D11 (agent, Oct 15): Continue the unblocked HTML review work using saved run evidence.
  `docdrift review <run-id>` regenerates HTML and its checksum ZIP without inference,
  execution, or rescoring. Leave D8/D9 proposed; no standing push authorization inferred
  from the user's approval to push the two previous commits.
- D12 (user, Oct 15): Supplied the Nebius project ID recorded above and reported
  applying for Sandbox access. Await provider approval; this is not confirmation
  of access, credit coverage, or authorization for a live Sandbox call.
- D13 (agent, Oct 15): Keep D9 in a separate supplemental development inventory;
  preserve the original fourteen-case bytes and prior results. Fingerprint new
  evaluation inputs and retain all proposal transcripts, including failures.
  Compare once with bounded approved inference after fixture freeze; no retries
  or fixture tuning to manufacture an agent advantage.
- D14 (user, Oct 15, "let's do that both"): Build offline Sandbox integration and
  the offline evidence-integrity command while provider approval is pending.
  This grants no live Sandbox call authorization.
- D15 (agent, Oct 15): Synthetic execution uses `synthetic_not_execution` evidence,
  unscored evaluation rows, zero real compute operations, and
  `synthetic_contract_passed` instead of `behavior_verified`. Persist upload and
  execution receipts before requests; resume accepted IDs, never retry uncertainty.
  Integrity verification checks unsigned bytes and makes no authenticity or
  execution-attestation claim.
- D16 (user, Oct 15, "push it"): Push the accumulated local work to origin/main.
  This is approval for the current push, not a standing automatic-push rule.
- D17 (user, Oct 15): Requested a persistent handoff while waiting for agent usage
  limits, so the next agent can continue demo preparation from existing evidence.
  This turn does not start the demo build or grant live Sandbox/hosting access.
- D18 (user/agent, Oct 16): User requested packaging the real demo from saved F6
  evidence with no new evaluation. Publish a sanitized offline bundle retaining
  both the failed one-shot and successful agent outcomes, original input hashes,
  and explicit redaction/rebuild provenance; preserve original saved artifacts
  and frozen inventories. User expects Sandbox access but has not yet approved
  the separately requested single read-only check. No deployment or standing
  push authorization is inferred.
- D19 (user, Oct 16, "i approve go"): Approved the pending single read-only
  Sandbox `GET whoami`. It succeeded with the existing key/project; six permission
  booleans are true (F7). This authorizes the access check only, not provisioning,
  execution, new model evaluation, deployment, or further live calls. The $0
  personal-spend limit and unverified Sandbox credit coverage remain in force.
- D20 (user/agent, Oct 16, "proceed with what we planned"): Continue the planned
  Sandbox verification using saved F6 output without another model evaluation.
  Bound activation to one private image import, three fixed runtime probes,
  and twelve pristine verifier operations. This retains the $0 personal-spend
  rule: actual execution/import/storage coverage and no personal charges must
  be established before resource requests. User was asked what approval covers;
  no factual confirmation has arrived. Prepare and test the concrete runner
  offline meanwhile; no deployment, held-out inference, or push is authorized.
- D21 (agent, Oct 16): Keep the default Sandbox adapter and synthetic CLI guarded;
  isolate planned live activation to the pinned F6 plan, explicit factual
  coverage record, immutable image/project, durable bounded receipts, and exact
  allowed inputs. Reuse the saved proposal unchanged, reporting zero current
  inference and historical generation separately. Accept documented no-signal
  and UTF-8 wire representations without weakening behavior checks.
- D22 (user, Oct 21): Builder access acquired. User also supplied Tavily and
  LangChain service credentials and offered Toloka/Tendem credentials if needed.
  Availability does not require adding those services: the planned next step is
  still saved-F6 Sandbox verification. No new grant amount, expiry, or factual
  execution/import/storage coverage statement was supplied. The D20 scope and
  $0 personal-spend requirement remain in force; credentials stay out of tracked
  files and evidence.
- D23 (agent, Oct 21): Allow a terminal missing source image only for the explicitly
  requested cancellation probe's matching completed `CANCELLED` receipt. Keep
  execution image checks strict. Preserve validated operation/attempt UUIDs
  in diagnostics for manual reconciliation, including stderr when report storage
  fails; this does not authorize resubmitting uncertain operations.
- D24 (user/research, Oct 21): User quoted the Builder approval email: $25
  Token Factory credit is coming separately; partner offers are $100 LangSmith,
  $25 Tavily, $50 Toloka, and $50 Tandem. These are offered benefits, not verified
  redeemed balances or Sandbox billing coverage. User is unsure whether beta
  usage is free. Official February ConTree early access was advertised as free;
  the May Token Factory migration and current docs do not confirm current free
  execution/import/storage. Preserve D20's $0 gate; obtain provider clarification
  using the saved draft instead of asking the user to guess or treating a zero
  diagnostic `cost` field as billing proof. No provider message is authorized or
  sent, and no additional grant is assumed received.
- D25 (user, Oct 21): "We will wait for the answer but in the meantime let's use
  it, i give permission" explicitly authorizes the prepared fixed-F6 Sandbox
  verification despite unverified billing. Supersede D20's prior-coverage gate
  only for this one-import/three-probe/twelve-verification scope with no new
  inference. Record a distinct scoped authorization; do not invent credit
  coverage, free pricing, a monetary cap, or actual $0 charges. Default live
  adapters/CLI remain guarded; no held-out inference, deployment, general
  service activation, external messaging, or push is authorized.
- D26 (agent, Oct 21): Preserve the terminal failed F10 import as the single
  consumed attempt. Do not reset state or silently replace its registry/image
  identity. Add read-only public Python image discovery to make a possible
  existing-image recovery concrete before changing the runtime contract. The
  discovery makes no resource mutation and does not authorize another import.
- D27 (agent, Oct 21, continuing the user's supplied discovery result): Recover
  the original session using only the discovered `python:3.12-slim` immutable UUID
  `4fa16c8f-62a9-35a4-a4ea-07b7e8cd44ae`. Freeze the inventory and failed-import
  response hashes in a separate recovery record; preserve the original identity,
  failed receipt, and consumed import count. Keep D25's remaining three probes,
  twelve verifier operations, and zero new inference. This changes the image
  source to an existing public reference, not a second import or a claim that it
  matches the failed OCI digest. No general image selection, new billing
  approval, deployment, or extra resource operation is introduced.
- D28 (agent, Oct 21, recording the user's completed run): Preserve F12 as a
  separate live Sandbox re-verification of the unchanged F6 agent proposal.
  Publish a sanitized supplemental evidence bundle with original and presented
  hashes; retain the historical Nemotron/local Docker comparison unchanged.
  D25's one-import/three-probe/twelve-verifier allowance is consumed. No further
  runtime operation or inference is needed for this result; billing, formal
  track qualification, held-out evaluation, and free live-agent judge access
  remain separate unresolved matters.
- D29 (user, Oct 21): Explicitly authorized committing and pushing the completed
  saved Sandbox verification work and preceding local commits to `origin/main`.
  This authorizes Git delivery, not additional cloud execution or inference.
  The current workspace still mounts `.git` read-only, rejects elevated shell
  execution, and cannot resolve `github.com`. Prepare an isolated writable local
  checkout and portable commit bundle without modifying the protected metadata;
  do not claim a successful push without a remote result.
- D30 (user, Oct 21): Selected the recommended hosted fixed-case judge demo and
  requested all foreseeable questions together. Prepare a portable isolated
  controller/worker using the existing repair engine; routine implementation
  choices use the proposed defaults in `docs/JUDGE_HOSTING_PLAN.md`. Hosting,
  fresh inference/Sandbox allowances, funding coverage, and deployment activation
  still need the answers being collected. The completed F6 scope is not reused.
- D31 (user, Oct 22): Answered the consolidated questions: use this VPS, the
  existing Nebius key/project, private shared judge access, and twenty total
  attempts with one worker. Approves eight model calls/seventeen disposable
  operations per attempt plus one global startup capability operation, with
  four attempts reserved for the once-only held-out comparison after code
  freeze. User reports $30.98 Token Factory credit and says "proceed, ill check
  the usages myself" while keeping granted credits as the official funding
  intent. This is bounded permission, not confirmed Sandbox coverage, an invoice,
  or an enforceable dollar cap. No new image imports. Owner records the video;
  repository publication waits for final review. The same VPS may host isolated
  DocDrift units on 127.0.0.1:8765 without touching NewsBias or its forbidden ports.
  Existing commit/push permission persists; provide environment/terminal steps
  where managed restrictions prevent direct work. Partner services remain unused.
- D32 (user report, Oct 22): Normal-terminal Tailscale diagnostics show the VPS
  connected and no existing Serve/Funnel configuration. User requests all setup
  instructions together and does not know the full `.ts.net` name. Read it from
  local status JSON, retain port 8443 for the isolated password-protected route,
  and provide the ordered setup/activation/acceptance/persistence/evaluation steps.
  These diagnostics do not establish a working public route or change D31's quota.
- D33 (user, Oct 22): The manual deployment checklist is too much; the agent
  should execute it. Rechecks confirm this executor cannot connect to systemd
  or tailscaled and command DNS fails. Verified the installed CLI's resume,
  no-daemon, host-access sandbox mode, and on-request approval options; provide
  one normal-terminal relaunch command. Existing deployment permission and
  limits persist. No attempt to bypass the current managed policy is authorized.
- D34 (user report, Oct 22): The normal-terminal resume command reports the
  conversation is open in another app. No stale lock or extra host process has
  been established. Use the supported `codex fork` command to create a new chat
  retaining recorded history, then continue deployment with the existing limits.
  Do not delete lock files, kill daemons, or treat the lock error as lost work.
- D35 (user, Oct 22; agent execution): User requested hosted deployment after
  granting host access. Verified DNS/Git/systemd/Tailscale, installed the two
  isolated units, and completed the authorized startup capability, one fresh
  acceptance repair, and four once-only held-out jobs. Both strategies verified
  2/2 held-out cases. Five attempts are consumed and fifteen remain. Preserve
  the frozen results, quota, and old F6 state. Public HTTPS waits on Tailscale's
  owner account enablement; do not claim it from local success. Existing credit-
  only intent, unverified billing, private repository, and NewsBias exclusions
  remain unchanged.

## Session log

- 2026-10-14: Milestone 1 local slice, snapshots, offline Nebius contracts,
  fixtures, challenge, wheel packaging committed; 423 tests pass. Added
  `AGENTS.md`/`CLAUDE.md` and this checklist. Next: offline baseline harness;
  wait for Builder approval.
- 2026-10-14 (later): Built offline model repair (one-shot + agent), Token
  Factory client, `repair`/`evaluate` CLI, feedback-log template, submission
  draft. 444 tests pass. Local Docker: execution-only baseline 3/4 drift
  detected, 0/3 false reports, 4/4 abstentions; synthetic agent replay verified
  end-to-end. No live inference. Next: first live call once credits confirmed.
- 2026-10-14 (later): Replaced the exact known-repair AST requirement with a
  data-flow check so equivalent model rewrites verify; challenge still rejects
  16/16; real Docker demo still `behavior_verified`. 452 tests pass.
- 2026-10-14 (later): $25 Token Factory fallback ruled out (needs $25 own spend first).
  Builder approval is the single gate. Next offline work: wire Sandbox adapter into
  repair/evaluate; text-protocol fallback if `tools` is unsupported.
- 2026-10-14 (later): $1 Token Factory trial key received. Listed models, confirmed
  tool calling, and ran the first live agent repair: renamed_method `behavior_verified`
  in 5 calls / ~7k tokens. Text fallback no longer needed. Next: live development-split
  evaluation (one_shot vs agent), then Sandbox wiring.
- 2026-10-14 (later): Live dev evaluation: every strategy detected 2/2, one_shot and agent
  verified 2/2, 0 false reports, 4/4 abstentions; ~14k tokens. Found that fixture READMEs
  state the fix, so one_shot vs agent is not separated (F4). Next: user decision on fixture prose.
- 2026-10-14 (later): Rewrote broken-fixture README prose to stop stating the fix; re-froze
  manifests/index. Live dev rerun unchanged (one_shot and agent 2/2): healthy neighbors still
  show the current API (F5). Held-out not run yet.
- 2026-10-14 (reconcile, max effort): Reviewed this session's low-effort work. Fixed: the
  data-flow verifier accepted 11 constructed bypasses (now a must-flow check; all 9 saved
  live repairs still pass); stale exact-AST wording in engine/challenge notes and docs;
  the "$25 route dead" entry (user had corrected it); "no card" stated as a user fact;
  Sandbox recorded as blocked on Builder although never checked. Added Decisions D1-D9 and
  the commit-identity note in `AGENTS.md`. 468 tests pass.
- 2026-10-15: Took over at pushed commit 5403817; recorded user-reported approximately $30
  Token Factory credits (D10). Added portable HTML reviews to evidence ZIPs and
  `docdrift review <run-id>`; rendered a saved live Nemotron repair without rescoring.
  Hardened failed exports and incomplete-run downloads; corrected stale no-live-repair
  prose. 488 tests pass, 16/16 constructed bad patches rejected, offline wheel install
  passes, real Docker demo `behavior_verified` (12 operations). No new inference or
  live Sandbox calls. Next: Sandbox `whoami` once user approval/project ID arrive;
  D8/D9 still proposed. Commit locally; no standing push permission inferred.
- 2026-10-15 (access update): Saved the user-supplied Nebius project ID and recorded
  the submitted Sandbox application; awaiting provider response and user approval
  before any live check. No provider calls. 488 tests pass.
- 2026-10-15 (development fixture): Implemented approved D9 in a separately frozen
  two-case inventory, preserving all 41 original evaluation artifacts. Manual
  Docker verification passed 3 target and 3 healthy cases (12 operations), with no
  replacement-API hint in the original traceback. Added HTML evaluation comparison,
  saved-report rendering, inventory hashes, failed-proposal records, and a free
  manual local judge quickstart. 526 tests and offline wheel install pass.
  Next: one bounded live supplemental comparison;
  Sandbox access and D8 remain pending.
- 2026-10-15 (supplemental comparison): One live run after freeze commit 7faa9e8:
  agent 1/1 behavior verified after reading source; one_shot 0/1 (static rejection).
  No false drift reports on the healthy case; 6 model calls / 8,781 tokens / 15 local Docker
  snippet operations. Recorded F6 and separate comparison HTML; all original 41
  evaluation artifacts unchanged, no held-out model or Sandbox calls. 526 tests
  and wheel check passed before inference; code unchanged since. Next: provider
  Sandbox approval, D8 decision, and free live-agent judge access.
- 2026-10-15 (offline Sandbox and integrity): Connected `repair`/`evaluate` to a
  persistent HTTP-mock Sandbox bridge, journaled model probes and uploads, and
  tested accepted-ID/timeout recovery across final target and healthy checks.
  Synthetic rows stay unscored with no verified examples or real compute counts.
  Added bounded `verify-evidence` with adversarial ZIP tests and explicit
  integrity-only claims. 644 tests pass; installed wheel exercises synthetic
  repair plus integrity checks with sockets/subprocesses blocked; real Docker
  demo still behavior_verified (12 operations). Both frozen inventories unchanged.
  No live Sandbox calls or inference used. Next: provider access approval, then
  approved live capability checks/activation; D8 and free live judging remain open.
- 2026-10-15 (push handoff): User authorized pushing the five accumulated local
  commits plus this handoff update to origin/main. Implementation validation is
  unchanged: 644 tests, installed-wheel checks, and the real Docker demo passed.
  Next: await Sandbox access; no live provider work authorized by this push.
- 2026-10-15 (usage-limit handoff): Added an explicit resume plan, exact real-run
  artifact/proposal paths, current validation and access constraints, and demo
  acceptance criteria. Next agent should package saved F6 evidence, then prepare
  submission/video material. 644 tests rechecked and pass. No code changes,
  provider calls, or new model evaluation.
- 2026-10-16: Packaged the saved real F6 comparison, both proposals, successful
  repair review, and sanitized evidence ZIP with deterministic rebuild/provenance;
  linked README/quickstart, reconciled submission F4/F5/F6 results, and wrote the
  2:45 video script. All 39 ZIP members and 28 local HTML links checked; repeat
  builds match; all 50 original saved files and both inventories preserved.
  644 tests pass. No new inference, snippet execution, provider call, or push.
  Next: approved Sandbox access check/coverage, real cloud verification, D8,
  free live-agent judging route, and video recording.
- 2026-10-16 (access check): User approved one read-only Sandbox `whoami`; it
  succeeded with all six permission booleans true in 0.168 seconds (F7). Saved
  a filtered mode-600 access record; updated current status and authorization
  scope. No resources created, snippet execution, or inference. 644 tests pass.
  Next: Sandbox credit coverage and approved live capability checks/activation,
  then D8, free live-agent judging access, and video recording.
- 2026-10-16 (Sandbox preparation): Prepared the saved F6 source/proposal into
  a frozen twelve-operation plan and dedicated bounded live runner with private
  import, three fixed capability probes, durable receipts, restart recovery,
  and explicit factual coverage gating. Added documented signal/UTF-8 parsing
  compatibility and separated historical proposal usage from zero new inference.
  705 tests pass, including installed-wheel checks and synthetic full lifecycle;
  the published 16-file F6 bundle still rebuilds byte-for-byte. No live Sandbox
  API call, model evaluation, resource creation, deployment, or push. Next:
  answer the pending coverage question, then run the prepared Sandbox step;
  D8 and free live-agent judging access remain unresolved.
- 2026-10-21: Recorded user-confirmed Builder access and availability of optional
  service credentials (unused, not saved). Revalidated the offline F6 plan;
  fixed cancellation-before-image-assignment recovery and retained known
  operation/attempt UUIDs after acceptance-persistence failures, including when
  the error report cannot be written. Added fourteen synthetic regression cases;
  719 tests pass. No authenticated Sandbox request, inference, resource creation,
  deployment, or push. Next: actual Sandbox execution/import/storage coverage
  confirmation, then the prepared bounded live verification; D8 and funded free
  live-agent judging access remain open.
- 2026-10-21 (billing clarification): Recorded the user's exact Builder credit
  offer and uncertainty about Sandbox beta billing. Researched public primary
  sources: legacy ConTree early access was explicitly free; current Token Factory
  beta coverage remains unverified. Saved source links and an unsent provider
  question in `docs/SANDBOX_VERIFICATION.md`. Documentation-only update; the
  preceding full code validation remains 719 passing tests. No authenticated
  Sandbox request, inference, resource creation, coverage record, external
  message, deployment, or push. Next: provider confirmation of current terms;
  local development and saved-evidence review remain available meanwhile.
- 2026-10-21 (scoped activation): User explicitly authorized the bounded F6 run
  despite unresolved billing (D25). Added a distinct strictly bounded permission
  schema and truthful unverified-billing evidence; saved the actual mode-600
  authorization separately from credit coverage. 751 tests pass. Attempted
  access read failed locally; DNS returned `EAI_AGAIN`, and workspace policy
  rejected DNS-only sandbox escalation because `sandbox_approval=false`.
  No matching connector was found. No successful provider response, resource
  submission, live state, inference, external message, deployment, or push.
  Next: execute the prepared command in a network-enabled environment under the
  existing permission; no repeat billing confirmation is needed for this scope.
- 2026-10-21 (import diagnosis): User ran the fixed verifier in their normal
  terminal; Nebius accepted import `01a15f6f-2d46-71c6-a692-ede648b18661`, then
  reported terminal FAILED with HTTP 404 from the registry pull (F10). No result
  image, runtime probe, verifier operation, or new inference. Preserved actual
  receipts; fixed completed-failure resume to stop without provider requests and
  added a read-only public Python image inventory command. 761 tests pass. Next: run `images`
  in the same terminal, then inspect possible existing-image recovery; no
  automatic reimport, fallback, state reset, or new provider call was performed.
- 2026-10-21 (existing-image recovery): User supplied the real read-only 15-image
  inventory, including Python 3.12 slim UUID `4fa16c8f-62a9-35a4-a4ea-07b7e8cd44ae`
  (F11). Implemented and prepared exact-record existing-image recovery that
  retains the failed import/session and remaining D25 operation scope; saved
  pre-recovery report/session copies. Actual record validation is offline, and
  lifecycle/resume tests use synthetic responses. All 824 tests pass. No
  additional provider request, image inspection, resource submission, session reset, inference, deployment,
  external message, or push during implementation. Next: user runs the prepared
  command with `--reuse-record` from the network-enabled normal terminal.
- 2026-10-21 (live Sandbox verification recorded): User completed F12 using the
  existing image: original failures reproduced, three repaired target cases and
  three healthy regressions passed, protected hashes preserved, zero new
  inference. Audited all 16 durable IDs (one failed import, three probes, twelve
  verifier operations); completed resume added no new recorded submissions.
  Published a separate sanitized deterministic cloud-verification bundle at
  `docs/demo/f6-sandbox/`, preserving exact proposal/source linkage and historical
  Docker comparison. Updated README, submission/video/quickstart, runtime notes,
  feedback log, and handoff. All 824 tests pass; 39 public archive payload members
  verify; 73 checked local links resolve. Offline audit/packaging made no new
  provider request, inference, deployment, external message, or push. Commit
  attempted but blocked: this workspace mounts `.git` read-only, so Git cannot
  create `index.lock`; validated changes remain uncommitted in the working tree. Next:
  record the video from saved evidence and resolve free live-agent judge access
  through Dec 15; D8 and billing clarification remain open.
- 2026-10-21 (Git delivery authorized): User explicitly permitted commit and push
  and then said to proceed. All 824 tests and the completed evidence validation
  remain applicable; implementation and evidence bytes are unchanged. Staging
  in the original checkout still failed on read-only `.git/index.lock`; the
  approval system rejected elevated execution, and normal GitHub lookup failed
  DNS resolution. Prepared the authorized commit in the isolated writable
  checkout `/tmp/docdrift-delivery-ctctogzg/repo`, preserving the nine preceding
  commits; the original Git metadata remains unchanged. A portable full-history
  bundle and delivery receipt are saved under `.docdrift/access/` as
  `docdrift-main.bundle` and `git-delivery-2026-10-21.json`. The explicit push
  attempt failed on GitHub DNS resolution, so no successful push is claimed.
  GitHub was found as an available but unconnected plugin; a connection was
  suggested, not assumed. No new cloud execution or inference. Next: push the
  prepared isolated checkout from the network-enabled normal terminal.
- 2026-10-21 (hosted judge route selected): User reports the prepared push done
  and selected a hosted fixed-case demo. The isolated delivery checkout's local
  `main` now matches its `origin/main`; the protected original checkout remains
  at its old metadata with matching saved worktree bytes. Inspected engine and
  adapter boundaries, prepared `docs/JUDGE_HOSTING_PLAN.md`, and collected the
  remaining hosting/funding/access/allowance decisions in one questionnaire.
  This is planning documentation; no new inference, provider execution,
  deployment, or held-out evaluation. Existing 824-test validation is unchanged.
- 2026-10-22 (private judge service): Recorded D31's VPS/existing-key/private-access
  choices, $30.98 Token Factory balance report, and separate twenty-attempt scope.
  Built fixed-fixture live bridge, durable queue/quotas, bounded model accounting,
  single-worker crash pause, private HTTP interface, saved-evidence fallback,
  sanitized review/downloads, once-only held-out queue/report, setup script, and
  isolated resource-limited user units. Prepared private authorization/state
  offline with zero attempts used. All 1,014 tests pass; cached offline package
  build/installed smoke and unit/JS checks pass. No new provider/model/guest
  request, service startup, route change, partner service, or outside-repo secret
  was used or created. Tailscale hostname/8443 availability remain unknown from
  this sandbox; normal-terminal diagnostics are pending. Added official workspace
  permission and VPS/GitHub steps. Commit prepared in the isolated delivery
  checkout; remote delivery still needs working network/host permissions. Next:
  establish HTTPS route, activate the one capability probe, accept one live judge
  run, then freeze and run the four reserved held-out jobs once; record video.
- 2026-10-22 (deployment instructions): Recorded the owner's connected Tailscale
  and empty Serve/Funnel diagnostics (D32); replaced the hostname placeholder
  with validated automatic discovery and consolidated startup readiness, Funnel
  enablement, private login, acceptance, and safe handoff instructions. Source
  implementation unchanged; actual activation and public acceptance remain pending.
- 2026-10-22 (agent execution access): Owner requested agent-operated deployment
  instead of manual steps (D33). Confirmed local service/network restrictions;
  documented one supported resume command requesting host access with on-request
  approvals. No source change or new live request; existing 1,014-test pass holds.
  Next: resume with effective host access, then perform and accept deployment.
- 2026-10-22 (conversation ownership): Recorded the reported resume ownership
  error (D34). Verified installed `codex fork` flags and official transcript
  preservation behavior; corrected the handoff to a separate chat with history.
  Documentation only; 1,014-test validation unchanged and no new live request.
- 2026-10-22 (hosted activation): Host access restored. Fixed systemd 249 ignoring
  quoted EnvironmentFile paths, reproduced the warning in a regression check,
  and passed all 1,015 tests. Installed/enabled the isolated web/worker units;
  startup capability and one fresh local HTTP repair passed, then both strategies
  verified 2/2 once-only held-out cases. Exported four sanitized reviews/ZIPs.
  Five attempts used, fifteen remain; 16 model calls / 22,241 tokens and 58 total
  Sandbox operations, no imports. Service/fix pushed to private origin/main.
  Public HTTPS is pending the owner's one-time Funnel account enablement. Verified
  all 211 source/artifact files and synchronized the original Git metadata to the
  pushed prepared tree without changing worktree bytes or private state.

## Evidence detail (historical: written before the first live call on October 14)

Continue the preserved architecture; the clone was
initially empty, with no commits and no applicable `AGENTS.md`.

The user confirmed a **$0 personal spending limit** on October 14: use only
granted free credits, with no personal investment. Advertised credits are not
an allocated budget. Live provider operations remain disabled until the actual
grant, service coverage, expiry, and protection against personal charges are
confirmed. Preserve NewsBias's resources and any shared credit pool.
The user reports that the Builder Program application is under review. No grant
amount, credited balance, expiration, or Sandbox permission has been confirmed.

### First unfinished milestone: 0, access and contract

The owned renamed-method fixture and independent contract are now frozen in
`fixtures/renamed_method/`. The target package, original failure, healthy neighbor,
three varied inputs, expected outputs, full-operation AST hashes, known repair,
and provenance manifest are present. Checks and profiles live outside the target.

Live access remains unconfirmed. No Nemotron inference, Sandbox probe, billing
check, credit assumption, external message, or paid provisioning occurred.
Focused builder time and a DocDrift allocation from granted promotional credits
remain unconfirmed. The personal spending cap is $0. The first remaining gate
is confirmed credit coverage and protection against personal charges, followed by an actual
Nemotron tool response and Sandbox contract/offline/artifact/recovery checks.
GitHub's existing connection was left intact; no login or plugin setup was needed.

### Milestone 1: local plumbing complete; remote acceptance outstanding

Implemented and exercised:

- Python 3.12 package/CLI with a locked development environment.
- Bounded local Git SHA resolution and safe snapshots with hashes and licenses.
- Markdown source spans, stable IDs, and unsupported-example inventory.
- Frozen declarative profiles, exact JSON checks, and operation/data-flow checks.
- One-fence documentation patch policy with protected input hashes.
- Fresh offline Docker operations, immutable images, bounded logs, and time limits.
- SQLite phases and accepted IDs persisted before startup; recovery reconciles
  known operations and does not resubmit completed phases.
- Fresh original failure reproduction, repaired checks, healthy regressions,
  JSON/diff/log/source/check evidence and a SHA-256 ZIP manifest.

An actual local demo reproduced the `AttributeError`, passed all three repaired
cases and all three healthy cases, and preserved protected hashes. A separate
actual interruption test resumed the same accepted, not-yet-started container
and completed the run with 12 unique snippet operations. Inference calls and
paid calls were zero. Docker Python-version preflight probes are separate from
the 12 snippet operations.

Validation: 145 automated invariant and adapter-contract tests pass. A final
actual local run also completed successfully after the recovery and export fixes.
The tests use contract doubles for orchestration; the local runtime evidence comes
from Docker operations. The initial Docker logging startup failure was retained
as an incomplete finding and its unstarted container was removed.

Public pinned GitHub inspection now resolves a branch/tag once, validates the
complete recursive tree, and checks every archive blob against the pinned tree
before extraction. A real unauthenticated read of the plan's python-slugify
commit inventoried eight fences (three candidates, five unsupported). No upstream
example was executed or assigned a behavior-verification claim.

The REST-backed `NebiusSandboxAdapter` now has offline contract coverage for
preflight, frozen uploads, submission, observation, cancellation, and artifacts.
All response fixtures are synthetic documented-shape examples, not live recordings.
Durable SQLite receipts precede submission; returned IDs are committed before
callbacks, ambiguous outcomes prohibit automatic retry, and a recovered ID is
observed without resubmitting. Tests enforce live mutation blocking, fixed guest
network denial, separate service/process status, bounded logs/artifacts, immutable
image identity, and safe result metadata. Raw resource `cost` fields are never
interpreted as dollars. The CLI's `sandbox-contract-demo` runs offline without
credentials, inference, or code execution and labels that limitation explicitly.

Current validation: **423 automated tests pass**, covering the original local
slice, public snapshots, synthetic REST parsing, durable submission receipts,
frozen evaluation artifacts, static challenges, distribution checks, the manual
workflow's context and spending gates, and independent checks that simulation
cannot enable live mutations. The locked development environment also installs
from its populated local cache. The CLI
contract demo completed with all checks passing and zero network calls, code
executions, inference calls, or paid calls. The live public GitHub inspection is
a separate read-only check, not a Nebius or behavioral verification result.

The current implementation is now committed and pushed to `Iljaadam/DocDrift`.
The first four commits separate the architecture, local manual slice, pinned
public snapshots, and offline Nebius contracts. Subsequent work is likewise
grouped by evaluation fixtures, static challenges, and distribution checks.

Additional local work now includes a frozen fourteen-case inventory, two broken
cases reserved for fresh held-out model runs, and a static rejection challenge.
All sixteen deliberately constructed bad proposals reject; the known manual
control is `accepted_static`, never behavior verified by the challenge. The
same protected-input hash gate is now used by the execution engine.

Fresh Docker smoke runs verified the supplied known repairs for all four owned
broken fixtures. They preserved the three healthy neighbors across three inputs
each. The return-shape fixture reproduced an original output-check failure with
process exit zero. These are curator-owned manual plumbing checks with no model
calls or scored evaluation. Their evidence remains in the local run store.

The CLI wheel now includes nine immutable fixture files and its MIT license.
An actual offline wheel installation into a fresh environment outside the
checkout passed help, fixture inventory, synthetic Sandbox contracts, and the
static challenge. A local distribution checker validates fixture/source/license
hashes and wheel metadata. CI is manual-only, with its runner skipped by default
until included Actions quota and protection against personal charges are
confirmed. GitHub initially rejected the workflow definition before scheduling
any jobs: `runner.temp` is unavailable in a job-level environment. The corrected
literal cache path passes actionlint 1.7.12. No hosted runner started, and no
manual workflow was dispatched.

Milestone 1 is **not complete under the plan**: remote preparation,
approved dependency acquisition, Nebius original reproduction,
pristine remote verification, and remote operation reconciliation are outstanding.
The local source-tree fixture needs no installation or dependency downloads.

### Next authorized implementation work

Keep work local while access and budget remain unresolved. Public GitHub reads
and the offline REST/receipt contracts are now implemented. Once the grant and
protection against personal charges are confirmed, the next provider step is
an explicitly scoped access check, followed by the original milestone-0 live
model/Sandbox capability probes. Live Sandbox mutations have no enable switch;
they remain disabled until the required access and budget controls are designed
and validated. Immutable image import/setup, durable upload recovery, real network
denial, provider cancellation timing, and billed units remain live-contract gaps.
Only after that gate passes should the actual Nemotron loop be exercised.

Milestones 2–5 remain unfinished. No model repair, evaluation results, review UI,
public release, hosting, judge-access route, or submission is claimed. The current
static defenses overlap milestone 3 but do not satisfy the complete challenge
or substitute for an actual model repair. NewsBias remains the primary project
and was not modified.
