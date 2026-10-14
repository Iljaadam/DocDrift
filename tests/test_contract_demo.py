import json
import socket
import subprocess
from pathlib import Path

from docdrift.contract_demo import run_contract_demo
from docdrift.store import StateStore


def test_contract_demo_never_connects_executes_or_reads_provider_secrets(tmp_path, monkeypatch):
    secret = 'existing-newsbias-key-must-not-enter-this-demo'
    monkeypatch.setenv('NEBIUS_API_KEY', secret)

    def forbidden(*args, **kwargs):
        raise AssertionError('Offline contract demo attempted a network connection or process execution')

    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    report = run_contract_demo(tmp_path)
    assert report['mode'] == 'offline_synthetic_contract'
    assert report['live_requests'] == report['code_executions'] == report['paid_calls'] == 0
    assert not report['behavior_verified']
    raw = Path(report['report_path']).read_bytes()
    assert secret.encode() not in raw
    assert b'Bearer ' not in raw
    receipts = report['submission_receipts']
    assert len(receipts) == 4
    assert sum(receipt['state'] == 'uncertain' for receipt in receipts) == 1
    assert sum(request['method'] == 'POST' and request['path'] == 'instances' for request in report['requests']) == 4
    assert report['results']['nonzero_exit']['service_state'] == 'SUCCESS'
    assert report['results']['nonzero_exit']['exit_code'] == 1
    ledger = StateStore(tmp_path).run(report['run_id'])
    assert ledger['metadata']['kind'] == 'offline_sandbox_contract'
    assert ledger['phases']['offline_contract_finished']['live_requests'] == 0


def test_cli_contract_output_carries_synthetic_label(tmp_path, monkeypatch, capsys):
    from docdrift.cli import main
    monkeypatch.setattr('sys.argv', ['docdrift', '--state-dir', str(tmp_path), 'sandbox-contract-demo'])
    main()
    summary = json.loads(capsys.readouterr().out)
    assert summary['mode'] == 'offline_synthetic_contract'
    assert summary['behavior_verified'] is False
    assert summary['live_requests'] == 0
    assert Path(summary['report_path']).is_file()
