# DocDrift implementation status

Deadline: **October 30, 2026, 17:00 UTC**. Entry point for agents: `AGENTS.md`.

## Checklist

Token Factory: $1 trial key in `~/.config/docdrift/nebius.env`; live inference approved (D5).
Sandboxes: permission never checked. The Sandbox API is on the same Token Factory host and
takes a bearer key plus a `Project` header, so a read-only `GET whoami` with this key and the
user's project ID would show it (needs user OK and the ID). All execution so far is local Docker.

**Access (milestone 0)**
- [x] Owned renamed-method fixture and independent contract frozen
- [ ] Builder Program approval (pending since before Oct 14)
- [x] Token Factory $1 trial key received; live inference approved by user (D5)
- [ ] $25 Token Factory credits via the hackathon form: status unknown. (Correction: the
  "promo code only after $25 own spend" restriction applies to Nebius cloud compute, not
  Token Factory, per user on Oct 14. An earlier entry here wrongly called this route dead.)
- [x] Live Nemotron tool-call response recorded (`docs/FEEDBACK_LOG.md` F2)
- [ ] Sandbox permission (read-only `whoami`, needs user OK); offline execution, image reuse, result parsing, cancellation, artifact download checked live

**Manual vertical slice (milestone 1)**
- [x] Local Docker slice: original failure, repaired checks, healthy neighbors, export, resume
- [x] Pinned public GitHub snapshots; offline Nebius REST/receipt contracts
- [ ] Same slice on Nebius Sandbox: remote prep, original reproduction, pristine re-verification, operation reconciliation

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
- [ ] Wire the Nebius Sandbox adapter into `repair`/`evaluate` (local Docker only today)
- [x] Live development-split run: one_shot 2/2, agent 2/2 verified (F4)
- [x] Fixture prose made neutral and re-frozen (F5); dev rerun still 2/2 for both strategies
- [ ] Decide D9: add a source-only case (no current-API neighbor) so agent vs one_shot separates (F5)
- [ ] Scored held-out run, once (D8)
- [ ] HTML review report from real runs (unblocked: the plan's gate, a real model repair
  passing independent checks, was met by F3)
- [x] CLI wheel with fixtures, offline install check

**Submission (milestone 5)**
- [ ] Free judge-access route through Dec 15 (CLI + credits, or hosted fixed-case endpoint — not on NewsBias infra)
- [ ] Video under 3 minutes (script in `ARCHITECTURE_PLAN.md` → Competition and demonstration)
- [ ] Nebius/NVIDIA feedback log (template ready: `docs/FEEDBACK_LOG.md`)
- [ ] Devpost write-up (draft: `docs/SUBMISSION_DRAFT.md`, numbers TBD) and submission

**Decision dates**
- Oct 22: still no Sandbox access → user decides: submit with real Nemotron on Token Factory
  and local Docker execution, clearly labelled (Coding eligibility uncertain), or stop.
- Sandbox access after ~Oct 26: swap only the final verification onto Sandboxes; keep the rest.
- Watch the $1 trial balance: evaluation runs cost tokens (first repair ~7k tokens).

**Next**, in order: (1) with user OK and project ID, read-only Sandbox `whoami`; (2) if permitted, wire the
Sandbox adapter into `repair`/`evaluate`, otherwise build the HTML review report first;
(3) settle D9 and add the case; (4) scored held-out run (D8).

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
  Sandbox calls are not approved yet.
- D6 (agent, Oct 14): Working model `nvidia/nemotron-3-super-120b-a12b`: tool calling
  verified (F2). The other Nemotron IDs are listed in F1.
- D7 (user, Oct 14): Broken-fixture README prose neutralised and re-frozen before any
  held-out model run (F4, F5).
- D8 (proposed by agent, awaiting user): run the held-out split once, after Sandbox wiring.
  If there is no Sandbox by Oct 22, run it on local Docker and label it so.
- D9 (proposed by agent, awaiting user): add a fixture whose fix needs the source (no
  current-API neighbour, no traceback hint), so the agent can beat one-shot.

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
