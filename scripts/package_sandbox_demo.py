"""Package saved F6 Sandbox evidence offline, without credentials or execution.

Run with ``.venv/bin/python scripts/package_sandbox_demo.py``. Rebuilding needs
the exact private saved artifacts; browsing the committed bundle does not.
"""

from __future__ import annotations

import argparse
import io
import json
import tempfile
import zipfile
from pathlib import Path

from docdrift.evidence import verify_evidence
from docdrift.review import render_review
from package_demo import digest, json_bytes, make_zip, scan, write_files


ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "cb10f48b57264526ada5e04d12bb7641"
SOURCE_RUN_ID = "4fd82cb8be7a449e8815d5366665f4ac"
RUN = f".docdrift/sandbox-f6/runs/{RUN_ID}"
RUNTIME = ".docdrift/sandbox-f6/runtime-report.json"
SOURCE_ARCHIVE = "docs/demo/f6/agent/evidence.zip"
SOURCE_PROPOSAL = "docs/demo/f6/proposals/agent.json"
INPUT_HASHES = {
    RUNTIME: "8dbeb9059b20c3a7e2c6711fe987cc14b606c5332289c08b54c7d4f048ced14b",
    RUN + "/evidence.zip": "f94b30506afc437476c2a74784c7c71187ffb8e8951d76fb8a330d18042be275",
    SOURCE_ARCHIVE: "ac8bd589d9455a897563e4cac1afab27ebd219d2ccb98c933ebde6a6a185944b",
    SOURCE_PROPOSAL: "bf2432df7af32780096e4591a6f331e3c0c5678203c1308dce3dbd026722e370",
}
LOOSE_MEMBERS = {
    "review.html", "report.json", "repair.json", "repair.patch", "ledger.json",
    "commands.json", "manifest.json",
}
NOTICE = (
    '<p class="qualification">Sanitized presentation copy of the saved live '
    'Nebius Sandbox verification of one DocDrift-owned development fixture. '
    'No new inference: the original Nemotron proposal is unchanged. Project ID '
    'and authorization metadata were redacted; HTML and the unsigned ZIP manifest '
    'were rebuilt. Billing remains unverified. This is saved evidence, not a '
    'held-out evaluation or signed execution attestation.</p>'
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def redact(value: object, replacements: dict[str, str], pointers: dict[str, list[str]], path: str = "") -> object:
    """Replace complete JSON string values and disclose every changed pointer."""
    if isinstance(value, dict):
        return {
            key: redact(item, replacements, pointers, path + "/" + key.replace("~", "~0").replace("/", "~1"))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item, replacements, pointers, path + "/" + str(index)) for index, item in enumerate(value)]
    if isinstance(value, str) and value in replacements:
        pointers[value].append(path)
        return replacements[value]
    return value


def package(output: Path) -> dict:
    inputs = {name: (ROOT / name).read_bytes() for name in INPUT_HASHES}
    require({name: digest(data) for name, data in inputs.items()} == INPUT_HASHES,
            "Saved Sandbox input hashes changed; refusing to package different evidence")
    original_integrity = verify_evidence(ROOT / RUN / "evidence.zip")
    source_integrity = verify_evidence(ROOT / SOURCE_ARCHIVE)
    with zipfile.ZipFile(io.BytesIO(inputs[RUN + "/evidence.zip"])) as archive:
        original = {name: archive.read(name) for name in archive.namelist()}
    with zipfile.ZipFile(io.BytesIO(inputs[SOURCE_ARCHIVE])) as archive:
        source = {name: archive.read(name) for name in archive.namelist()}
    for name, data in original.items():
        require((ROOT / RUN / name).read_bytes() == data,
                f"Original archive and saved loose evidence differ: {name}")
    for collection in (inputs, original, source):
        for name, data in collection.items():
            if not name.endswith(".zip"):
                scan(name, data, sanitized=False)

    runtime = json.loads(inputs[RUNTIME])
    report = json.loads(original["report.json"])
    ledger = json.loads(original["ledger.json"])
    require(runtime["status"] == "completed" and runtime["verification_run_id"] == RUN_ID
            and runtime["repair_verdict"] == "behavior_verified" and report["behavior_verified"] is True,
            "Expected saved completed behavior verification")
    require(runtime["source_run_id"] == SOURCE_RUN_ID
            and runtime["source_evidence_sha256"] == INPUT_HASHES[SOURCE_ARCHIVE]
            and report["provenance"]["archive_sha256"] == INPUT_HASHES[SOURCE_ARCHIVE]
            and runtime["source_proposal_sha256"] == INPUT_HASHES[SOURCE_PROPOSAL]
            and original["repair.json"] == inputs[SOURCE_PROPOSAL]
            and json.loads(source["repair.json"]) == json.loads(original["repair.json"]),
            "Saved Sandbox evidence does not match the public F6 source and model proposal")
    linked_members = sorted(name for name in original if name.startswith(("original/", "patched/", "profile/"))
                            or name in {"original.py", "repaired.py", "replacement.py", "repair.patch"})
    require(all(original[name] == source[name] for name in linked_members),
            "Frozen source, checks or patch differ from the public F6 source evidence")
    require(runtime["current_inference_calls"] == 0 and runtime["verifier_inference_calls"] == 0
            and runtime["operation_attempts"] == {"image_imports": 1, "runtime_probes": 3, "verifier_operations": 12}
            and runtime["artifact_bytes_match"] is True and runtime["protected_hashes_preserved"] is True
            and runtime["billed_amount"] is None and runtime["billed_amount_status"] == "unverified"
            and runtime["held_out_evaluation"] is False,
            "Saved scope or qualification differs from the expected bounded run")
    historical = ledger["metadata"]["historical_generation"]
    require(historical["usage"]["model_calls"] == 5
            and historical["usage"]["prompt_tokens"] + historical["usage"]["completion_tokens"] == 7841,
            "Historical model usage differs from the saved F6 proposal")

    authorization = runtime["billing_authorization"]
    replacements = {
        authorization["project_id"]: "REDACTED_NEBIUS_PROJECT_ID",
        authorization["authorized_at_utc"]: "REDACTED_AUTHORIZATION_TIMESTAMP",
        runtime["authorization_record"]: "REDACTED_AUTHORIZATION_RECORD",
        runtime["reuse_record"]: "REDACTED_IMAGE_REUSE_RECORD",
        runtime["verification_report"]: "report.json",
        runtime["review_path"]: "review.html",
    }
    redactions = {
        value: {"replacement": replacement, "original_value_sha256": digest(value.encode()), "json_pointers": {}}
        for value, replacement in replacements.items()
    }
    members = dict(original)
    documents = {
        "report.json": report, "ledger.json": ledger,
        "commands.json": json.loads(original["commands.json"]), "runtime-report.json": runtime,
    }
    sanitized = {}
    for name, document in documents.items():
        pointers = {value: [] for value in replacements}
        sanitized[name] = json_bytes(redact(document, replacements, pointers))
        for value, paths in pointers.items():
            if paths:
                redactions[value]["json_pointers"][name] = paths
    require(all(item["json_pointers"] for item in redactions.values()), "An expected redaction was not applied")
    members.update({name: data for name, data in sanitized.items() if name != "runtime-report.json"})
    with tempfile.TemporaryDirectory(prefix="docdrift-sandbox-demo-") as directory:
        staged = Path(directory)
        write_files(staged, members)
        html = render_review(json.loads(members["report.json"]), staged, archive_available=True)
        members["review.html"] = html.replace("<main>", "<main>" + NOTICE, 1).encode()
    members["manifest.json"] = json_bytes({
        "algorithm": "sha256",
        "files": {name: digest(data) for name, data in sorted(members.items()) if name != "manifest.json"},
    })
    published = {name: members[name] for name in LOOSE_MEMBERS}
    published.update({
        "evidence.zip": make_zip(members),
        "runtime-report.json": sanitized["runtime-report.json"],
        "index.html": INDEX.encode(),
        "README.md": README.encode(),
    })
    with tempfile.TemporaryDirectory(prefix="docdrift-sandbox-demo-check-") as directory:
        archive_path = Path(directory) / "evidence.zip"
        archive_path.write_bytes(published["evidence.zip"])
        integrity = verify_evidence(archive_path)
    provenance = {
        "kind": "docdrift_saved_sandbox_demo_presentation", "case": "F6", "run_id": RUN_ID,
        "source_run_id": SOURCE_RUN_ID,
        "original_input_sha256": INPUT_HASHES,
        "source_linkage": {
            "source_evidence": "../f6/agent/evidence.zip", "source_evidence_sha256": INPUT_HASHES[SOURCE_ARCHIVE],
            "source_proposal": "../f6/proposals/agent.json", "source_proposal_sha256": INPUT_HASHES[SOURCE_PROPOSAL],
            "repair_json_is_byte_identical_to_source_proposal": True,
            "byte_identical_source_archive_members": linked_members,
        },
        "original_archive_member_sha256": {name: digest(data) for name, data in sorted(original.items())},
        "original_archive_integrity": original_integrity,
        "source_archive_integrity": source_integrity,
        "redactions": list(redactions.values()),
        "transformations": [
            "Replaced only disclosed complete JSON string values in report, ledger, commands, and runtime-report presentation copies; reserialized those JSON files.",
            "Regenerated review.html with an explicit saved-evidence notice.",
            "Rebuilt the unsigned manifest and deterministic ZIP; all other original archive member bytes are unchanged.",
            "Published the sanitized runtime-report separately from the original 39-member evidence payload; raw provider responses, account records and private state are omitted.",
            "Added an index and README describing source linkage, current versus historical usage, and limitations.",
        ],
        "credential_scan": "Input/output text and all ZIP members checked for common key/token/private-key patterns; no matches. No credential file loaded.",
        "published_archive_integrity": integrity,
        "published_file_sha256": {name: digest(data) for name, data in sorted(published.items())},
        "limits": "Unsigned hashes establish internal consistency only, not origin or signed execution attestation. Packaging made no provider calls or new execution. One owned development case, not held out; billing remains unverified.",
    }
    published["provenance.json"] = json_bytes(provenance)
    for name, data in {**members, **published}.items():
        if not name.endswith(".zip"):
            # This is an intentionally public example destination, not a saved host path.
            scan(name, data.replace(b"/tmp/docdrift-f6-sandbox-rebuild", b"/tmp/docdrift-f6-rebuild"), sanitized=True)
            require(not any(value.encode() in data for value in replacements),
                    f"Expected private value remains in {name}; value withheld")
    require({name: digest((ROOT / name).read_bytes()) for name in INPUT_HASHES} == INPUT_HASHES,
            "Original inputs changed while packaging")
    if output.exists():
        require(not any(path.relative_to(output).as_posix() not in published for path in output.rglob("*") if path.is_file()),
                "Output contains unexpected files; refusing to overwrite")
    write_files(output, published)
    return integrity


README = """# F6: saved live Nebius Sandbox verification

Open [index.html](index.html) directly from a fresh clone, with no credentials,
server, Docker, inference, or network. [review.html](review.html) is self-contained.

On October 21, the saved October 15 Nemotron agent repair was re-verified on live
Nebius Sandboxes: original failure reproduced, three frozen repaired target
inputs and three healthy regression inputs passed, and protected hashes stayed
unchanged. This is one **DocDrift-owned development fixture**, not held out;
it does not establish general model advantage or competition eligibility.

The source is the exact public [F6 evidence ZIP](../f6/agent/evidence.zip), SHA-256
`ac8bd589d9455a897563e4cac1afab27ebd219d2ccb98c933ebde6a6a185944b`.
[repair.json](repair.json) is byte-identical to the saved [agent proposal](../f6/proposals/agent.json),
SHA-256 `bf2432df7af32780096e4591a6f331e3c0c5678203c1308dce3dbd026722e370`.
The source, frozen checks, snippets and patch also match that source archive.
Historical generation: five Nemotron calls, 7,841 tokens. This Sandbox
verification: **zero new inference**, one failed import, three runtime probes,
and twelve verifier operations. The import failed with registry HTTP 404;
recovery used the existing public `python:3.12-slim` image UUID
`4fa16c8f-62a9-35a4-a4ea-07b7e8cd44ae`, without another import.

The probes recorded Python 3.12, effective UID 65534, only the loopback interface,
artifact bytes matching after download, and terminal cancellation. Cancellation
captures are incomplete; do not interpret them as complete guest output. The
runtime report is the final completed resume observation. Its start/update
timestamps do not measure the original run duration, and its pre-request
cancellation observation may come from resume.

- [runtime-report.json](runtime-report.json): sanitized saved orchestration/probe summary.
- [review.html](review.html), [report.json](report.json), [ledger.json](ledger.json): saved verifier outcome and receipts.
- [repair.patch](repair.patch), [repair.json](repair.json): exact accepted patch and proposal.
- [evidence.zip](evidence.zip): 39 manifested evidence payload files, plus rebuilt manifest; source/checks/logs remain inside the ZIP.
- [provenance.json](provenance.json): exact original and presentation hashes, redaction JSON pointers, source linkage and offline integrity results.

Project ID, authorization timestamp/record paths, and private absolute report
paths were replaced in presentation copies. Every replacement and original
value hash is disclosed in provenance.json. Report/ledger/commands JSON was reserialized,
HTML regenerated, and ZIP hashes rebuilt. All other original archive member
bytes are unchanged, including the model proposal and patch. The original
gitignored artifacts are preserved; the original Sandbox ZIP SHA-256 is
`f94b30506afc437476c2a74784c7c71187ffb8e8951d76fb8a330d18042be275`.
Raw provider responses, account records, credentials and private state are not
published. Common credential-pattern scans found no matches; no key file was read.

**Billing remains unverified.** Raw resource fields, including `cost`, are
diagnostic values with unconfirmed units/aggregation, not invoice totals or
proof of free execution. Unsigned SHA-256 manifests establish internal
integrity, not authenticity or signed execution attestation. Offline packaging
and integrity checking do not re-execute examples or endorse saved claims.

From the repository root:

```bash
.venv/bin/docdrift verify-evidence docs/demo/f6-sandbox/evidence.zip
```

To rebuild, the exact original `.docdrift/` inputs are required:

```bash
.venv/bin/python scripts/package_sandbox_demo.py
.venv/bin/python scripts/package_sandbox_demo.py --output /tmp/docdrift-f6-sandbox-rebuild
```

Packaging validates frozen inputs, source linkage, original and published ZIPs,
and matching saved loose files. It performs no inference, example execution,
Docker, network, or provider calls. Provenance records output hashes except its
own hash. The output ZIP is deterministic.
"""

INDEX = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>DocDrift · saved F6 Sandbox verification</title><style>
body{margin:0;background:#f3f5f4;color:#162b38;font:16px/1.6 system-ui,sans-serif}main{max-width:900px;margin:auto;padding:40px 24px}h1{font-size:clamp(28px,5vw,44px);line-height:1.15}h2{font-size:21px}a{color:#17674b;text-underline-offset:4px}section{background:#fff;border:1px solid #dbe3e5;border-radius:10px;margin:22px 0;padding:22px}code{font-size:.85em;overflow-wrap:anywhere}p{color:#586d77}.tag{font-size:13px;color:#17674b;font-weight:700}.notice{padding:14px;background:#fff9ed;border-left:3px solid #d3a342}li{margin:12px 0}.button{display:inline-block;background:#162b38;color:white;border-radius:6px;padding:12px 18px;text-decoration:none}table{border-collapse:collapse;width:100%;text-align:left}th,td{padding:10px;border-bottom:1px solid #dbe3e5}footer{font-size:13px;color:#586d77}</style></head><body><main>
<p class="tag">Owned development fixture · saved Nemotron repair · live Nebius Sandboxes</p>
<h1>The same saved repair, verified on Sandboxes</h1>
<p>The October 15 agent proposal was re-verified on October 21 without new inference. Browse the saved original failure, patch, frozen checks and recorded operation receipts.</p>
<p><a class="button" href="review.html">Open saved verification review</a></p>
<section><h2>What the saved run records</h2><table><tbody>
<tr><th>Original failure</th><td><code>OccurrenceIndex().build(words)</code> reproduced</td></tr>
<tr><th>Accepted repair</th><td><code>OccurrenceIndex().positions(words, include_empty=True)</code></td></tr>
<tr><th>Final behavior checks</th><td>3 target inputs + 3 healthy regression inputs passed</td></tr>
<tr><th>Protected source/checks</th><td>Hashes preserved</td></tr>
<tr><th>Current inference</th><td>0 calls</td></tr>
<tr><th>Historical generation</th><td>5 Nemotron calls · 7,841 tokens</td></tr>
<tr><th>Operation attempts</th><td>1 failed import · 3 runtime probes · 12 verifier operations</td></tr>
</tbody></table><p>The failed import was preserved. Recovery used an existing public Python 3.12 image without another import. The probes recorded effective UID 65534, only the loopback interface, matching downloaded artifact bytes, and terminal cancellation handling.</p>
<p class="notice">This is one DocDrift-owned development case, not held out. It does not establish general model advantage, exhaustive behavior coverage, or competition eligibility. Cancellation captures are incomplete. Billing remains unverified; raw resource cost fields are diagnostic values, not charges.</p></section>
<section><h2>Follow the evidence</h2><ol>
<li><a href="../f6/index.html">Read the original Nemotron/Docker comparison</a>, including the <a href="../f6/proposals/agent.json">exact saved model proposal</a>.</li>
<li><a href="review.html">Inspect the Sandbox original failure and final checks</a>, or download the <a href="evidence.zip" download>sanitized evidence ZIP</a>.</li>
<li><a href="runtime-report.json">Inspect the runtime/probe summary</a>. This is the final completed resume observation; its timestamps do not measure the original run duration.</li>
<li><a href="provenance.json">Check original hashes, exact source linkage, presentation hashes and disclosed redactions</a>.</li>
</ol><p>Verifier <a href="report.json">report</a> · <a href="ledger.json">ledger</a> · <a href="repair.json">proposal</a> · <a href="repair.patch">patch</a>.</p></section>
<section><h2>Saved evidence and integrity</h2><p class="notice">Presentation copies redact project and authorization metadata and private report paths. HTML and unsigned ZIP hashes were rebuilt; recorded outcomes, source, frozen checks, proposal and patch remain unchanged. Hashes establish internal integrity, not authenticity or signed execution attestation.</p>
<p><a href="README.md">Read the exact qualifications and offline rebuild/check instructions</a>. Packaging made no provider calls, new inference, or example executions. Original private artifacts were preserved.</p></section>
<footer>Open these files directly from a fresh clone. No credentials, inference, Docker, web server, or network connection is required.</footer>
</main></body></html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/demo/f6-sandbox")
    args = parser.parse_args()
    integrity = package(args.output)
    print(f"Packaged saved F6 Sandbox evidence: {integrity['files_checked']} members verified; ZIP SHA-256 {integrity['archive_sha256']}")


if __name__ == "__main__":
    main()
