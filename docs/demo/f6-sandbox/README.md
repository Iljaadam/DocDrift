# F6: saved live Nebius Sandbox verification

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
