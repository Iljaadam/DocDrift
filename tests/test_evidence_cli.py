"""CLI integrity checks stay independent of execution and run state."""

import hashlib
import json
import socket
import zipfile

import pytest

from docdrift.cli import main


@pytest.mark.parametrize('tampered', [False, True])
def test_verify_evidence_cli_reads_only_archive_and_reports_limited_claim(tmp_path, monkeypatch, capsys, tampered):
    archive = tmp_path / 'evidence.zip'
    report = b'{"repair_verdict":"untrusted claim"}\n'
    manifest = {'algorithm': 'sha256', 'files': {'report.json': hashlib.sha256(report).hexdigest()}}
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as stream:
        stream.writestr('report.json', b'changed report' if tampered else report)
        stream.writestr('manifest.json', json.dumps(manifest))
    def forbidden(*args, **kwargs):
        pytest.fail('Evidence checking must not execute, contact a socket, or create state')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr('subprocess.Popen', forbidden)
    monkeypatch.setattr('docdrift.store.StateStore.__init__', forbidden)
    state = tmp_path / 'unused-state'
    monkeypatch.setattr('sys.argv', ['docdrift', '--state-dir', str(state), 'verify-evidence', str(archive)])
    if tampered:
        with pytest.raises(SystemExit) as error:
            main()
        assert error.value.code == 2
        assert 'SHA-256 mismatch' in capsys.readouterr().err
    else:
        main()
        result = json.loads(capsys.readouterr().out)
        assert result['status'] == 'integrity_verified'
        assert result['files_checked'] == 1
        assert result['execution_attested'] is False
        assert result['authenticity_attested'] is False
    assert not state.exists()
