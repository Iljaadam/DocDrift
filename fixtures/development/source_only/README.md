# Owned source-inspection development fixture

This is a newly authored, curator-owned fixture, not an observed bug in a public
project. It is an additional development case outside the original frozen
fourteen-case inventory. It does not change either held-out case or its split.

The target documents an occurrence index with an obsolete method. The current
source provides the replacement and an option needed to preserve empty tokens.
The repository README contains no example using that current API, and its healthy
neighbor exercises a different class. The original missing-method name is not a
close spelling of the replacement, so Python's spelling suggestion is not an
intended repair cue. Isolated baseline execution must still establish the actual
failure and captured traceback.

The model receives the repository README and baseline finding, as in the existing
harness. The agent can additionally inspect the package source. Profiles,
acceptance checks, this curator note, the manual known repair, and provenance
remain outside the patchable repository and must not be included in model
prompts. “Source-inspection” describes where authoritative API evidence is
available; a one-shot model might still guess the repair. No agent advantage or
model outcome is claimed by constructing this case.

The Python 3.12 profile uses dependency-free source-tree imports. Three frozen
inputs cover empty collections, repeated tokens, and empty/case/Unicode/whitespace
preservation. The target maps exact tokens to every zero-based position. The
unrelated healthy example counts tokens and characters. The external oracle
recomputes expectations without importing or executing the target package.
Complete known-repair AST hashes are informational under DocDrift's current
verifier; acceptance also requires frozen JSON outputs, the declared API call,
and its result reaching printed output.

`provenance.json` records authorship and split intent. `manifest.json` freezes all
files in this fixture except itself with SHA-256. A future run must additionally
record its Git commit, image, original reproduction, repaired cases, and healthy
regressions. Static fixture tests and synthetic tool replays are not evidence of
a live Nemotron repair or Nebius Sandbox access.
