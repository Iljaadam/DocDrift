"""Bound snapshot inputs and pin local Git revisions without target execution."""

import hashlib
import io
import subprocess
import tarfile

import pytest

from docdrift import snapshot
from docdrift.snapshot import SnapshotError, extract_archive, resolve_local, safe_path


def _archive(entries):
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for member, content in entries:
            archive.addfile(member, io.BytesIO(content) if member.isfile() else None)
    return data.getvalue()


def _file(name, content=b""):
    member = tarfile.TarInfo(name)
    member.size = len(content)
    return member, content


@pytest.mark.parametrize("path", ["../escape", "/absolute", "nested/../../escape", "nested\\escape", ".git/config", "nested/.git/config", "nested//file", "./file"])
def test_reject_noncanonical_or_escaping_paths(path):
    with pytest.raises(SnapshotError):
        safe_path(path)


def test_validate_whole_archive_before_writing_traversal(tmp_path):
    destination = tmp_path / "snapshot"
    with pytest.raises(SnapshotError):
        extract_archive(_archive([_file("safe.txt", b"safe"), _file("../escape.txt", b"escape")]), destination)
    assert not (destination / "safe.txt").exists()
    assert not (tmp_path / "escape.txt").exists()


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE, tarfile.BLKTYPE])
def test_reject_archive_links_and_special_files(kind, tmp_path):
    member = tarfile.TarInfo("unsafe")
    member.type = kind
    member.linkname = "../outside"
    with pytest.raises(SnapshotError, match="unsupported"):
        extract_archive(_archive([(member, b"")]), tmp_path / "snapshot")


def test_reject_preexisting_destination_symlink_escape(tmp_path):
    destination = tmp_path / "snapshot"
    destination.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (destination / "nested").symlink_to(outside, target_is_directory=True)
    with pytest.raises(SnapshotError):
        extract_archive(_archive([_file("nested/payload.txt", b"escaped")]), destination)
    assert not (outside / "payload.txt").exists()


def test_reject_destination_root_symlink(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    destination = tmp_path / "snapshot"
    destination.symlink_to(outside, target_is_directory=True)
    with pytest.raises(SnapshotError):
        extract_archive(_archive([_file("payload.txt", b"escaped")]), destination)
    assert not (outside / "payload.txt").exists()


def test_reject_lfs_pointer(tmp_path):
    pointer = b"version https://git-lfs.github.com/spec/v1\noid sha256:deadbeef\nsize 100\n"
    with pytest.raises(SnapshotError, match="LFS"):
        extract_archive(_archive([_file("large.bin", pointer)]), tmp_path / "snapshot")


def test_reject_duplicate_archive_paths(tmp_path):
    with pytest.raises(SnapshotError, match="Duplicate"):
        extract_archive(_archive([_file("same", b"one"), _file("same", b"two")]), tmp_path / "snapshot")


def test_enforce_download_limit_before_parsing(tmp_path):
    with pytest.raises(SnapshotError, match="25 MiB"):
        extract_archive(b"x" * (25 * 1024 * 1024 + 1), tmp_path / "snapshot")


def test_enforce_extracted_limit_on_sparse_member(tmp_path):
    # A real GNU sparse tar represents a >50 MiB logical file in a tiny archive.
    member, content = _file("huge.txt")
    member.pax_headers = {"GNU.sparse.map": "0,0", "GNU.sparse.size": str(50 * 1024 * 1024 + 1)}
    with pytest.raises(SnapshotError, match="50 MiB"):
        extract_archive(_archive([(member, content)]), tmp_path / "snapshot")
    assert not (tmp_path / "snapshot" / "huge.txt").exists()


def test_enforce_file_count_limit(tmp_path):
    with pytest.raises(SnapshotError, match="2,000"):
        extract_archive(_archive([_file(f"file-{index}") for index in range(2001)]), tmp_path / "snapshot")


def test_extract_records_exact_hashes_and_regular_modes(tmp_path):
    source = b"raise RuntimeError('target code must not execute')\n"
    member, content = _file("package.py", source)
    member.mode = 0o777
    destination = tmp_path / "snapshot"
    hashes = extract_archive(_archive([(member, content)]), destination)
    assert hashes == {"package.py": hashlib.sha256(source).hexdigest()}
    assert (destination / "package.py").read_bytes() == source
    assert (destination / "package.py").stat().st_mode & 0o777 == 0o644


def _git(repository, *arguments):
    return subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "-C", str(repository), *arguments],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


@pytest.fixture
def local_repository(tmp_path):
    repository = tmp_path / "source"
    repository.mkdir()
    _git(repository, "init", "-b", "main")
    _git(repository, "config", "user.name", "DocDrift fixture test")
    _git(repository, "config", "user.email", "fixture@example.invalid")
    (repository / "README.md").write_text("First pinned documentation.\n")
    (repository / "LICENSE").write_text("Owned test license.\n")
    (repository / "package.py").write_text("raise RuntimeError('must not execute')\n")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "Owned initial snapshot")
    return repository


def test_pin_full_commit_before_mutable_branch_moves(local_repository, tmp_path, monkeypatch):
    repository = local_repository
    first = _git(repository, "rev-parse", "HEAD")
    first_content = (repository / "README.md").read_bytes()
    (repository / "README.md").write_text("Second commit documentation.\n")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "Second owned snapshot")
    second = _git(repository, "rev-parse", "HEAD")
    _git(repository, "update-ref", "refs/heads/main", first)
    original_run = snapshot.subprocess.run

    def move_after_resolution(arguments, **kwargs):
        result = original_run(arguments, **kwargs)
        if "rev-parse" in arguments:
            original_run(["git", "-C", str(repository), "update-ref", "refs/heads/main", second], check=True, capture_output=True)
        return result

    monkeypatch.setattr(snapshot.subprocess, "run", move_after_resolution)
    destination = tmp_path / "snapshot"
    provenance = resolve_local(repository, "main", destination)
    assert provenance["commit"] == first
    assert (destination / "README.md").read_bytes() == first_content
    assert provenance["license_files"] == ["LICENSE"]
    assert provenance["files"]["README.md"] == hashlib.sha256(first_content).hexdigest()


def test_snapshot_ignores_dirty_working_tree(local_repository, tmp_path):
    original = (local_repository / "README.md").read_bytes()
    (local_repository / "README.md").write_text("Uncommitted documentation.\n")
    (local_repository / "untracked.py").write_text("raise RuntimeError('must not execute')\n")
    destination = tmp_path / "snapshot"
    provenance = resolve_local(local_repository, "HEAD", destination)
    assert (destination / "README.md").read_bytes() == original
    assert "untracked.py" not in provenance["files"]
    assert len(provenance["commit"]) == 40


def test_reject_submodule_tree_entry(local_repository, tmp_path):
    commit = _git(local_repository, "rev-parse", "HEAD")
    _git(local_repository, "update-index", "--add", "--cacheinfo", f"160000,{commit},nested-module")
    _git(local_repository, "commit", "-m", "Owned unsupported submodule")
    with pytest.raises(SnapshotError, match="Submodules"):
        resolve_local(local_repository, "HEAD", tmp_path / "snapshot")


def test_reject_option_like_revision(local_repository, tmp_path):
    with pytest.raises(SnapshotError, match="dash"):
        resolve_local(local_repository, "--help", tmp_path / "snapshot")
