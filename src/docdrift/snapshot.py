"""Resolve and extract a bounded local Git snapshot without running its code."""

from __future__ import annotations

import hashlib
import io
import re
import subprocess
import tarfile
from pathlib import Path, PurePosixPath


class SnapshotError(ValueError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_path(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or '..' in path.parts or '\\' in value or '\x00' in value or '.git' in path.parts:
        raise SnapshotError(f"Unsafe snapshot path: {value!r}")
    if str(path) != value.rstrip('/'):
        raise SnapshotError(f"Noncanonical snapshot path: {value!r}")
    return str(path)


def extract_archive(archive: bytes, destination: Path, *, max_archive_bytes: int = 25 * 1024 * 1024) -> dict[str, str]:
    if type(max_archive_bytes) is not int or not 1 <= max_archive_bytes <= 54 * 1024 * 1024:
        raise SnapshotError('Invalid archive byte limit')
    if destination.is_symlink() or any(parent.is_symlink() for parent in destination.parents):
        raise SnapshotError('Archive destination must not traverse symlinks')
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise SnapshotError('Archive destination must be a pristine directory')
    if len(archive) > max_archive_bytes:
        raise SnapshotError('Archive exceeds its byte limit (25 MiB by default)')
    hashes: dict[str, str] = {}
    total = 0
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:') as stream:
        members = stream.getmembers()
        if len(members) > 2000:
            raise SnapshotError('Snapshot exceeds 2,000 entries')
        seen: set[str] = set()
        for member in members:
            name = safe_path(member.name)
            if name in seen:
                raise SnapshotError(f'Duplicate archive path: {name}')
            seen.add(name)
            if not member.isfile() and not member.isdir():
                raise SnapshotError(f'Links and special files are unsupported: {name}')
            total += member.size
            if total > 50 * 1024 * 1024:
                raise SnapshotError('Extracted snapshot exceeds 50 MiB')
            if member.isfile():
                source = stream.extractfile(member)
                assert source is not None
                if source.read(128).startswith(b'version https://git-lfs.github.com/spec/v1'):
                    raise SnapshotError(f'LFS pointer is unsupported: {name}')
        destination.mkdir(parents=True, exist_ok=True)
        for member in members:
            name = safe_path(member.name)
            target = destination / name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            source = stream.extractfile(member)
            assert source is not None
            content = source.read()
            if content.startswith(b'version https://git-lfs.github.com/spec/v1'):
                raise SnapshotError(f'LFS pointer is unsupported: {name}')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            target.chmod(0o644)
            hashes[name] = sha256(content)
    return hashes


def resolve_local(repository: Path, ref: str, destination: Path) -> dict:
    repository = repository.resolve(strict=True)
    if ref.startswith('-'):
        raise SnapshotError('A revision cannot start with a dash')
    base = ['git', '-c', 'core.hooksPath=/dev/null', '-C', str(repository)]
    try:
        commit = subprocess.run(base + ['rev-parse', '--verify', f'{ref}^{{commit}}'], capture_output=True, text=True, check=True).stdout.strip()
        if not re.fullmatch(r'[0-9a-f]{40}', commit):
            raise SnapshotError('Expected a full SHA-1 Git commit')
        tree = subprocess.run(base + ['ls-tree', '-r', commit], capture_output=True, text=True, check=True).stdout
        if any(line.startswith('160000 ') for line in tree.splitlines()):
            raise SnapshotError('Submodules are unsupported')
        process = subprocess.Popen(base + ['archive', '--format=tar', commit], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        chunks: list[bytes] = []
        size = 0
        assert process.stdout is not None
        try:
            while chunk := process.stdout.read(65536):
                size += len(chunk)
                if size > 25 * 1024 * 1024:
                    process.kill()
                    raise SnapshotError('Archive exceeds 25 MiB')
                chunks.append(chunk)
        finally:
            process.stdout.close()
            return_code = process.wait()
        if return_code:
            raise SnapshotError('git archive failed')
        archive = b''.join(chunks)
        destination.mkdir(parents=True, exist_ok=False)
        files = extract_archive(archive, destination)
        licenses = [name for name in files if PurePosixPath(name).name.lower().startswith(('license', 'copying'))]
        return {'kind': 'local_git', 'origin': str(repository), 'commit': commit, 'archive_sha256': sha256(archive), 'files': files, 'license_files': licenses}
    except subprocess.CalledProcessError as exc:
        raise SnapshotError('Could not resolve the local Git revision') from exc


def file_hashes(root: Path) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): sha256(path.read_bytes()) for path in sorted(root.rglob('*')) if path.is_file()}
