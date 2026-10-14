import gzip
import hashlib
import io
import json
import subprocess
import tarfile

import httpx
import pytest

from docdrift.engine import inspect_github
from docdrift.snapshot import SnapshotError


def owned_transport(files):
    commit, tree = 'a' * 40, 'b' * 40
    entries = []
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode='w') as stream:
        for name, content in files.items():
            blob = hashlib.sha1(f'blob {len(content)}\0'.encode() + content).hexdigest()
            entries.append({'path': name, 'mode': '100644', 'type': 'blob', 'size': len(content), 'sha': blob})
            member = tarfile.TarInfo(f'owned-source/{name}')
            member.size = len(content)
            stream.addfile(member, io.BytesIO(content))
    compressed = gzip.compress(archive.getvalue())
    requests = []

    def response(status, body=b'', headers=None):
        return httpx.Response(status, stream=httpx.ByteStream(body), headers=headers or {})

    def handler(request):
        requests.append(request)
        if request.url.path == '/repos/owned/source/commits/main':
            return response(200, json.dumps({'sha': commit, 'commit': {'tree': {'sha': tree}}}).encode())
        if request.url.path == f'/repos/owned/source/git/trees/{tree}':
            return response(200, json.dumps({'sha': tree, 'truncated': False, 'tree': entries}).encode())
        if request.url.path == f'/repos/owned/source/tarball/{commit}':
            return response(302, headers={'location': f'https://codeload.github.com/owned/source/legacy.tar.gz/{commit}'})
        if request.url.host == 'codeload.github.com':
            return response(200, compressed)
        raise AssertionError(f'Unexpected public request: {request.url}')
    return httpx.MockTransport(handler), requests


def test_public_inventory_executes_nothing_and_makes_no_verification_claim(tmp_path, monkeypatch):
    marker = tmp_path / 'target-code-executed'
    files = {'README.md': b'```python\nprint(1)\n```\n\n```pycon\n>>> print(1)\n```\n',
        'danger.py': f'from pathlib import Path\nPath({str(marker)!r}).touch()\n'.encode()}
    transport, requests = owned_transport(files)

    def no_process(*args, **kwargs):
        raise AssertionError('Public snapshot inspection tried to launch a process')
    monkeypatch.setattr(subprocess, 'Popen', no_process)
    with httpx.Client(transport=transport, headers={'Authorization': 'Bearer unrelated-key'}, cookies={'session': 'unrelated-session'}) as client:
        result = inspect_github('owned/source', 'main', ['README.md'], client=client)
    assert result['execution'] == 'not_run'
    assert result['behavior_verified'] is False
    assert result['provenance']['commit'] == 'a' * 40
    assert len(result['examples']) == 2
    assert result['examples'][1]['status'] == 'unsupported'
    assert not marker.exists()
    assert len(requests) == 4
    assert all('authorization' not in request.headers and 'cookie' not in request.headers for request in requests)


def test_public_inspection_rejects_document_escape_before_network():
    transport, requests = owned_transport({'README.md': b'hello'})
    with httpx.Client(transport=transport) as client:
        with pytest.raises(SnapshotError):
            inspect_github('owned/source', 'main', ['../credentials.md'], client=client)
    assert requests == []
