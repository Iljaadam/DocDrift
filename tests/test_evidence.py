"""Untrusted ZIP evidence is read as data; nothing is extracted or executed."""

import hashlib
import json
import stat
import struct
import warnings
import zipfile
from pathlib import Path

import pytest

from docdrift.evidence import EvidenceError, verify_evidence


DEFAULT_FILES = {'report.json': b'{"repair_verdict":"behavior_verified"}', 'original/example.py': b'print("example")\n'}


def make_archive(tmp_path, files=None, *, manifest=None, extra=None, compression=zipfile.ZIP_DEFLATED):
    payload = dict(DEFAULT_FILES if files is None else files)
    if manifest is None:
        manifest = {'algorithm': 'sha256', 'files': {name: hashlib.sha256(content).hexdigest() for name, content in payload.items()}}
    raw_manifest = manifest if isinstance(manifest, bytes) else json.dumps(manifest).encode()
    target = tmp_path / 'evidence.zip'
    with zipfile.ZipFile(target, 'w', compression) as archive:
        for name, content in payload.items():
            archive.writestr(name, content)
        for name, content in (extra or {}).items():
            archive.writestr(name, content)
        archive.writestr('manifest.json', raw_manifest)
    return target


def modify_header(path, offset, field_offset, value, kind='<H'):
    data = bytearray(path.read_bytes())
    struct.pack_into(kind, data, offset + field_offset, value)
    path.write_bytes(data)


def test_matching_manifest_returns_integrity_only_and_hash_of_exact_archive(tmp_path, monkeypatch):
    marker = tmp_path / 'must-not-exist'
    files = dict(DEFAULT_FILES)
    files['original/example.py'] = f'from pathlib import Path\nPath({str(marker)!r}).write_text("executed")\n'.encode()
    files['review.html'] = b'<script>throw new Error("must never run")</script>'
    archive = make_archive(tmp_path, files)
    before = archive.read_bytes()
    def extraction_forbidden(*args, **kwargs):
        pytest.fail('Integrity checking must not extract ZIP contents')
    monkeypatch.setattr(zipfile.ZipFile, 'extract', extraction_forbidden)
    monkeypatch.setattr(zipfile.ZipFile, 'extractall', extraction_forbidden)
    result = verify_evidence(archive)
    assert result['status'] == 'integrity_verified'
    assert result['files_checked'] == len(files)
    assert result['archive_sha256'] == hashlib.sha256(before).hexdigest()
    assert result['execution_attested'] is result['authenticity_attested'] is False
    assert 'not proof of origin' in result['coverage_note']
    assert 'saved claims are not endorsed' in result['coverage_note']
    assert result['uncompressed_bytes'] == sum(len(value) for value in files.values()) + len(zipfile.ZipFile(archive).read('manifest.json'))
    assert archive.read_bytes() == before
    assert not marker.exists()
    assert sorted(path.name for path in tmp_path.iterdir()) == ['evidence.zip']


def test_current_engine_export_is_accepted_without_running_anything_new(tmp_path):
    from test_engine import ContractAdapter, run_fixture
    report, state = run_fixture(tmp_path, ContractAdapter())
    archive = state / 'runs' / report['run_id'] / 'evidence.zip'
    result = verify_evidence(archive)
    with zipfile.ZipFile(archive) as stream:
        assert result['files_checked'] == len(stream.infolist()) - 1
        assert 'review.html' in stream.namelist()
    assert result['execution_attested'] is False


def test_arbitrary_report_claim_is_not_interpreted_or_endorsed(tmp_path):
    archive = make_archive(tmp_path, {'report.json': b'not even valid JSON; no report semantics are attested'})
    result = verify_evidence(archive)
    assert result['status'] == 'integrity_verified'
    assert 'repair_verdict' not in result
    assert not result['execution_attested']


@pytest.mark.parametrize('mutation', ['changed', 'missing', 'extra', 'no-report', 'self-listed'])
def test_tampered_or_incomplete_member_coverage_is_rejected(tmp_path, mutation):
    files = dict(DEFAULT_FILES)
    manifest = {'algorithm': 'sha256', 'files': {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}}
    extra = None
    if mutation == 'changed':
        files['report.json'] += b'changed'
    elif mutation == 'missing':
        files.pop('original/example.py')
    elif mutation == 'extra':
        extra = {'unlisted.txt': b'unlisted'}
    elif mutation == 'no-report':
        files.pop('report.json')
        manifest['files'].pop('report.json')
    else:
        manifest['files']['manifest.json'] = 'a' * 64
    archive = make_archive(tmp_path, files, manifest=manifest, extra=extra)
    with pytest.raises(EvidenceError, match='mismatch|cover|report.json'):
        verify_evidence(archive)


@pytest.mark.parametrize('manifest', [
    b'not json', b'[]', b'{"algorithm":"sha256","files":[],"extra":1}',
    b'{"algorithm":"sha256","algorithm":"sha256","files":{}}',
    b'{"algorithm":"sha256","files":{"report.json":"a","report.json":"b"}}',
    b'{"algorithm":"sha256","files":{"report.json":NaN}}',
    b'{"algorithm":"sha256","files":{"report.json":true}}',
    b'{"algorithm":"sha256","files":{"report.json":4}}',
    b'{"algorithm":"md5","files":{}}',
    b'{"algorithm":"sha256","files":{"report.json":"ABC"}}',
    b'{"algorithm":"sha256","files":{"../escape":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}',
    b'\xff\xfe',
])
def test_manifest_is_strict_and_has_only_canonical_sha256_entries(tmp_path, manifest):
    archive = make_archive(tmp_path, manifest=manifest)
    with pytest.raises(EvidenceError):
        verify_evidence(archive)


@pytest.mark.parametrize('name', ['../escape', '/absolute', 'C:/drive', 'a\\b', 'a//b', 'a/./b', './report.json', 'a/../report.json', 'a\nname', 'directory/'])
def test_unsafe_and_noncanonical_member_paths_are_rejected(tmp_path, name):
    archive = make_archive(tmp_path, {'report.json': b'{}', name: b'unsafe'})
    with pytest.raises(EvidenceError, match='path|directories'):
        verify_evidence(archive)
    assert sorted(path.name for path in tmp_path.iterdir()) == ['evidence.zip']


def test_null_byte_filename_cannot_be_silently_truncated(tmp_path):
    archive = make_archive(tmp_path, {'report.json': b'{}', 'evilX.py': b''}, compression=zipfile.ZIP_STORED)
    raw = archive.read_bytes().replace(b'evilX.py', b'evil\x00.py')
    archive.write_bytes(raw)
    with pytest.raises(EvidenceError, match='path|filename'):
        verify_evidence(archive)


def test_duplicate_zip_members_are_rejected_even_with_same_content(tmp_path):
    archive = make_archive(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        with zipfile.ZipFile(archive, 'a') as stream:
            stream.writestr('report.json', DEFAULT_FILES['report.json'])
    with pytest.raises(EvidenceError, match='Duplicate ZIP'):
        verify_evidence(archive)


@pytest.mark.parametrize('mode', [stat.S_IFLNK, stat.S_IFIFO, stat.S_IFSOCK, stat.S_IFCHR, stat.S_IFDIR])
def test_links_and_special_members_are_rejected(tmp_path, mode):
    archive = make_archive(tmp_path, {'report.json': b'{}'})
    entry = zipfile.ZipInfo('special')
    entry.create_system = 3
    entry.external_attr = (mode | 0o600) << 16
    with zipfile.ZipFile(archive, 'a') as stream:
        stream.writestr(entry, b'outside')
    with pytest.raises(EvidenceError, match='special files'):
        verify_evidence(archive)


@pytest.mark.parametrize('location', ['local', 'central', 'both'])
def test_encrypted_flags_in_either_header_are_rejected(tmp_path, location):
    archive = make_archive(tmp_path)
    raw = archive.read_bytes()
    central = raw.index(b'PK\x01\x02')
    if location in {'local', 'both'}:
        modify_header(archive, 0, 6, 1)
    if location in {'central', 'both'}:
        modify_header(archive, central, 8, 1)
    with pytest.raises(EvidenceError, match='Encrypted'):
        verify_evidence(archive)


def test_corrupt_member_crc_and_compressed_stream_are_rejected(tmp_path):
    archive = make_archive(tmp_path, compression=zipfile.ZIP_STORED)
    raw = bytearray(archive.read_bytes())
    offset = raw.index(DEFAULT_FILES['report.json'])
    raw[offset] ^= 1
    archive.write_bytes(raw)
    with pytest.raises(EvidenceError, match='integrity|compression'):
        verify_evidence(archive)
    archive = make_archive(tmp_path)
    raw = bytearray(archive.read_bytes())
    name_length, extra_length = struct.unpack_from('<HH', raw, 26)
    offset = 30 + name_length + extra_length
    raw[offset:offset + 5] = b'\xff' * 5
    archive.write_bytes(raw)
    with pytest.raises(EvidenceError, match='integrity|compression'):
        verify_evidence(archive)


def test_invalid_zip_and_missing_manifest_are_rejected(tmp_path):
    archive = tmp_path / 'evidence.zip'
    archive.write_bytes(b'not a zip')
    with pytest.raises(EvidenceError, match='ZIP'):
        verify_evidence(archive)
    with zipfile.ZipFile(archive, 'w') as stream:
        stream.writestr('report.json', b'{}')
    with pytest.raises(EvidenceError, match='manifest.json'):
        verify_evidence(archive)


def test_advertised_zip_bomb_is_rejected_before_decompression(tmp_path, monkeypatch):
    archive = make_archive(tmp_path)
    raw = archive.read_bytes()
    central = raw.index(b'PK\x01\x02')
    modify_header(archive, central, 24, 21 * 1024 * 1024, '<I')
    def no_open(*args, **kwargs):
        pytest.fail('Oversized metadata must be rejected before opening members')
    monkeypatch.setattr(zipfile.ZipFile, 'open', no_open)
    with pytest.raises(EvidenceError, match='20 MiB'):
        verify_evidence(archive)


def test_forged_count_does_not_allocate_an_unbounded_member_list(tmp_path, monkeypatch):
    archive = make_archive(tmp_path)
    raw = archive.read_bytes()
    end = raw.rindex(b'PK\x05\x06')
    modify_header(archive, end, 8, 1)
    modify_header(archive, end, 10, 1)
    def no_zipfile(*args, **kwargs):
        pytest.fail('Actual central-directory count must be checked before ZipFile')
    monkeypatch.setattr(zipfile, 'ZipFile', no_zipfile)
    with pytest.raises(EvidenceError, match='member count'):
        verify_evidence(archive)


def test_limits_for_archive_manifest_and_member_count(tmp_path, monkeypatch):
    archive = make_archive(tmp_path)
    monkeypatch.setattr('docdrift.evidence.MAX_ARCHIVE_BYTES', 16)
    with pytest.raises(EvidenceError, match='archive limit'):
        verify_evidence(archive)
    monkeypatch.setattr('docdrift.evidence.MAX_ARCHIVE_BYTES', 25 * 1024 * 1024)
    monkeypatch.setattr('docdrift.evidence.MAX_MANIFEST_BYTES', 1)
    with pytest.raises(EvidenceError, match='Manifest exceeds'):
        verify_evidence(archive)
    monkeypatch.setattr('docdrift.evidence.MAX_MEMBERS', 1)
    with pytest.raises(EvidenceError, match='member limit'):
        verify_evidence(archive)


def test_unsupported_compression_and_header_disagreement_are_rejected(tmp_path):
    archive = make_archive(tmp_path, compression=zipfile.ZIP_BZIP2)
    with pytest.raises(EvidenceError, match='compression method'):
        verify_evidence(archive)
    archive = make_archive(tmp_path)
    modify_header(archive, 0, 8, zipfile.ZIP_STORED)
    with pytest.raises(EvidenceError, match='headers disagree'):
        verify_evidence(archive)


def test_missing_archive_is_a_safe_evidence_error(tmp_path):
    with pytest.raises(EvidenceError, match='Could not read'):
        verify_evidence(tmp_path / 'missing.zip')
    with pytest.raises(EvidenceError, match='regular file'):
        verify_evidence(tmp_path)


@pytest.mark.parametrize('member_name', ['report.json', 'manifest.json'])
def test_understated_sizes_cannot_hide_extra_deflate_output(tmp_path, member_name):
    if member_name == 'report.json':
        prefix = b'{}'
        manifest = {'algorithm': 'sha256', 'files': {'report.json': hashlib.sha256(prefix).hexdigest()}}
        archive = make_archive(tmp_path, {'report.json': prefix + b' ' * (8 * 1024 * 1024)}, manifest=manifest)
    else:
        prefix = json.dumps({'algorithm': 'sha256', 'files': {'report.json': hashlib.sha256(b'{}').hexdigest()}}).encode()
        archive = make_archive(tmp_path, {'report.json': b'{}'}, manifest=prefix + b' ' * (8 * 1024 * 1024))
    with zipfile.ZipFile(archive) as stream:
        local = stream.getinfo(member_name).header_offset
    raw = archive.read_bytes()
    central = 0
    while True:
        central = raw.index(b'PK\x01\x02', central)
        length = struct.unpack_from('<H', raw, central + 28)[0]
        if raw[central + 46:central + 46 + length] == member_name.encode():
            break
        central += 4
    # Keep both headers and the prefix CRC mutually consistent. ZipExtFile
    # would accept this prefix and silently discard the actual expanded tail.
    for offset, size_field, crc_field in [(local, 22, 14), (central, 24, 16)]:
        modify_header(archive, offset, size_field, len(prefix), '<I')
        modify_header(archive, offset, crc_field, zipfile.crc32(prefix), '<I')
    with pytest.raises(EvidenceError, match='exceeds its declared'):
        verify_evidence(archive)


def test_local_crc_and_sizes_must_match_without_a_data_descriptor(tmp_path):
    archive = make_archive(tmp_path)
    modify_header(archive, 0, 14, 123, '<I')
    modify_header(archive, 0, 18, 0, '<I')
    modify_header(archive, 0, 22, 0, '<I')
    with pytest.raises(EvidenceError, match='CRC or sizes disagree'):
        verify_evidence(archive)


def test_data_descriptors_are_explicitly_outside_the_export_format(tmp_path):
    archive = make_archive(tmp_path)
    raw = archive.read_bytes()
    central = raw.index(b'PK\x01\x02')
    modify_header(archive, 0, 6, 8)
    modify_header(archive, central, 8, 8)
    with pytest.raises(EvidenceError, match='data descriptors'):
        verify_evidence(archive)


@pytest.mark.parametrize('tail', ['truncated', 'trailing', 'concatenated'])
def test_deflate_stream_must_finish_once_and_consume_exactly_its_region(tmp_path, tail):
    import zlib
    original = b'{"saved":"evidence"}'
    encoder = zlib.compressobj(wbits=-15)
    compressed = encoder.compress(original) + encoder.flush()
    if tail == 'truncated':
        compressed = compressed[:-1]
    elif tail == 'trailing':
        compressed += b'junk'
    else:
        encoder = zlib.compressobj(wbits=-15)
        compressed += encoder.compress(b'second stream') + encoder.flush()
    manifest = {'algorithm': 'sha256', 'files': {'report.json': hashlib.sha256(original).hexdigest()}}
    archive = make_archive(tmp_path, {'report.json': compressed}, manifest=manifest, compression=zipfile.ZIP_STORED)
    central = archive.read_bytes().index(b'PK\x01\x02')
    for offset, method_field, crc_field, length_field in [(0, 8, 14, 22), (central, 10, 16, 24)]:
        modify_header(archive, offset, method_field, zipfile.ZIP_DEFLATED)
        modify_header(archive, offset, crc_field, zlib.crc32(original), '<I')
        modify_header(archive, offset, length_field, len(original), '<I')
    with pytest.raises(EvidenceError, match='incomplete deflate|extra compressed'):
        verify_evidence(archive)


def test_valid_empty_and_multi_chunk_members_work_with_both_compressions(tmp_path):
    import random
    # Exercise compressed-input and decoded-output boundaries independently.
    payloads = [b'', b'x' * (2 * 65536), random.Random(1).randbytes(2 * 65536 + 17)]
    for compression in [zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED]:
        for payload in payloads:
            archive = make_archive(tmp_path, {'report.json': payload}, compression=compression)
            assert verify_evidence(archive)['files_checked'] == 1
