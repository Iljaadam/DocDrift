# Constructed verifier challenge

**October 28, 2026 · owned fixture · real local Docker execution**

None of 16 deliberately bad proposals received behavioral verification.
The good manual control passed all three repaired inputs and all three healthy
regressions, with protected hashes preserved.

| Path through the verifier | Cases | Result |
|---|---|---|
| Invalid document, protected-file, or non-text payload | 9 | Rejected at submission gates |
| Bad code replacement | 7 | Real engine run; none behavior-verified |
| Good manual repair | 1 | `behavior_verified` |

The discarded-result proposal retained the API call and printed a fixed answer.
It exited zero for every input and matched one expected output, but failed the
other two inputs and the result-flow requirement. The final verdict was
`execution_passed`, with `behavior_verified: false`.

- **Good control:** [review](control/review.html) · [evidence ZIP](control/evidence.zip).
- **Discarded result:** [review](discarded-result/review.html) · [evidence ZIP](discarded-result/evidence.zip).
- **All cases:** [summary JSON](report.json).

This used 54 local snippet operations and no model calls, Nebius operations,
or hosted judge attempts. Seven bad replacements and the control entered the
production engine; the other nine payloads have boundary evidence only.

The downloadable archives are presentation copies: controller paths were
redacted in JSON, HTML was regenerated, and unsigned manifests were rebuilt.
Each ZIP includes `presentation.json` with original archive/member hashes and
the files changed for presentation. Verdicts and observed outputs were preserved.
Both archives pass `docdrift verify-evidence`; this checks bytes, not authenticity.

See [coverage and reproduction](../../VERIFICATION_CHALLENGE.md).
