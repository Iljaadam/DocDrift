# Offline evidence integrity

Run from a checkout or installed wheel, with no Docker or provider credentials:

```sh
docdrift verify-evidence /path/to/evidence.zip
```

Success returns JSON with `status: integrity_verified`, `files_checked`, the
archive SHA-256, and uncompressed bytes. Invalid or unsupported archives exit 2.
The checker reads without extracting, importing, executing, or opening network
connections. It creates no state directory.

The checker requires a strict SHA-256 manifest covering every regular-file member
except itself, including `report.json`. It checks ZIP structure, CRCs, lengths,
complete compressed streams, and member hashes. Duplicate/noncanonical/unsafe
paths, symlinks, special files, encryption, malformed manifests, and missing or
unlisted members are rejected.

Limits: 25 MiB archive bytes, 20 MiB uncompressed bytes including the manifest,
1 MiB manifest, and 2,500 members. Only regular stored/deflated entries without
data descriptors are supported, matching the exporter. ZIP64 and multipart
archives are unsupported. Decompression is bounded even when lengths are forged.

`execution_attested: false` and `authenticity_attested: false` are deliberate.
The manifest is unsigned; anyone can replace both content and hashes. Integrity
identifies the inspected bytes and checks internal consistency. It does not
prove who produced them, that execution occurred, or that saved verdicts are true.
Inspect provenance, checks, logs, and reports, and rerun the declared fixture to
assess those claims. Synthetic Sandbox archives can pass integrity while still
containing no runtime execution evidence.
