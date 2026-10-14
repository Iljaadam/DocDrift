# Frozen evaluation inventory

This is a curator-owned inventory of the architecture plan's fourteen cases,
not an evaluation result. No target package was executed to create it, and no
model calls or paid execution occurred. `index.json` freezes case selection,
curator ground truth, and development versus held-out splits before evaluation.
The index's `reproduction_status: not_run` refers to results in the planned scored
evaluation. It is not a history of every local fixture smoke check. Curator-only
manual runs and their evidence are stored separately; they do not expose known
repairs to a model or replace the later model evaluation.

| Cases | Coverage and current status |
| --- | --- |
| Four owned broken examples | Renamed method, renamed imported symbol, changed keyword, changed return shape. All have three frozen varied inputs and manual repairs. |
| Three owned healthy examples | Word summary, joined text and length, ascending token order and first token. Each is a neighbor of a broken example. |
| Three owned unsupported examples | Secret/service dependency, IPython syntax, incomplete sketch. Static inventory only; none has an execution profile. |
| One owned setup failure | The declared offline PEP 517 build requires a missing file. The current profile loader rejects that setup recipe. No installation or setup failure was executed. |
| Three pinned public candidates | python-slugify quickstart, python-dotenv stream quickstart, python-dotenv IPython example. All remain `pending_reproduction`, with fence ordinals and environment contracts unresolved. |

The existing renamed-method fixture is referenced without modification. New
repositories live in their respective `repository/` directories. Profiles,
checks, known repairs, and classifier contracts live outside those patchable
repositories. The owned fixtures are MIT licensed; public candidate licenses
and package environments must be established from their pinned snapshots.

`renamed_import_broken` and `changed_return_shape_broken` are held out.
Agent development/challenge loops must select only `split = development`; model
prompts, diagnosis probes, or repair training must not consume held-out
snapshots, checks, or known repairs before their evaluation run. The curator
and static contract tests necessarily inspect the held-out artifacts to freeze
them, and curator-only manual validation may execute the declared contracts.
This is a split declaration, not evidence of a model evaluation.

The supported profiles use Python 3.12 and dependency-free source-tree imports.
Inputs cover empty collections, repeated tokens, and case/Unicode/whitespace
preservation. Declarative JSON expectations and complete AST hashes provide
limited, independent behavior and operation coverage. Trusted `checks.py`
files recompute those expectations without importing the target packages.

The changed-return-shape example documents a scalar count, while the frozen
API returns a dictionary. Its predicted original failure is an output-oracle
mismatch despite successful process execution. Static evidence and a mocked
observed-output test establish the contract; they do not claim that an actual
original process has exited zero. Isolated execution must reproduce that result.

The setup case contains a deliberately unsupported profile. It must receive a
setup/profile finding before execution, not a documentation-repair claim.
Its curator label describes the intended missing-prerequisite case; a real
`environment_setup_failure` observation still needs an isolated setup run.
Unsupported and setup-only cases have no known documentation repair.

`manifest.json` freezes every file under this directory except itself using
SHA-256. The index also records the existing renamed-method manifest's hash.
Changed artifacts require curator review and a new freeze, rather than a
candidate repair. Git commits and environment identities must additionally be
resolved and recorded by each future run. Never count pending, unsupported,
setup-only, skipped, or statically inspected examples as behavior verified.
