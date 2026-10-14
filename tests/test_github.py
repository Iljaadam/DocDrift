"""Anonymous public snapshot contracts using mocked HTTP and owned tar data."""

import gzip
import hashlib
import io
import json
import tarfile

import httpx
import pytest

from docdrift import github
from docdrift.github import resolve_public_github
from docdrift.snapshot import SnapshotError


COMMIT = "a" * 40
TREE = "b" * 40
ROOT = "owner-demo-aaaaaaa"
FILES = {"README.md": b"Owned snapshot documentation.\n", "LICENSE": b"MIT owned fixture.\n", "package.py": b"raise RuntimeError('must never execute')\n"}


def _blob(content):
    return hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()


def _tree(files=FILES):
    directories = set()
    for path in files:
        parts = path.split("/")
        directories.update("/".join(parts[:index]) for index in range(1, len(parts)))
    entries = [{"path": path, "mode": "040000", "type": "tree", "sha": TREE} for path in sorted(directories)]
    entries.extend({"path": path, "mode": "100644", "type": "blob", "sha": _blob(content), "size": len(content)} for path, content in files.items())
    return {"sha": TREE, "truncated": False, "tree": entries}


def _tar(files=FILES, *, extra=(), root=ROOT):
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w", format=tarfile.PAX_FORMAT) as archive:
        top = tarfile.TarInfo(root)
        top.type = tarfile.DIRTYPE
        archive.addfile(top)
        directories = set()
        for path in files:
            parts = path.split("/")
            directories.update("/".join(parts[:index]) for index in range(1, len(parts)))
        for path in sorted(directories):
            member = tarfile.TarInfo(f"{root}/{path}")
            member.type = tarfile.DIRTYPE
            archive.addfile(member)
        for path, content in files.items():
            member = tarfile.TarInfo(f"{root}/{path}")
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
        for member, content in extra:
            archive.addfile(member, io.BytesIO(content) if member.isfile() else None)
    return gzip.compress(data.getvalue(), mtime=0)


def _response(content, *, status=200, headers=None):
    if isinstance(content, (dict, list)):
        content = json.dumps(content).encode()
    return httpx.Response(status, headers=headers, stream=httpx.ByteStream(content))


class PublicFixture:
    def __init__(self, *, tree=None, archive=None, commit=None, location=None):
        self.tree = _tree() if tree is None else tree
        self.archive = _tar() if archive is None else archive
        self.commit = {"sha": COMMIT, "commit": {"tree": {"sha": TREE}}} if commit is None else commit
        self.location = location or f"https://codeload.github.com/owner/demo/legacy.tar.gz/{COMMIT}"
        self.requests = []
        self.archive_headers = {}

    def __call__(self, request):
        self.requests.append(request)
        path = request.url.path
        if request.url.host == "api.github.com" and path.startswith("/repos/owner/demo/commits/"):
            return _response(self.commit)
        if path == f"/repos/owner/demo/git/trees/{TREE}":
            assert request.url.query == b"recursive=1"
            return _response(self.tree)
        if path == f"/repos/owner/demo/tarball/{COMMIT}":
            return _response(b"", status=302, headers={"Location": self.location})
        if request.url.host == "codeload.github.com":
            return _response(self.archive, headers=self.archive_headers)
        raise AssertionError(f"Unexpected mocked request: {request.url}")


def _resolve(tmp_path, fixture, **kwargs):
    with httpx.Client(transport=httpx.MockTransport(fixture)) as client:
        return resolve_public_github("owner/demo", "main", tmp_path / "snapshot", client=client, **kwargs)


@pytest.mark.parametrize("repository", ["owner/demo", "https://github.com/owner/demo"])
def test_public_ref_is_resolved_once_and_archive_is_pinned(repository, tmp_path):
    fixture = PublicFixture()
    with httpx.Client(transport=httpx.MockTransport(fixture)) as client:
        provenance = resolve_public_github(repository, "main", tmp_path / "snapshot", client=client)
    assert provenance["kind"] == "public_github"
    assert provenance["origin"] == "https://github.com/owner/demo"
    assert provenance["commit"] == COMMIT
    assert provenance["tree_sha"] == TREE
    assert provenance["archive_sha256"] == hashlib.sha256(fixture.archive).hexdigest()
    assert provenance["files"] == {path: hashlib.sha256(content).hexdigest() for path, content in FILES.items()}
    assert provenance["license_files"] == ["LICENSE"]
    assert sum("/commits/" in request.url.path for request in fixture.requests) == 1
    assert all("main" not in request.url.path for request in fixture.requests[1:])
    for path, content in FILES.items():
        assert (tmp_path / "snapshot" / path).read_bytes() == content
        assert (tmp_path / "snapshot" / path).stat().st_mode & 0o777 == 0o644


def test_named_ref_with_slash_is_one_encoded_path_parameter(tmp_path):
    fixture = PublicFixture()
    with httpx.Client(transport=httpx.MockTransport(fixture)) as client:
        resolve_public_github("owner/demo", "heads/feature/topic", tmp_path / "snapshot", client=client)
    assert fixture.requests[0].url.raw_path.endswith(b"/commits/heads%2Ffeature%2Ftopic")


def test_supports_preloaded_responses_from_injected_mock_transport(tmp_path):
    fixture = PublicFixture()

    def preloaded(request):
        response = fixture(request)
        response.read()
        return response

    with httpx.Client(transport=httpx.MockTransport(preloaded)) as client:
        result = resolve_public_github("owner/demo", "main", tmp_path / "snapshot", client=client)
    assert result["commit"] == COMMIT


def test_client_credentials_cookies_and_default_headers_are_never_sent(tmp_path):
    fixture = PublicFixture()
    with httpx.Client(transport=httpx.MockTransport(fixture), auth=("forbidden", "forbidden"), headers={"Authorization": "forbidden", "X-Credential": "forbidden"}, cookies={"session": "forbidden"}, follow_redirects=True) as client:
        resolve_public_github("owner/demo", "main", tmp_path / "snapshot", client=client)
    assert len(fixture.requests) == 4
    for request in fixture.requests:
        assert "authorization" not in request.headers
        assert "cookie" not in request.headers
        assert "x-credential" not in request.headers
        assert request.headers["accept-encoding"] == "identity"
        assert request.extensions["timeout"]["read"] <= 10


@pytest.mark.parametrize("repository", ["http://github.com/owner/demo", "https://user:pass@github.com/owner/demo", "https://github.com:443/owner/demo", "https://www.github.com/owner/demo", "https://example.com/owner/demo", "https://github.com/owner/demo?token=forbidden", "https://github.com/owner/demo#fragment", "https://github.com/owner/demo?", "https://github.com/owner/demo#", "https://github.com/owner/de\nmo", "https://github.com/owner/de\tmo", "https://github.com/owner/demo/", "https://github.com/owner/demo/tree/main", "../demo", "owner/../demo", "owner/demo%2Fother", "owner/demo.git", "owner/demo\\other", "-owner/demo", "owner-/demo", "owner_/demo", "owner--name/demo"])
def test_reject_noncanonical_repository_before_network(repository, tmp_path):
    fixture = PublicFixture()
    with httpx.Client(transport=httpx.MockTransport(fixture)) as client:
        with pytest.raises(SnapshotError):
            resolve_public_github(repository, "main", tmp_path / "snapshot", client=client)
    assert not fixture.requests


@pytest.mark.parametrize("ref", ["", "../main", "main/../evil", "%2e%2e", "main?token=x", "main#fragment", "main\0", "/main", "-main", "main//other", "main.", ".hidden", "heads/.hidden", "heads/name.lock"])
def test_reject_invalid_revision_before_network(ref, tmp_path):
    fixture = PublicFixture()
    with httpx.Client(transport=httpx.MockTransport(fixture)) as client:
        with pytest.raises(SnapshotError):
            resolve_public_github("owner/demo", ref, tmp_path / "snapshot", client=client)
    assert not fixture.requests


@pytest.mark.parametrize("commit", [{"sha": "short", "commit": {"tree": {"sha": TREE}}}, {"sha": COMMIT}, {"sha": COMMIT, "commit": []}, {"sha": COMMIT, "commit": {"tree": {"sha": "bad"}}}])
def test_require_full_commit_and_tree_identity(commit, tmp_path):
    fixture = PublicFixture(commit=commit)
    with pytest.raises(SnapshotError, match="full commit and tree"):
        _resolve(tmp_path, fixture)
    assert len(fixture.requests) == 1


def test_explicit_commit_cannot_resolve_to_another_sha(tmp_path):
    fixture = PublicFixture()
    with httpx.Client(transport=httpx.MockTransport(fixture)) as client:
        with pytest.raises(SnapshotError, match="different commit"):
            resolve_public_github("owner/demo", "c" * 40, tmp_path / "snapshot", client=client)


@pytest.mark.parametrize("truncated", [True, None, "false"])
def test_reject_incomplete_submodule_scan(truncated, tmp_path):
    tree = _tree()
    tree["truncated"] = truncated
    fixture = PublicFixture(tree=tree)
    with pytest.raises(SnapshotError, match="untruncated"):
        _resolve(tmp_path, fixture)
    assert len(fixture.requests) == 2


@pytest.mark.parametrize("mode,kind", [("160000", "commit"), ("120000", "blob"), ("100644", "commit"), ("077777", "blob")])
def test_reject_submodules_symlinks_or_invalid_tree_modes(mode, kind, tmp_path):
    tree = _tree()
    tree["tree"][0].update(mode=mode, type=kind)
    fixture = PublicFixture(tree=tree)
    with pytest.raises(SnapshotError):
        _resolve(tmp_path, fixture)
    assert len(fixture.requests) == 2
    assert not (tmp_path / "snapshot").exists()


def test_git_tree_bounds_entry_count_before_archive_request(tmp_path):
    tree = _tree()
    tree["tree"] = [{"path": f"file-{index}", "mode": "100644", "type": "blob", "size": 0, "sha": _blob(b"")} for index in range(2001)]
    fixture = PublicFixture(tree=tree)
    with pytest.raises(SnapshotError, match="2,000"):
        _resolve(tmp_path, fixture)
    assert len(fixture.requests) == 2


def test_git_tree_bounds_extracted_size_before_archive_request(tmp_path):
    tree = _tree()
    tree["tree"][0]["size"] = 50 * 1024 * 1024 + 1
    fixture = PublicFixture(tree=tree)
    with pytest.raises(SnapshotError, match="50 MiB"):
        _resolve(tmp_path, fixture)
    assert len(fixture.requests) == 2


@pytest.mark.parametrize("path", ["../escape", ".", "bad\\path", "bad\0path", "bad\npath", "x" * 256])
def test_git_tree_path_validation_precedes_archive_download(path, tmp_path):
    tree = _tree()
    tree["tree"][0]["path"] = path
    fixture = PublicFixture(tree=tree)
    with pytest.raises(SnapshotError):
        _resolve(tmp_path, fixture)
    assert len(fixture.requests) == 2


def test_encoded_traversal_in_redirect_is_rejected(tmp_path):
    fixture = PublicFixture(location=f"https://codeload.github.com/owner/demo/%2e%2e/{COMMIT}")
    with pytest.raises(SnapshotError, match="Traversal"):
        _resolve(tmp_path, fixture)
    assert len(fixture.requests) == 3


@pytest.mark.parametrize("location", ["http://codeload.github.com/owner/demo/legacy.tar.gz/" + COMMIT, "https://example.com/archive/" + COMMIT, "https://user:pass@codeload.github.com/owner/demo/legacy.tar.gz/" + COMMIT, "https://codeload.github.com:443/owner/demo/legacy.tar.gz/" + COMMIT, "https://codeload.github.com/owner/demo/legacy.tar.gz/main", "https://codeload.github.com/owner/demo/legacy.tar.gz/" + COMMIT + "?token=forbidden"])
def test_redirects_cannot_escape_host_https_or_commit_constraints(location, tmp_path):
    fixture = PublicFixture(location=location)
    with pytest.raises(SnapshotError):
        _resolve(tmp_path, fixture)
    assert len(fixture.requests) == 3


def test_redirect_loop_is_bounded(tmp_path):
    fixture = PublicFixture()

    def redirect_forever(request):
        if request.url.host == "codeload.github.com":
            fixture.requests.append(request)
            return _response(b"", status=302, headers={"Location": str(request.url)})
        return fixture(request)

    with httpx.Client(transport=httpx.MockTransport(redirect_forever)) as client:
        with pytest.raises(SnapshotError, match="redirect limit"):
            resolve_public_github("owner/demo", "main", tmp_path / "snapshot", client=client)
    assert len(fixture.requests) == 6


@pytest.mark.parametrize("status", [403, 404, 429, 503])
def test_public_failure_does_not_login_retry_or_write(status, tmp_path):
    requests = []

    def failure(request):
        requests.append(request)
        return _response(b"forbidden response data", status=status)

    with httpx.Client(transport=httpx.MockTransport(failure)) as client:
        with pytest.raises(SnapshotError, match=f"HTTP {status}"):
            resolve_public_github("owner/demo", "main", tmp_path / "snapshot", client=client)
    assert len(requests) == 1
    assert not (tmp_path / "snapshot").exists()


def test_network_timeout_is_not_retried(tmp_path):
    requests = []

    def timeout(request):
        requests.append(request)
        raise httpx.ReadTimeout("owned mock timeout", request=request)

    with httpx.Client(transport=httpx.MockTransport(timeout)) as client:
        with pytest.raises(SnapshotError, match="timed out"):
            resolve_public_github("owner/demo", "main", tmp_path / "snapshot", client=client)
    assert len(requests) == 1


def test_deadline_covers_all_requests_instead_of_resetting_each_phase(tmp_path, monkeypatch):
    clock = [0.0]
    fixture = PublicFixture()
    monkeypatch.setattr(github.time, "monotonic", lambda: clock[0])

    def delayed(request):
        clock[0] += 23.0
        return fixture(request)

    with httpx.Client(transport=httpx.MockTransport(delayed)) as client:
        with pytest.raises(SnapshotError, match="deadline"):
            resolve_public_github("owner/demo", "main", tmp_path / "snapshot", client=client)
    assert len(fixture.requests) == 3
    assert not (tmp_path / "snapshot").exists()


def test_download_stream_limit_is_independent_of_content_length(tmp_path, monkeypatch):
    monkeypatch.setattr(github, "_DOWNLOAD_LIMIT", 64)
    fixture = PublicFixture()
    with pytest.raises(SnapshotError, match="byte limit"):
        _resolve(tmp_path, fixture)
    assert not (tmp_path / "snapshot").exists()


def test_oversized_content_length_rejected_before_body(tmp_path):
    fixture = PublicFixture()
    fixture.archive_headers["Content-Length"] = str(25 * 1024 * 1024 + 1)
    with pytest.raises(SnapshotError, match="byte limit"):
        _resolve(tmp_path, fixture)


def test_http_decompression_is_never_implicit(tmp_path):
    fixture = PublicFixture()
    fixture.archive_headers["Content-Encoding"] = "gzip"
    with pytest.raises(SnapshotError, match="HTTP content encoding"):
        _resolve(tmp_path, fixture)


def test_gzip_expansion_is_bounded_before_tar_parsing(tmp_path, monkeypatch):
    monkeypatch.setattr(github, "_TAR_LIMIT", 1024)
    fixture = PublicFixture(archive=gzip.compress(b"\0" * 2048))
    with pytest.raises(SnapshotError, match="expansion limit"):
        _resolve(tmp_path, fixture)


def test_declared_huge_pax_payload_rejected_before_tarfile_allocation(tmp_path):
    member = tarfile.TarInfo("pax")
    member.type = tarfile.XHDTYPE
    member.size = 1024 * 1024 * 1024
    fixture = PublicFixture(archive=gzip.compress(member.tobuf() + b"\0" * 1024))
    with pytest.raises(SnapshotError, match="expansion limit"):
        _resolve(tmp_path, fixture)


def test_extended_header_payload_has_its_own_small_limit(tmp_path):
    member = tarfile.TarInfo("pax")
    member.type = tarfile.XHDTYPE
    member.size = 65537
    payload = b"x" * member.size
    padding = b"\0" * ((-member.size) % 512 + 1024)
    fixture = PublicFixture(archive=gzip.compress(member.tobuf() + payload + padding))
    with pytest.raises(SnapshotError, match="extended metadata"):
        _resolve(tmp_path, fixture)


def test_sparse_pax_metadata_is_rejected_before_sparse_map_allocation(tmp_path):
    member = tarfile.TarInfo(ROOT + "/sparse")
    member.pax_headers = {"GNU.sparse.map": "0,0", "GNU.sparse.size": "1"}
    fixture = PublicFixture(archive=_tar(extra=[(member, b"")]))
    with pytest.raises(SnapshotError, match="sparse files"):
        _resolve(tmp_path, fixture)


@pytest.mark.parametrize("name", ["../escape", "/absolute", ROOT + "/../escape", ROOT + "/.git/config"])
def test_unsafe_archive_paths_are_rejected_before_destination_writes(name, tmp_path):
    member = tarfile.TarInfo(name)
    member.size = 1
    fixture = PublicFixture(archive=_tar(extra=[(member, b"x")]))
    with pytest.raises(SnapshotError):
        _resolve(tmp_path, fixture)
    assert not (tmp_path / "snapshot").exists()
    assert not (tmp_path / "escape").exists()


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE])
def test_archive_links_and_special_files_rejected_before_writes(kind, tmp_path):
    member = tarfile.TarInfo(ROOT + "/link")
    member.type = kind
    member.linkname = "../../escape"
    fixture = PublicFixture(archive=_tar(extra=[(member, b"")]))
    with pytest.raises(SnapshotError, match="unsupported"):
        _resolve(tmp_path, fixture)
    assert not (tmp_path / "snapshot").exists()


def test_pax_overridden_traversal_path_is_validated(tmp_path):
    member = tarfile.TarInfo(ROOT + "/safe")
    member.pax_headers = {"path": "../escape"}
    member.size = 1
    fixture = PublicFixture(archive=_tar(extra=[(member, b"x")]))
    with pytest.raises(SnapshotError):
        _resolve(tmp_path, fixture)
    assert not (tmp_path / "escape").exists()


def test_reject_multiple_archive_top_directories(tmp_path):
    member = tarfile.TarInfo("another/README.md")
    member.size = 1
    fixture = PublicFixture(archive=_tar(extra=[(member, b"x")]))
    with pytest.raises(SnapshotError, match="consistent top directory"):
        _resolve(tmp_path, fixture)


def test_duplicate_archive_files_are_rejected(tmp_path):
    member = tarfile.TarInfo(ROOT + "/README.md")
    member.size = len(FILES["README.md"])
    fixture = PublicFixture(archive=_tar(extra=[(member, FILES["README.md"])]))
    with pytest.raises(SnapshotError, match="Duplicate"):
        _resolve(tmp_path, fixture)


def test_matching_lfs_pointer_is_still_unsupported(tmp_path):
    files = {"README.md": b"version https://git-lfs.github.com/spec/v1\noid sha256:deadbeef\nsize 10\n"}
    fixture = PublicFixture(tree=_tree(files), archive=_tar(files))
    with pytest.raises(SnapshotError, match="LFS"):
        _resolve(tmp_path, fixture)


def test_archive_bytes_must_match_pinned_blob_not_just_filename_and_size(tmp_path):
    files = dict(FILES)
    files["README.md"] = b"X" * len(files["README.md"])
    fixture = PublicFixture(archive=_tar(files))
    with pytest.raises(SnapshotError, match="blob does not match"):
        _resolve(tmp_path, fixture)
    assert not (tmp_path / "snapshot").exists()


def test_archive_cannot_silently_omit_export_ignored_files(tmp_path):
    files = {path: content for path, content in FILES.items() if path != "LICENSE"}
    fixture = PublicFixture(archive=_tar(files))
    with pytest.raises(SnapshotError, match="omits files"):
        _resolve(tmp_path, fixture)


def test_archive_cannot_add_unlisted_files(tmp_path):
    files = {**FILES, "unexpected.py": b"raise RuntimeError('must not execute')\n"}
    fixture = PublicFixture(archive=_tar(files))
    with pytest.raises(SnapshotError, match="inventory"):
        _resolve(tmp_path, fixture)


def test_public_snapshot_supports_verified_nested_files(tmp_path):
    files = {"docs/guide.md": b"# Owned nested example\n", "COPYING": b"MIT\n"}
    fixture = PublicFixture(tree=_tree(files), archive=_tar(files))
    provenance = _resolve(tmp_path, fixture)
    assert set(provenance["files"]) == set(files)
    assert provenance["license_files"] == ["COPYING"]


def test_valid_long_unicode_path_uses_pax_metadata(tmp_path):
    files = {"docs/" + "é" * 80 + ".md": b"# Owned unicode path\n"}
    fixture = PublicFixture(tree=_tree(files), archive=_tar(files))
    result = _resolve(tmp_path, fixture)
    assert set(result["files"]) == set(files)


@pytest.mark.parametrize("destination_type", ["existing", "symlink", "parent_symlink"])
def test_unsafe_existing_destinations_rejected_before_network(destination_type, tmp_path):
    fixture = PublicFixture()
    destination = tmp_path / "snapshot"
    if destination_type == "existing":
        destination.mkdir()
    elif destination_type == "symlink":
        destination.symlink_to(tmp_path, target_is_directory=True)
    else:
        linked = tmp_path / "linked"
        linked.symlink_to(tmp_path, target_is_directory=True)
        destination = linked / "snapshot"
    with httpx.Client(transport=httpx.MockTransport(fixture)) as client:
        with pytest.raises(SnapshotError, match="destination"):
            resolve_public_github("owner/demo", "main", destination, client=client)
    assert not fixture.requests
