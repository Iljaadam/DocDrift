# Constructed static verification challenge

`docdrift.challenge.run_challenge` checks deliberately constructed proposals
against the owned renamed-method fixture. It reads frozen bytes and parses
Markdown/Python ASTs. It never imports the target package, executes a proposal,
starts Docker, or calls Nebius or a model.

The report is labeled `static_policy_challenge`. Every case records its expected
rejection, actual static verdict, reason, gate, and evidence hashes. The known
manual `tally` → `count` control must pass the patch boundary and frozen operation
AST. Its verdict is `accepted_static`, with `behavior_verified: false`.

The constructed cases cover:

- Deleting the entire target fence or relabeling it as text.
- Swallowing an exception, replacing the API operation with a fixed result, or
  keeping a dummy API call while replacing the result used by the output.
- Inserting a skip marker, NUL, Markdown fence, empty replacement, or non-text
  replacement.
- Editing application source, the package manifest, independent checks, the
  frozen profile, or the fixture provenance manifest.
- Adding an unauthorized test file. This owned target currently has no tests
  directory; the report states that limitation. Unit tests additionally prove
  that the same hash gate rejects changes to an existing protected test file
  using an explicitly synthetic byte sentinel.

The dummy-call case illustrates the distinction between coarse operation
presence and data flow. The ordinary patch policy accepts its retained calls,
and the named `WordCounter.count` operation remains present. The
`operation_data_flow` gate rejects it because the printed result is reassigned
from a value that no longer carries the call's result. (Before October 14 this
gate required an exact match with the known repair's AST; that rejected
equivalent model rewrites and was relaxed.)

The reusable `validate_protected_changes` function compares full relative paths,
the exact file inventory, all protected hashes, and the selected Markdown hash.
Its `approved_target_hash` must come from bytes returned by `apply_replacement`;
an arbitrary proposed document cannot nominate its own approved hash. This lets
the engine use its existing exact-span policy and the same hash boundary without
giving another file with the same basename the target's exemption.

```python
from pathlib import Path
from docdrift.challenge import run_challenge

report = run_challenge(
    Path("fixtures/renamed_method"),
    Path("artifacts/static-challenge.json"),
)
assert report["all_expectations_met"]
```

Output is optional and must remain outside the frozen fixture. Reports are
deterministic and contain hashes rather than simulated execution logs or
invented observed outputs. The input manifest must match before the runner
evaluates a case; all proposals remain in memory.

Generated `__pycache__` directories and `.pyc`/`.pyo` files are excluded from the
source inventory, matching the repository's Python cache policy. The report
records that exclusion rule. The runner never loads or executes these caches;
their presence cannot alter a frozen source, profile, check, or known repair.
Other unlisted files still invalidate the fixture inventory.

This challenge supplies static rejection evidence only. It establishes no
execution pass, behavioral verification, healthy-example rerun, model-generated
repair, or provider qualification. It does not complete milestone 3 of the
architecture plan. The previously recorded local Docker manual run is separate
runtime evidence; this runner does not repeat or replace it.
