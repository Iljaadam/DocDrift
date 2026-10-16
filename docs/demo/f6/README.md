# F6: saved real demo evidence

Open [index.html](index.html) directly from a fresh clone. No credentials,
inference, Docker, server, or network connection is needed to browse it.

This is one exploratory comparison on an additional **DocDrift-owned development
fixture**, added after the earlier development results. It is not held out and
does not establish general model superiority. Generation used live NVIDIA
Nemotron (`nvidia/nemotron-3-super-120b-a12b`) through Nebius Token Factory;
execution used **local Docker**, not Nebius Sandboxes.

The agent repaired 1/1 broken example. The one-shot proposal repaired 0/1: its
`OccurrenceIndex.build(words)` rewrite removed the constructor and was statically
rejected. Both model strategies made zero false drift reports on the unrelated
healthy example. Totals: 6 model calls, 8,781 tokens, 15 local snippet operations.
The accepted repair was `OccurrenceIndex().positions(words, include_empty=True)`.
Frozen verification checks cover three target inputs and three healthy regression
inputs; they do not prove behavior for every input.

## Files and provenance

- [comparison.html](comparison.html), [JSON](comparison.json), [Markdown](comparison.md): the saved source-only comparison.
- [agent/review.html](agent/review.html): original error, patch, recorded checks, usage, and logs.
- [agent/report.json](agent/report.json), [repair.json](agent/repair.json), [repair.patch](agent/repair.patch): successful agent repair.
- [one-shot proposal](proposals/one-shot.json), [agent proposal](proposals/agent.json): original model transcripts, byte-for-byte. The latter is structurally identical to `agent/repair.json`; original formatting differs.
- [agent/evidence.zip](agent/evidence.zip): all 39 original manifested members, with the presentation changes below and a rebuilt manifest. Source, checks, snippets and individual log files are stored here to avoid duplicating the fixture tree outside the ZIP.
- [provenance.json](provenance.json): original input/member SHA-256 hashes, exact JSON pointers for every redaction, original path-value hashes, transformations, published hashes, and offline integrity results.

The original gitignored evidence was preserved. The original ZIP SHA-256 is
`3edb8afb8716de4be73d1472b2a65c04ef990ce745f70c10869fabaac802e346`.
The published ZIP has a different hash because these are sanitized presentation
copies. Only two distinct private absolute path values were redacted:

- `report.json` `/provenance/origin` and `ledger.json` `/metadata/provenance/origin`
  now say `REDACTED_LOCAL_SOURCE_ORIGIN`.
- `ledger.json` `/events/0/payload/run_directory` and `/phases/frozen/run_directory`
  now say `REDACTED_LOCAL_RUN_DIRECTORY`.

The agent HTML was regenerated from those copies with a presentation notice;
comparison HTML was regenerated with that notice and a working relative run link.
The archive's SHA-256 manifest was rebuilt. Every other archived payload is
byte-for-byte unchanged. Common credential patterns were checked in all text
inputs and outputs, including ZIP members; no matches were found. No key file
was loaded. Runtime `/work/example.py` paths and public model identifiers remain.
Unsigned manifests establish internal integrity, not authenticity or signed
execution attestation. Packaging is not a fresh behavior verification.

## Offline checks and rebuilding

From the repository root, with the project environment installed:

```bash
.venv/bin/docdrift verify-evidence docs/demo/f6/agent/evidence.zip
```

Rebuilding requires the exact original `.docdrift/` inputs listed in
`provenance.json`; they are not included in a fresh clone:

```bash
.venv/bin/python scripts/package_demo.py
.venv/bin/python scripts/package_demo.py --output /tmp/docdrift-f6-rebuild
```

The script checks frozen input hashes, verifies the original ZIP and matching
loose evidence, scans text, replaces only the disclosed paths, renders saved
reports, creates a deterministic ZIP, and verifies its 39 manifested members.
It performs no inference, example execution, Docker, network, or Sandbox calls.
Output hashes are recorded in `provenance.json` (except that file's own hash).
