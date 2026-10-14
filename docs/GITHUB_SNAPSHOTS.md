# Public GitHub inspection snapshots

`resolve_public_github` accepts `owner/name` or
`https://github.com/owner/name` and a bounded branch, tag, or commit reference.
It performs anonymous reads without GitHub CLI login, tokens, or target code
execution. Public snapshots are for inspection in this slice. They do not
authorize executing a public repository or establish behavioral verification.

The resolver reads the commit endpoint once, requires full commit and tree
SHAs, and uses the tree SHA and commit SHA for every subsequent request.
GitHub documents branch/tag/SHA resolution and anonymous access for public
repositories. [Commit API](https://docs.github.com/en/rest/commits/commits#get-a-commit)

A recursive Git tree supplies blob identities, sizes, directory inventory,
and submodule/symlink modes. The resolver rejects truncated trees rather than
treating an incomplete scan as evidence of no submodules.
[Git trees API](https://docs.github.com/en/rest/git/trees#get-a-tree)

The pinned archive REST request follows a bounded, validated redirect to
GitHub's codeload host. HTTPS requests and redirects stay on `api.github.com`,
`github.com`, or `codeload.github.com`. Explicit requests contain no client
default authorization, cookies, or credential headers. Private repositories,
credential URLs, alternate hosts, query-bearing repository URLs, and
noncanonical paths are rejected.
[Archive API](https://docs.github.com/en/rest/repos/contents#download-a-repository-archive-tar)

Limits are 25 MiB downloaded archive bytes, 50 MiB extracted file bytes, and
2,000 tree/archive entries after removing the enclosing archive directory.
JSON metadata is capped at 4 MiB. Gzip expansion, including tar headers and
padding, is capped at 54 MiB. Physical tar header sizes are validated before
PAX or GNU extensions can allocate their declared payloads, with at most
64 KiB per extended metadata payload. API requests use
bounded streams, no automatic retries, a 60-second operation deadline checked
between reads, and at most 10 seconds of inactivity per network read.

Before destination writes, the resolver validates one enclosing directory,
every path, every member type, file sizes, and every Git blob SHA-1 identity.
The archive must contain exactly the files in the pinned tree. Links, special
files, sparse files, LFS pointers, archive omissions from `export-ignore`, and
content changes from `export-subst` are unsupported. A snapshot destination
must be new and must not traverse symlinks.

Provenance records the canonical origin URL, full commit SHA, tree SHA,
downloaded archive SHA-256, extracted file SHA-256 hashes, and discovered
license filenames. GitHub may change archive compression bytes while keeping
the contents for a pinned commit stable, so archive and extracted-content
identities are recorded separately.
[Archive stability](https://docs.github.com/en/repositories/working-with-files/using-files/downloading-source-code-archives#stability-of-source-code-archives)

Tests use mocked HTTP transports and owned synthetic archives. They execute
no target code and make no external requests. This implementation adds no
Nebius calls, paid provisioning, or assumed credits.
