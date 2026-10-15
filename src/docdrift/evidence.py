"""Bounded, offline integrity checks for exported evidence ZIPs.

The bundled manifest is not signed or trusted independently. Matching its
hashes does not authenticate the bundle or substantiate its recorded verdicts.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import stat
import struct
import zipfile
import zlib
from pathlib import Path, PurePosixPath


MAX_ARCHIVE_BYTES = 25 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 20 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_MEMBERS = 2500
_CHUNK_BYTES = 64 * 1024
_END = struct.Struct('<4s4H2IH')
_CENTRAL = struct.Struct('<4s6H3I5H2I')
_LOCAL = struct.Struct('<4s5H3I2H')


class EvidenceError(ValueError):
    """The archive cannot establish the requested limited integrity claim."""


def _safe_name(name: str) -> str:
    path = PurePosixPath(name)
    if (not name or len(name) > 4096 or path.is_absolute() or str(path) != name
            or '..' in path.parts or ':' in name or '\\' in name
            or any(ord(char) < 32 or ord(char) == 127 for char in name)
            or name in {'.', '..'}):
        raise EvidenceError('Unsafe or noncanonical ZIP member path')
    return name


def _central_directory(data: bytes) -> int:
    """Bound metadata before ZipFile builds its member list.

    Counting only ZipFile.infolist() would first allocate attacker-supplied
    entries. Check the actual directory count as well as the declared count.
    Small DocDrift exports need neither ZIP64 nor multipart ZIP support.
    """
    offset = data.rfind(b'PK\x05\x06', max(0, len(data) - 65535 - _END.size))
    if offset < 0 or offset + _END.size > len(data):
        raise EvidenceError('Invalid ZIP end record')
    _, disk, start_disk, disk_count, count, size, start, comment_size = _END.unpack_from(data, offset)
    if offset + _END.size + comment_size != len(data):
        raise EvidenceError('Invalid ZIP end record or trailing data')
    if disk or start_disk or disk_count != count:
        raise EvidenceError('Multipart ZIP archives are unsupported')
    if count == 0xffff or size == 0xffffffff or start == 0xffffffff:
        raise EvidenceError('ZIP64 evidence archives are unsupported')
    if count > MAX_MEMBERS:
        raise EvidenceError('Evidence exceeds the 2,500-member limit')
    if start + size != offset:
        raise EvidenceError('Invalid ZIP central directory bounds')
    cursor, actual_count, total = start, 0, 0
    while cursor < offset:
        if cursor + _CENTRAL.size > offset:
            raise EvidenceError('Truncated ZIP central directory')
        fields = _CENTRAL.unpack_from(data, cursor)
        if fields[0] != b'PK\x01\x02':
            raise EvidenceError('Invalid ZIP central directory entry')
        actual_count += 1
        if actual_count > MAX_MEMBERS:
            raise EvidenceError('Evidence exceeds the 2,500-member limit')
        compressed, uncompressed = fields[8:10]
        if compressed == 0xffffffff or uncompressed == 0xffffffff or fields[16] == 0xffffffff:
            raise EvidenceError('ZIP64 evidence archives are unsupported')
        total += uncompressed
        if total > MAX_UNCOMPRESSED_BYTES:
            raise EvidenceError('Evidence exceeds the 20 MiB uncompressed limit')
        if fields[13]:
            raise EvidenceError('Multipart ZIP archives are unsupported')
        cursor += _CENTRAL.size + sum(fields[10:13])
        if cursor > offset:
            raise EvidenceError('Truncated ZIP central directory entry')
    if actual_count != count or cursor != offset:
        raise EvidenceError('ZIP member count does not match its central directory')
    return start


def _validate_member(info: zipfile.ZipInfo, data: bytes, central_start: int) -> str:
    name = _safe_name(info.orig_filename)
    if name != info.filename:
        raise EvidenceError('Ambiguous ZIP member filename')
    file_type = stat.S_IFMT(info.external_attr >> 16)
    if info.is_dir() or info.external_attr & 0x18 or file_type not in {0, stat.S_IFREG}:
        raise EvidenceError('ZIP links, directories, and special files are unsupported')
    if info.flag_bits & 0x41:
        raise EvidenceError('Encrypted ZIP members are unsupported')
    if info.flag_bits & 8:
        raise EvidenceError('ZIP data descriptors are unsupported')
    if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
        raise EvidenceError('Unsupported evidence compression method')
    if info.compress_type == zipfile.ZIP_STORED and info.compress_size != info.file_size:
        raise EvidenceError('Stored ZIP member compressed and uncompressed sizes disagree')
    if info.file_size < 0 or info.compress_size < 0 or info.header_offset < 0:
        raise EvidenceError('Invalid ZIP member bounds')
    if info.header_offset + _LOCAL.size > central_start:
        raise EvidenceError('Invalid ZIP local header bounds')
    fields = _LOCAL.unpack_from(data, info.header_offset)
    if fields[0] != b'PK\x03\x04':
        raise EvidenceError('Invalid ZIP local header')
    if fields[2] & 0x41:
        raise EvidenceError('Encrypted ZIP members are unsupported')
    if fields[2] != info.flag_bits or fields[3] != info.compress_type:
        raise EvidenceError('ZIP local and central headers disagree')
    if fields[6:9] != (info.CRC, info.compress_size, info.file_size):
        raise EvidenceError('ZIP local and central CRC or sizes disagree')
    body = info.header_offset + _LOCAL.size + fields[9] + fields[10]
    if body + info.compress_size > central_start:
        raise EvidenceError('ZIP member extends beyond its data region')
    return name



def _member_chunks(archive: zipfile.ZipFile, info: zipfile.ZipInfo, data: bytes):
    """Inflate with an explicit output bound and require the entire stream.

    ZipExtFile truncates output to the central-directory file_size, which can
    conceal extra expanded bytes when an attacker also forges the prefix CRC.
    Its unbounded read can allocate that hidden output before truncating it.
    Use ZipFile only for its local-name and overlapping-entry checks.
    """
    with archive.open(info):
        pass
    fields = _LOCAL.unpack_from(data, info.header_offset)
    body = info.header_offset + _LOCAL.size + fields[9] + fields[10]
    end = body + info.compress_size
    decoder = zlib.decompressobj(-15) if info.compress_type == zipfile.ZIP_DEFLATED else None
    count, crc = 0, 0
    for start in range(body, end, _CHUNK_BYTES):
        pending = data[start:min(start + _CHUNK_BYTES, end)]
        while True:
            limit = min(_CHUNK_BYTES, info.file_size - count + 1)
            block = decoder.decompress(pending, limit) if decoder else pending
            count += len(block)
            if count > info.file_size:
                raise EvidenceError('ZIP member exceeds its declared uncompressed size')
            crc = zlib.crc32(block, crc)
            if block:
                yield block
            if decoder is None:
                break
            if decoder.unused_data:
                raise EvidenceError('ZIP member has extra compressed stream data')
            pending = decoder.unconsumed_tail
            if not pending and (decoder.eof or len(block) < limit):
                break
            # An empty call drains any buffered output after max_length was
            # reached without retaining raw input in unconsumed_tail.
    if decoder is not None and not decoder.eof:
        raise EvidenceError('ZIP member has an incomplete deflate stream')
    if count != info.file_size or crc != info.CRC:
        raise EvidenceError('ZIP member integrity check failed (CRC or size)')

def _manifest(content: bytes, member_names: set[str]) -> dict[str, str]:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise EvidenceError('Duplicate manifest JSON key')
            result[key] = value
        return result

    def invalid_number(value):
        raise EvidenceError('Non-finite manifest JSON number')

    try:
        manifest = json.loads(content.decode('utf-8'), object_pairs_hook=pairs, parse_constant=invalid_number)
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, EvidenceError):
            raise
        raise EvidenceError('Manifest is not valid strict UTF-8 JSON') from exc
    if not isinstance(manifest, dict) or set(manifest) != {'algorithm', 'files'}:
        raise EvidenceError('Manifest must contain only algorithm and files')
    if manifest['algorithm'] != 'sha256' or not isinstance(manifest['files'], dict):
        raise EvidenceError('Manifest requires sha256 and a file-hash object')
    files = manifest['files']
    for name, digest in files.items():
        _safe_name(name)
        if not isinstance(digest, str) or re.fullmatch(r'[0-9a-f]{64}', digest) is None:
            raise EvidenceError('Manifest contains an invalid SHA-256 digest')
    if set(files) != member_names - {'manifest.json'}:
        raise EvidenceError('Manifest does not exactly cover the evidence members')
    if 'report.json' not in files:
        raise EvidenceError('Evidence requires a listed report.json')
    return files


def verify_evidence(archive_path: Path) -> dict:
    """Check ZIP structure and manifest hashes, without extraction or execution.

    ``files_checked`` excludes manifest.json itself. The returned archive hash
    identifies the exact bytes inspected, including the unsigned manifest.
    Saved report contents are never executed, interpreted, or endorsed. Only
    regular stored/deflated entries without data descriptors are supported,
    matching current exports; ZIP64 and multipart archives are unsupported.
    """
    path = Path(archive_path)
    try:
        if not stat.S_ISREG(path.stat().st_mode):
            raise EvidenceError('Evidence archive must be a regular file')
        with path.open('rb') as source:
            data = source.read(MAX_ARCHIVE_BYTES + 1)
    except OSError as exc:
        raise EvidenceError('Could not read evidence archive') from exc
    if len(data) > MAX_ARCHIVE_BYTES:
        raise EvidenceError('Evidence exceeds the 25 MiB archive limit')
    central_start = _central_directory(data)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members: dict[str, zipfile.ZipInfo] = {}
            for info in archive.infolist():
                name = _validate_member(info, data, central_start)
                if name in members:
                    raise EvidenceError('Duplicate ZIP member path')
                members[name] = info
            if 'manifest.json' not in members:
                raise EvidenceError('Evidence requires manifest.json')
            if members['manifest.json'].file_size > MAX_MANIFEST_BYTES:
                raise EvidenceError('Manifest exceeds the 1 MiB limit')
            manifest_content = b''.join(_member_chunks(archive, members['manifest.json'], data))
            manifest = _manifest(manifest_content, set(members))
            actual_total = members['manifest.json'].file_size
            for name, expected in manifest.items():
                digest, count = hashlib.sha256(), 0
                for chunk in _member_chunks(archive, members[name], data):
                    count += len(chunk)
                    actual_total += len(chunk)
                    if actual_total > MAX_UNCOMPRESSED_BYTES:
                        raise EvidenceError('Evidence exceeds the allowed uncompressed size')
                    digest.update(chunk)
                if count != members[name].file_size:
                    raise EvidenceError('ZIP member size differs from the declared size')
                if digest.hexdigest() != expected:
                    raise EvidenceError(f'SHA-256 mismatch for {name}')
    except EvidenceError:
        raise
    except (zipfile.BadZipFile, zipfile.LargeZipFile, EOFError, RuntimeError, NotImplementedError, zlib.error, OSError, struct.error, UnicodeError, ValueError, OverflowError) as exc:
        raise EvidenceError('ZIP member integrity or compression check failed') from exc
    return {
        'kind': 'docdrift_evidence_integrity',
        'status': 'integrity_verified',
        'files_checked': len(manifest),
        'archive_sha256': hashlib.sha256(data).hexdigest(),
        'uncompressed_bytes': actual_total,
        'execution_attested': False,
        'authenticity_attested': False,
        'coverage_note': 'Checks member bytes against the bundled unsigned SHA-256 manifest. '
                         'Anyone can replace both content and hashes. This is not proof of origin, '
                         'an execution attestation, or fresh behavior verification; saved claims are not endorsed.',
    }
