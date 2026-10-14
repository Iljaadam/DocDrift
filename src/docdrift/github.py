"""Bounded anonymous GitHub snapshots for inspection; no target code executes."""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import tarfile
import tempfile
import time
from contextlib import closing
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urljoin, urlsplit

import httpx

from .snapshot import SnapshotError, extract_archive, safe_path


_DOWNLOAD_LIMIT = 25 * 1024 * 1024
_EXTRACTED_LIMIT = 50 * 1024 * 1024
_TAR_LIMIT = 54 * 1024 * 1024
_ENTRY_LIMIT = 2000
_JSON_LIMIT = 4 * 1024 * 1024
_DEADLINE_SECONDS = 60
_CHUNK_SIZE = 65536
_HEADER_LIMIT = 65536
_REDIRECT_LIMIT = 3
_HOSTS = {"api.github.com", "github.com", "codeload.github.com"}
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_OWNER = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?\Z")
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]{1,100}\Z")
_REF = re.compile(r"[A-Za-z0-9._/-]{1,256}\Z")


def _repository_name(repository: str) -> tuple[str, str]:
    if not isinstance(repository, str) or len(repository) > 256 or any(ord(char) <= 32 or ord(char) == 127 for char in repository) or "?" in repository or "#" in repository:
        raise SnapshotError("Require a public GitHub owner/name or canonical HTTPS repository URL")
    slug = repository
    if repository.startswith("https://"):
        parsed = urlsplit(repository)
        if parsed.netloc != "github.com" or parsed.query or parsed.fragment:
            raise SnapshotError("Require a canonical GitHub URL without credentials, port, query, or fragment")
        slug = parsed.path.removeprefix("/")
    parts = slug.split("/")
    if len(parts) != 2:
        raise SnapshotError("Require exactly one GitHub owner and repository name")
    owner, name = parts
    if not _OWNER.fullmatch(owner) or "--" in owner or not _REPOSITORY.fullmatch(name) or name in {".", ".."} or name.endswith(".git"):
        raise SnapshotError("Invalid GitHub owner or repository name")
    return owner, name


def _revision(ref: str) -> str:
    if not isinstance(ref, str) or not _REF.fullmatch(ref) or ref.startswith(("-", "/")) or ref.endswith(("/", ".")) or ".." in ref or "//" in ref:
        raise SnapshotError("Require a bounded branch, tag, or commit reference without traversal or URL syntax")
    if any(part.startswith(".") or part.endswith(".lock") for part in ref.split("/")):
        raise SnapshotError("Invalid GitHub commit reference")
    return quote(ref, safe="")


def _url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise SnapshotError("Invalid GitHub redirect URL") from exc
    if parsed.scheme != "https" or parsed.hostname not in _HOSTS or parsed.username is not None or parsed.password is not None or port is not None or "#" in url or "\\" in url or any(ord(char) <= 32 or ord(char) == 127 for char in url):
        raise SnapshotError("GitHub redirects must stay on approved HTTPS hosts without credentials")
    if "?" in url and not (parsed.hostname == "api.github.com" and parsed.query == "recursive=1"):
        raise SnapshotError("Unexpected query in GitHub redirect")
    decoded_path = unquote(parsed.path)
    if "\\" in decoded_path or any(ord(char) < 32 or ord(char) == 127 for char in decoded_path) or any(part in {".", ".."} for part in decoded_path.split("/")):
        raise SnapshotError("Traversal in GitHub redirect")
    return url


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise SnapshotError("GitHub snapshot request deadline exceeded")
    return remaining


def _fetch(client: httpx.Client, url: str, limit: int, deadline: float, *, output=None, archive_commit: str | None = None) -> tuple[bytes, str]:
    """Stream raw response bytes with an independent cap and manual redirects."""
    for redirects in range(_REDIRECT_LIMIT + 1):
        url = _url(url)
        timeout = httpx.Timeout(min(10.0, _remaining(deadline)))
        # Construct directly: client auth/default headers/cookies never become
        # part of these public requests, including cross-host redirects.
        request = httpx.Request(
            "GET", url,
            headers={"Accept": "application/vnd.github+json", "Accept-Encoding": "identity", "User-Agent": "DocDrift/0.1 public-inspection", "X-GitHub-Api-Version": "2026-03-10"},
            extensions={"timeout": timeout.as_dict()},
        )
        try:
            response = client.send(request, stream=True, auth=None, follow_redirects=False)
            with closing(response):
                _remaining(deadline)
                if response.status_code in {301, 302, 303, 307, 308}:
                    if redirects == _REDIRECT_LIMIT or "location" not in response.headers:
                        raise SnapshotError("GitHub snapshot redirect limit exceeded or Location is absent")
                    url = _url(urljoin(url, response.headers["location"]))
                    if archive_commit and urlsplit(url).path.rstrip("/").split("/")[-1] not in {archive_commit, f"{archive_commit}.tar.gz"}:
                        raise SnapshotError("Archive redirect does not retain the pinned commit")
                    continue
                if response.status_code != 200:
                    raise SnapshotError(f"Public GitHub snapshot request failed (HTTP {response.status_code}); no authentication or retry was attempted")
                if archive_commit and urlsplit(url).hostname != "codeload.github.com":
                    raise SnapshotError("Pinned GitHub archive must be delivered by codeload.github.com")
                if response.headers.get("content-encoding", "identity").lower() not in {"", "identity"}:
                    raise SnapshotError("Unexpected HTTP content encoding in GitHub response")
                declared_size = response.headers.get("content-length")
                if declared_size is not None and (len(declared_size) > 20 or not declared_size.isascii() or not declared_size.isdecimal() or int(declared_size) > limit):
                    raise SnapshotError("GitHub response exceeds its byte limit or has invalid Content-Length")
                content = bytearray()
                digest = hashlib.sha256()
                size = 0
                # Preloaded responses occur with injected mock transports;
                # normal network responses remain raw, bounded streams.
                chunks = (response.content,) if response.is_stream_consumed else response.iter_raw(chunk_size=_CHUNK_SIZE)
                for chunk in chunks:
                    _remaining(deadline)
                    size += len(chunk)
                    if size > limit:
                        raise SnapshotError("GitHub response exceeds its byte limit")
                    digest.update(chunk)
                    if output is None:
                        content.extend(chunk)
                    else:
                        output.write(chunk)
                return bytes(content), digest.hexdigest()
        except httpx.HTTPError as exc:
            raise SnapshotError("Public GitHub snapshot request failed or timed out; no retry was attempted") from exc
    raise SnapshotError("GitHub redirect limit exceeded")


def _json_response(client: httpx.Client, url: str, deadline: float) -> dict:
    content, _ = _fetch(client, url, _JSON_LIMIT, deadline)
    try:
        data = json.loads(content)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise SnapshotError("GitHub returned invalid JSON metadata") from exc
    if not isinstance(data, dict):
        raise SnapshotError("GitHub metadata must be a JSON object")
    return data


def _path(value) -> str:
    if not isinstance(value, str):
        raise SnapshotError("GitHub snapshot paths must be strings")
    try:
        encoded = value.encode("utf-8")
    except UnicodeError as exc:
        raise SnapshotError("GitHub snapshot paths must be valid UTF-8") from exc
    if len(encoded) > 4096 or any(len(part.encode("utf-8")) > 255 for part in PurePosixPath(value).parts) or any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise SnapshotError("GitHub snapshot path is overlong or contains control characters")
    path = safe_path(value)
    if path == ".":
        raise SnapshotError("GitHub snapshot paths must identify an entry below the root")
    return path


def _tree(data: dict, expected_sha: str) -> tuple[dict[str, dict], set[str]]:
    if data.get("sha") != expected_sha or data.get("truncated") is not False or not isinstance(data.get("tree"), list):
        raise SnapshotError("Require a complete, untruncated Git tree for the pinned commit")
    if len(data["tree"]) > _ENTRY_LIMIT:
        raise SnapshotError("Git tree exceeds 2,000 entries")
    files = {}
    directories = set()
    seen = set()
    total = 0
    for item in data["tree"]:
        if not isinstance(item, dict):
            raise SnapshotError("Invalid Git tree entry")
        path = _path(item.get("path"))
        if path in seen:
            raise SnapshotError("Duplicate path in Git tree")
        seen.add(path)
        mode, kind = item.get("mode"), item.get("type")
        if mode == "160000" or kind == "commit":
            raise SnapshotError("Submodules are unsupported")
        if mode == "120000":
            raise SnapshotError("Symlinks are unsupported")
        if not isinstance(item.get("sha"), str) or not _SHA.fullmatch(item["sha"]):
            raise SnapshotError("Git tree entry requires a full blob or tree SHA")
        if mode == "040000" and kind == "tree":
            directories.add(path)
        elif mode in {"100644", "100755"} and kind == "blob":
            size = item.get("size")
            if type(size) is not int or size < 0:
                raise SnapshotError("Git blob requires a valid declared size")
            total += size
            if total > _EXTRACTED_LIMIT:
                raise SnapshotError("Git tree exceeds the 50 MiB extracted limit")
            files[path] = item
        else:
            raise SnapshotError("Unsupported Git tree mode or type")
    for path in seen:
        for parent in PurePosixPath(path).parents:
            if str(parent) != "." and str(parent) not in directories:
                raise SnapshotError("Git tree is missing a parent directory")
    return files, directories


def _physical_tar(stream, size: int, deadline: float) -> None:
    """Bound header sizes before tarfile reads PAX/GNU extension payloads."""
    stream.seek(0)
    while True:
        _remaining(deadline)
        header = stream.read(512)
        if len(header) != 512:
            raise SnapshotError("Truncated GitHub tar archive")
        if header == b"\0" * 512:
            while trailing := stream.read(_CHUNK_SIZE):
                _remaining(deadline)
                if trailing.strip(b"\0"):
                    raise SnapshotError("Unexpected trailing data in GitHub tar archive")
            stream.seek(0)
            return
        try:
            item = tarfile.TarInfo.frombuf(header, encoding="utf-8", errors="surrogateescape")
        except tarfile.TarError as exc:
            raise SnapshotError("Invalid GitHub tar header") from exc
        if item.size < 0 or item.size > _TAR_LIMIT:
            raise SnapshotError("GitHub tar member exceeds the expansion limit")
        next_header = stream.tell() + ((item.size + 511) // 512) * 512
        if next_header > size:
            raise SnapshotError("Truncated GitHub tar member")
        if item.type == tarfile.GNUTYPE_SPARSE:
            raise SnapshotError("GitHub archive sparse files are unsupported")
        if item.type in {tarfile.XHDTYPE, tarfile.XGLTYPE, tarfile.GNUTYPE_LONGNAME, tarfile.GNUTYPE_LONGLINK}:
            if item.size > _HEADER_LIMIT:
                raise SnapshotError("GitHub tar extended metadata exceeds its expansion limit")
            payload = stream.read(item.size)
            if item.type in {tarfile.XHDTYPE, tarfile.XGLTYPE}:
                position = 0
                while position < len(payload):
                    separator = payload.find(b" ", position)
                    if separator < 0 or separator - position > 20:
                        raise SnapshotError("Invalid GitHub PAX metadata")
                    digits = payload[position:separator]
                    if not digits.isdigit():
                        raise SnapshotError("Invalid GitHub PAX metadata")
                    end = position + int(digits)
                    if end <= separator + 1 or end > len(payload) or payload[end - 1:end] != b"\n":
                        raise SnapshotError("Invalid GitHub PAX metadata")
                    key = payload[separator + 1:end - 1].partition(b"=")[0]
                    if key.startswith(b"GNU.sparse."):
                        raise SnapshotError("GitHub archive sparse files are unsupported")
                    position = end
        stream.seek(next_header)


def _archive(compressed, destination: Path, expected_files: dict[str, dict], expected_directories: set[str], deadline: float) -> dict[str, str]:
    with tempfile.TemporaryFile() as expanded, tempfile.TemporaryFile() as normalized:
        compressed.seek(0)
        size = 0
        try:
            with gzip.GzipFile(fileobj=compressed, mode="rb") as decoder:
                while chunk := decoder.read(_CHUNK_SIZE):
                    _remaining(deadline)
                    size += len(chunk)
                    if size > _TAR_LIMIT:
                        raise SnapshotError("GitHub gzip archive exceeds its 54 MiB expansion limit")
                    expanded.write(chunk)
            _physical_tar(expanded, size, deadline)
            entries = []
            seen = set()
            topdir = None
            top_seen = False
            total = 0
            with tarfile.open(fileobj=expanded, mode="r:") as source:
                for item in source:
                    _remaining(deadline)
                    name = _path(item.name)
                    parts = PurePosixPath(name).parts
                    if topdir is None:
                        topdir = parts[0]
                    if parts[0] != topdir:
                        raise SnapshotError("GitHub archive must have one consistent top directory")
                    if len(parts) == 1:
                        if not item.isdir() or entries or top_seen:
                            raise SnapshotError("Invalid GitHub archive top directory")
                        top_seen = True
                        continue
                    path = "/".join(parts[1:])
                    if path in seen:
                        raise SnapshotError("Duplicate path in GitHub archive")
                    seen.add(path)
                    if len(entries) >= _ENTRY_LIMIT:
                        raise SnapshotError("GitHub archive exceeds 2,000 entries")
                    if item.sparse is not None or (not item.isdir() and not item.isfile()):
                        raise SnapshotError("GitHub archive links, sparse files, and special files are unsupported")
                    if item.size < 0:
                        raise SnapshotError("Invalid GitHub archive member size")
                    total += item.size
                    if total > _EXTRACTED_LIMIT:
                        raise SnapshotError("GitHub archive exceeds the 50 MiB extracted limit")
                    if item.isdir():
                        if item.size != 0 or path not in expected_directories:
                            raise SnapshotError("Archive directory does not match the pinned Git tree")
                    else:
                        expected = expected_files.get(path)
                        if expected is None or item.size != expected["size"]:
                            raise SnapshotError("Archive file inventory or size does not match the pinned Git tree")
                        fileobj = source.extractfile(item)
                        assert fileobj is not None
                        digest = hashlib.sha1(f"blob {item.size}\0".encode("ascii"))
                        first = fileobj.read(128)
                        if first.startswith(b"version https://git-lfs.github.com/spec/v1"):
                            raise SnapshotError("LFS pointers are unsupported")
                        digest.update(first)
                        while chunk := fileobj.read(_CHUNK_SIZE):
                            _remaining(deadline)
                            digest.update(chunk)
                        if digest.hexdigest() != expected["sha"]:
                            raise SnapshotError("Archive blob does not match the pinned Git tree")
                    entries.append((path, item))
                if {path for path, item in entries if item.isfile()} != set(expected_files):
                    raise SnapshotError("GitHub archive omits files from the pinned Git tree (export-ignore is unsupported)")
                with tarfile.open(fileobj=normalized, mode="w", format=tarfile.PAX_FORMAT) as target:
                    for path, item in entries:
                        _remaining(deadline)
                        clean = tarfile.TarInfo(path)
                        clean.type = tarfile.DIRTYPE if item.isdir() else tarfile.REGTYPE
                        clean.size = item.size
                        clean.mode = 0o755 if item.isdir() else 0o644
                        target.addfile(clean, source.extractfile(item) if item.isfile() else None)
            normalized_size = normalized.tell()
            if normalized_size > _TAR_LIMIT:
                raise SnapshotError("Normalized GitHub tar archive exceeds its metadata limit")
            normalized.seek(0)
            _remaining(deadline)
            return extract_archive(normalized.read(_TAR_LIMIT + 1), destination, max_archive_bytes=_TAR_LIMIT)
        except SnapshotError:
            raise
        except (OSError, EOFError, tarfile.TarError, ValueError, RecursionError, UnicodeError) as exc:
            raise SnapshotError("GitHub returned an invalid or truncated gzip tar archive") from exc


def resolve_public_github(repository: str, ref: str, destination: Path, *, client: httpx.Client | None = None) -> dict:
    """Resolve a public ref once, verify its Git tree, and extract its pinned tar."""
    owner, name = _repository_name(repository)
    revision = _revision(ref)
    if destination.is_symlink() or any(parent.is_symlink() for parent in destination.parents) or destination.exists():
        raise SnapshotError("Public snapshot destination must be new and must not traverse symlinks")
    deadline = time.monotonic() + _DEADLINE_SECONDS
    owns_client = client is None
    client = client or httpx.Client(trust_env=False)
    try:
        api = f"https://api.github.com/repos/{owner}/{name}"
        resolved = _json_response(client, f"{api}/commits/{revision}", deadline)
        commit = resolved.get("sha")
        commit_metadata = resolved.get("commit")
        tree_metadata = commit_metadata.get("tree") if isinstance(commit_metadata, dict) else None
        tree_sha = tree_metadata.get("sha") if isinstance(tree_metadata, dict) else None
        if not isinstance(commit, str) or not _SHA.fullmatch(commit) or not isinstance(tree_sha, str) or not _SHA.fullmatch(tree_sha):
            raise SnapshotError("GitHub commit metadata requires full commit and tree SHAs")
        if _SHA.fullmatch(ref.lower()) and commit != ref.lower():
            raise SnapshotError("GitHub returned a different commit than the requested pinned SHA")
        files, directories = _tree(_json_response(client, f"{api}/git/trees/{tree_sha}?recursive=1", deadline), tree_sha)
        with tempfile.TemporaryFile() as archive:
            _, archive_sha256 = _fetch(client, f"{api}/tarball/{commit}", _DOWNLOAD_LIMIT, deadline, output=archive, archive_commit=commit)
            hashes = _archive(archive, destination, files, directories, deadline)
        return {"kind": "public_github", "origin": f"https://github.com/{owner}/{name}", "commit": commit, "tree_sha": tree_sha, "archive_sha256": archive_sha256, "files": hashes, "license_files": [path for path in hashes if PurePosixPath(path).name.lower().startswith(("license", "copying"))]}
    finally:
        if owns_client:
            client.close()
