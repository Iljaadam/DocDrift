# Publication security review — October 28, 2026

The review covered tracked source and documentation, reachable Git history,
committed evidence ZIPs, locked dependencies, and the hosted judge's access
boundary. This is a targeted review, not a guarantee of security.

## Fixes

- **Certificate trust:** upgraded `certifi` from `2026.7.22` to `2026.10.23` and
  added a `>=2026.10.19` package minimum. The old version included roots affected
  by [GHSA-6q48-6c7w-9gw2](https://github.com/certifi/python-certifi/security/advisories/GHSA-6q48-6c7w-9gw2).
- **Provider credentials:** model requests now use the fixed Token Factory HTTPS
  endpoint, reject redirects, ignore environment proxies, and omit provider
  error bodies. Responses remain capped at 1 MiB, without automatic retries.
- **Git hashes:** SHA-1 is explicitly marked as Git content-address compatibility,
  rather than a security primitive. Evidence manifests use SHA-256.

## Checks

| Check | Outcome |
|---|---|
| Gitleaks 8.30.1, all 49 pre-publication commits | Two findings reviewed: a synthetic fixture key and a test idempotency UUID |
| Current tracked files and nested evidence archives | Same two synthetic test values; no real credential identified |
| Exact-match scan for five configured credential forms | No matches across 408 reachable blobs and six historical ZIP blobs |
| OSV query of all 15 locked third-party package versions | Zero advisory matches after the dependency update |
| Full offline suite, including redirect/error/response-limit regressions | 1,027 passed |
| Constructed challenge with real Docker execution | No bad proposal behavior-verified; good manual control verified |

Bandit findings were reviewed alongside the code. Remaining notices concern
argument-list subprocesses, fixed internal SQL column choices, temporary-path
checks, synthetic assertions, and other contextual uses. The scan is not claimed
to be warning-free. No shell execution or untrusted SQL interpolation was found.

The judge requires authentication, bounds HTTP body size and concurrent
connections, enforces same-origin admission, and serves only allowlisted
artifacts. Its UI renders values as text, while saved HTML escapes evidence and
uses restrictive response headers. Provider credentials and private state remain
outside Git and downloadable evidence.

## Scope

Execution is intended for trusted, curated fixtures. It is not a general service
for running arbitrary public repositories. Static checks and varied inputs cover
the declared contracts, not arbitrary semantic equivalence. Billing coverage,
credit expiry, and whether the fixed shared quota satisfies judging requirements
remain separate operational questions.

Future dependency releases and credential changes need fresh checks. Report a
security issue through the repository owner's GitHub profile; never include live
credentials in a public issue.
