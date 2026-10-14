# Owned renamed-method fixture

This fixture is authored for DocDrift and licensed under the MIT license in
`repository/LICENSE`. It is a constructed API drift case, not an upstream bug.
Only `repository/` is the target snapshot. The profile, independent checks,
known manual repair, and this provenance note live outside that snapshot.

The first `python` fence in `repository/README.md` invokes
`WordCounter().tally(words)`, but the frozen package defines only `count`.
The second fence already uses `count` and produces a healthy summary.
The known repair changes just the target method name to `count`.

`profile.json` freezes Python 3.12 and a dependency-free source-tree import
recipe. An isolated operation receives the snapshot on its `PYTHONPATH`;
installation and dependency download are unnecessary for this fixture. The
package manifest is preserved as target provenance, rather than an install
instruction. Execution still belongs inside the execution adapter; controller
tests do not import or execute the target package.

The three frozen inputs cover an empty collection, repeated words, and exact
Unicode, case, empty-string, and whitespace preservation. The target oracle
is a word-to-count mapping. The healthy oracle independently checks distinct
and total counts. Controller-held `expected_json` values compare structured
stdout, rather than accepting a printed success claim. The trusted
`checks.py` additionally recomputes those expectations without importing the
target package, and requires the complete meaningful operation and data flow
through an AST template. Each profile example also freezes
`operation_ast_sha256`: SHA-256 of the UTF-8 encoded
`ast.dump(ast.parse(code), include_attributes=False)` for its accepted
operation. The target hash comes from `repair.py`; the healthy hash comes
from the original second fence. The engine can compare this declarative hash
without importing or executing `checks.py`. It preserves the complete
operation and data flow, while ignoring source locations and formatting.
`required_call` describes the expected API operation. These checks cover this
fixture and these inputs; they do not establish arbitrary semantic equivalence.

`manifest.json` records SHA-256 hashes of every fixture file except the
manifest itself. Freeze these artifacts before baseline execution or model
interaction. A changed hash requires curator review and a new frozen
fixture; it is not a candidate documentation repair. A run also resolves and
records its own target snapshot commit and file hashes.

Local contract tests inspect source text and ASTs, exercise the trusted
oracle, and verify the freeze manifest. They establish that the fixture is
ready for isolated execution. They are not evidence that a remote baseline,
Nemotron call, or repaired execution has occurred.
