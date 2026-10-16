"""Package the saved F6 demo offline; never run a model, Docker, or a provider.

Run with ``.venv/bin/python scripts/package_demo.py``. The original gitignored
inputs are required to rebuild; a fresh clone can browse the committed output.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import tempfile
import zipfile
from pathlib import Path

from docdrift.evidence import verify_evidence
from docdrift.review import render_evaluation_review, render_review


ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "4fd82cb8be7a449e8815d5366665f4ac"
RUN = f".docdrift/runs/{RUN_ID}"
EVALUATION = ".docdrift/evaluations/source-only-live-1"
ONE_SHOT = ".docdrift/proposals/34303fa5d21f4213bccec9827b0e28cf.json"
AGENT = ".docdrift/proposals/d718ad233d6a4bf2b393b2e45d591522.json"
INPUT_HASHES = {
    EVALUATION + ".json": "85b9a4b781ed45a68da3a1dc861221c74850a057466d8eae03782c7b26eb5e6f",
    EVALUATION + ".md": "8b46b5da3b2519f0edfef49c213bcf748f4f449a53784d86209576250ffea9b6",
    EVALUATION + ".html": "93344ed1cc2edf1ec0a2bb12daf3827804e4e10663b3b7742634450778feed53",
    ONE_SHOT: "e3ccb688f7ce575f3b3c3ff19f3f59fe0ef78f3112740ef58786f3e71243dd05",
    AGENT: "bf2432df7af32780096e4591a6f331e3c0c5678203c1308dce3dbd026722e370",
    RUN + "/evidence.zip": "3edb8afb8716de4be73d1472b2a65c04ef990ce745f70c10869fabaac802e346",
}
NOTICE = (
    '<p class="qualification">Sanitized presentation copy of saved F6 evidence. '
    'Two private absolute paths were replaced in report/ledger copies; HTML and '
    'the unsigned ZIP manifest were rebuilt. Saved outcomes are unchanged. '
    'Hashes establish internal integrity, not signed execution attestation.</p>'
)
LOOSE_MEMBERS = {
    "review.html", "report.json", "repair.json", "repair.patch", "ledger.json",
    "commands.json", "manifest.json",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()


def scan(name: str, data: bytes, *, sanitized: bool) -> None:
    """Fail without exposing a matched value; inspect every text member."""
    text = data.decode("utf-8")
    credentials = re.compile(
        r"(?i)(?:sk-[a-z0-9_-]{12,}|Bearer\s+[a-z0-9._-]{12,}|"
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
        r"\b(?:api_key|access_token|secret_key)[\"']?\s*[:=]\s*[\"']?[a-z0-9_-]{12,}|"
        r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b|"
        r"\beyJ[a-z0-9_-]{8,}\.[a-z0-9_-]{8,}\.[a-z0-9_-]{8,}\b)"
    )
    if credentials.search(text):
        raise ValueError(f"Possible credential in {name}; matched value withheld")
    # The documented rebuild destination is an intentionally public example.
    path_text = text.replace("/tmp/docdrift-f6-rebuild", "")
    if sanitized and re.search(r"/(?:home|root|tmp)/[^\s\"<>\\]+", path_text):
        raise ValueError(f"Unredacted private path in {name}; matched value withheld")


def notice(html: str) -> bytes:
    return html.replace("<main>", "<main>" + NOTICE, 1).encode()


def write_files(root: Path, files: dict[str, bytes]) -> None:
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def make_zip(files: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            member = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            member.create_system = 3
            member.external_attr = 0o100644 << 16
            member.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(member, data, compresslevel=9)
    return stream.getvalue()


def package(output: Path) -> dict:
    inputs = {name: (ROOT / name).read_bytes() for name in INPUT_HASHES}
    if {name: digest(data) for name, data in inputs.items()} != INPUT_HASHES:
        raise ValueError("Saved F6 input hashes changed; refusing to publish different evidence")
    original_integrity = verify_evidence(ROOT / RUN / "evidence.zip")
    with zipfile.ZipFile(io.BytesIO(inputs[RUN + "/evidence.zip"])) as archive:
        original = {name: archive.read(name) for name in archive.namelist()}
    # Also check the saved loose evidence before reading presentation inputs.
    for name, data in original.items():
        if (ROOT / RUN / name).read_bytes() != data:
            raise ValueError(f"Original archive and saved loose member differ: {name}")
    for name, data in {**inputs, **original}.items():
        if not name.endswith(".zip"):
            scan(name, data, sanitized=False)

    report = json.loads(original["report.json"])
    ledger = json.loads(original["ledger.json"])
    source_origin = report["provenance"]["origin"]
    run_directory = ledger["phases"]["frozen"]["run_directory"]
    redactions = [
        {
            "replacement": "REDACTED_LOCAL_SOURCE_ORIGIN",
            "original_value_sha256": "9315cd9fce6f273ef6c5a0d911599745c93dc90c2f67a370dc5638cff08fc412",
            "json_pointers": {"report.json": ["/provenance/origin"], "ledger.json": ["/metadata/provenance/origin"]},
        },
        {
            "replacement": "REDACTED_LOCAL_RUN_DIRECTORY",
            "original_value_sha256": "fdd0e184450211e417bf7d8f6cee78845a6cd0ed40b16abe98fdc1017319f6a8",
            "json_pointers": {"ledger.json": ["/events/0/payload/run_directory", "/phases/frozen/run_directory"]},
        },
    ]
    private_values = [source_origin, run_directory]
    for value, redaction in zip(private_values, redactions):
        if digest(value.encode()) != redaction["original_value_sha256"]:
            raise ValueError("An expected F6 redaction value changed")

    members = dict(original)
    for name in ("report.json", "ledger.json"):
        text = original[name].decode()
        for value, redaction in zip(private_values, redactions):
            expected = len(redaction["json_pointers"].get(name, []))
            if text.count(value) != expected:
                raise ValueError(f"Unexpected redaction count in {name}")
            text = text.replace(value, redaction["replacement"])
        members[name] = text.encode()

    if json.loads(inputs[AGENT]) != json.loads(members["repair.json"]):
        raise ValueError("Saved successful proposal does not match the run repair")
    with tempfile.TemporaryDirectory(prefix="docdrift-demo-") as directory:
        staged = Path(directory)
        write_files(staged, members)
        members["review.html"] = notice(render_review(json.loads(members["report.json"]), staged, archive_available=True))
    members["manifest.json"] = json_bytes({
        "algorithm": "sha256",
        "files": {name: digest(data) for name, data in sorted(members.items()) if name != "manifest.json"},
    })
    published = {"agent/" + name: members[name] for name in LOOSE_MEMBERS}
    published["agent/evidence.zip"] = make_zip(members)
    published["comparison.json"] = inputs[EVALUATION + ".json"]
    published["comparison.md"] = inputs[EVALUATION + ".md"]
    published["comparison.html"] = notice(render_evaluation_review(
        json.loads(inputs[EVALUATION + ".json"]), run_links={RUN_ID: "agent/review.html"},
    ))
    published["proposals/one-shot.json"] = inputs[ONE_SHOT]
    published["proposals/agent.json"] = inputs[AGENT]
    published["index.html"] = INDEX.encode()
    published["README.md"] = README.encode()
    with tempfile.TemporaryDirectory(prefix="docdrift-demo-check-") as directory:
        archive_path = Path(directory) / "evidence.zip"
        archive_path.write_bytes(published["agent/evidence.zip"])
        integrity = verify_evidence(archive_path)
    provenance = {
        "kind": "docdrift_saved_demo_presentation", "case": "F6", "run_id": RUN_ID,
        "original_input_sha256": INPUT_HASHES,
        "original_archive_member_sha256": {name: digest(data) for name, data in sorted(original.items())},
        "original_archive_integrity": original_integrity,
        "redactions": redactions,
        "transformations": [
            "Replaced only the listed report/ledger JSON string values; original formatting retained.",
            "Regenerated agent/review.html with an explicit presentation notice from saved, sanitized inputs.",
            "Regenerated comparison.html with that notice and relative agent/review.html run link.",
            "Rebuilt agent/manifest.json and deterministic ZIP; all other archive member bytes unchanged.",
            "Copied comparison JSON/Markdown and both proposal JSON files byte-for-byte.",
            "Kept source, checks, snippets and log files in the ZIP only to reduce loose-file duplication.",
        ],
        "credential_scan": "All input/output text and ZIP members checked for common key/token/private-key patterns; no matches. No credential file loaded.",
        "published_archive_integrity": integrity,
        "published_file_sha256": {name: digest(data) for name, data in sorted(published.items())},
        "limits": "Unsigned hashes establish internal consistency only. This packaging ran no model, examples, Docker or provider calls; saved verdicts are unchanged.",
    }
    published["provenance.json"] = json_bytes(provenance)
    for name, data in {**members, **published}.items():
        if not name.endswith(".zip"):
            scan(name, data, sanitized=True)
    if {name: digest((ROOT / name).read_bytes()) for name in INPUT_HASHES} != INPUT_HASHES:
        raise ValueError("Original inputs changed while packaging")
    expected_files = set(published)
    if output.exists() and any(path.relative_to(output).as_posix() not in expected_files for path in output.rglob("*") if path.is_file()):
        raise ValueError("Output contains unexpected files; refusing to overwrite")
    write_files(output, published)
    return integrity


README = """# F6: saved real demo evidence

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
"""

INDEX = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>DocDrift · saved F6 demo</title><style>
body{margin:0;background:#f3f5f4;color:#162b38;font:16px/1.6 system-ui,sans-serif}main{max-width:900px;margin:auto;padding:40px 24px}h1{font-size:clamp(28px,5vw,44px);line-height:1.15}h2{font-size:21px}a{color:#17674b;text-underline-offset:4px}section{background:#fff;border:1px solid #dbe3e5;border-radius:10px;margin:22px 0;padding:22px}code{font-size:.85em;overflow-wrap:anywhere}p{color:#586d77}.tag{font-size:13px;color:#17674b;font-weight:700}.notice{padding:14px;background:#fff9ed;border-left:3px solid #d3a342}li{margin:12px 0}.button{display:inline-block;background:#162b38;color:white;border-radius:6px;padding:12px 18px;text-decoration:none}table{border-collapse:collapse;width:100%;text-align:left}th,td{padding:10px;border-bottom:1px solid #dbe3e5}footer{font-size:13px;color:#586d77}</style></head><body><main>
<p class="tag">DocDrift-owned fixture · live Nemotron generation · local Docker execution</p>
<h1>A saved repair you can inspect offline</h1>
<p>F6 follows one broken documentation example through a failed one-shot proposal and a successful agent repair. Browse the recorded evidence directly from this checkout.</p>
<p><a class="button" href="comparison.html">Open strategy comparison</a></p>
<section><h2>The recorded result</h2><table><thead><tr><th>Strategy</th><th>Verified repairs</th><th>Model calls</th><th>Tokens</th></tr></thead><tbody><tr><th>One-shot</th><td>0 / 1</td><td>1</td><td>940</td></tr><tr><th>Agent</th><td>1 / 1</td><td>5</td><td>7,841</td></tr></tbody></table>
<p>Both model strategies made zero false drift reports on one unrelated healthy example. The full comparison, including execution-only, recorded 15 local snippet operations.</p>
<p>This is one exploratory development comparison, added after earlier development results. It is not held out and does not establish general superiority. Execution was local Docker; this evidence does not establish Nebius Sandbox execution.</p></section>
<section><h2>Follow the evidence</h2><ol>
<li><a href="proposals/one-shot.json">Inspect the failed one-shot proposal</a>: <code>OccurrenceIndex.build(words)</code> removed the constructor and was statically rejected.</li>
<li><a href="proposals/agent.json">Read the agent transcript</a>: it listed files, read source and documentation, and probed a replacement before submitting it.</li>
<li><a href="agent/review.html">Review the successful repair</a>: <code>OccurrenceIndex().positions(words, include_empty=True)</code>, with three frozen target checks and three healthy regression checks.</li>
<li><a href="agent/evidence.zip" download>Download the evidence ZIP</a>: saved source, checks, logs, report, patch, ledger, and rebuilt SHA-256 manifest.</li>
</ol></section>
<section><h2>Presentation and integrity</h2><p class="notice">Sanitized presentation copies: two private absolute path values were replaced in report/ledger copies; HTML and unsigned ZIP hashes were rebuilt. Saved outcomes are unchanged. This is not a fresh execution or a signed execution attestation.</p>
<p><a href="README.md">Read provenance, exact redaction locations, and rebuild instructions</a>, or inspect <a href="provenance.json">original input hashes and published integrity results</a>. The original saved evidence was preserved.</p>
<p>Machine-readable comparison: <a href="comparison.json">JSON</a> · <a href="comparison.md">Markdown</a>. Repair: <a href="agent/report.json">report</a> · <a href="agent/repair.json">record</a> · <a href="agent/repair.patch">patch</a>.</p></section>
<footer>No credentials, inference, Docker, web server, or network connection is required to browse these files. Recorded behavior acceptance covers declared inputs, not every possible input.</footer>
</main></body></html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/demo/f6")
    args = parser.parse_args()
    integrity = package(args.output)
    print(f"Packaged saved F6 evidence: {integrity['files_checked']} members verified; ZIP SHA-256 {integrity['archive_sha256']}")


if __name__ == "__main__":
    main()
