import json
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from docdrift.adapters import ExecutionRequest
from docdrift.sandbox_execution import GUEST_REPOSITORY
from docdrift.sandbox_simulation import IMAGE_ID, FixtureSandboxSimulation, create_fixture_simulation


FIXTURE = Path(__file__).resolve().parents[1] / 'fixtures' / 'renamed_method'


def request(tmp_path, code=None, value='[]'):
    snapshot = tmp_path / 'snapshot'
    shutil.copytree(FIXTURE / 'repository', snapshot)
    return ExecutionRequest(snapshot, code or (FIXTURE / 'repair.py').read_text(), {'DOCDRIFT_INPUT': value}, IMAGE_ID)


def test_unknown_uploaded_code_is_never_executed_or_assigned_a_fixture_success(tmp_path, monkeypatch):
    marker = tmp_path / 'must-not-exist'
    code = f'from pathlib import Path\nPath({str(marker)!r}).write_text("executed")\nprint({{}})\n'
    execution = request(tmp_path, code)
    def forbidden(*args, **kwargs):
        pytest.fail('Fixture simulation must never launch a subprocess')
    monkeypatch.setattr(subprocess, 'run', forbidden)
    with create_fixture_simulation(tmp_path / 'state', [FIXTURE]) as adapter:
        result = adapter.execute(execution, lambda _: None, run_id='run', phase='unknown')
        assert result.synthetic and result.exit_code != 0
        assert 'no code was executed' in result.stderr
    assert not marker.exists()


def test_exact_fixture_source_and_input_are_required_for_the_oracle_response(tmp_path):
    execution = request(tmp_path)
    with create_fixture_simulation(tmp_path / 'state', [FIXTURE]) as adapter:
        unknown_input = replace(execution, environment={'DOCDRIFT_INPUT': '["not", "frozen"]'})
        result = adapter.execute(unknown_input, lambda _: None, run_id='run', phase='unknown_input')
        assert result.exit_code != 0 and 'No frozen synthetic fixture response' in result.stderr
        changed_code = replace(execution, code=execution.code + '# different bytes\n')
        result = adapter.execute(changed_code, lambda _: None, run_id='run', phase='changed_code')
        assert result.exit_code != 0
        (execution.snapshot / 'drift_demo' / '__init__.py').write_text('raise RuntimeError("different package")\n')
        result = adapter.execute(execution, lambda _: None, run_id='run', phase='changed_source')
        assert result.exit_code != 0


def test_documentation_patch_is_permitted_without_relaxing_package_identity(tmp_path):
    execution = request(tmp_path)
    document = execution.snapshot / 'README.md'
    document.write_text(document.read_text().replace('.tally(', '.count('))
    with create_fixture_simulation(tmp_path / 'state', [FIXTURE]) as adapter:
        result = adapter.execute(execution, lambda _: None, run_id='run', phase='patched_documentation')
    assert result.exit_code == 0 and json.loads(result.stdout) == {}


def test_saved_run_registration_supports_future_phases_after_restart(tmp_path):
    execution = request(tmp_path)
    state = tmp_path / 'state'
    run_root = tmp_path / 'saved_run'
    shutil.copytree(execution.snapshot, run_root / 'original')
    (run_root / 'profile').mkdir()
    for name in ['profile.json', 'checks.py']:
        shutil.copyfile(FIXTURE / name, run_root / 'profile' / name)
    (run_root / 'replacement.py').write_text(execution.code)
    with create_fixture_simulation(state, [FIXTURE]) as first:
        original = first.execute(execution, lambda _: None, run_id='run', phase='first')
    with create_fixture_simulation(state, []) as resumed:
        resumed.simulation.register_run(run_root)
        receipt = resumed.recover('run', 'first', expected_image_id=IMAGE_ID)
        assert resumed.observe(receipt['operation_id']).operation_id == original.operation_id
        result = resumed.execute(execution, lambda _: None, run_id='run', phase='second')
        assert result.exit_code == 0 and result.synthetic
        assert not any(method == 'POST' and path == 'files' for method, path in resumed.simulation.requests)


def test_unlabelled_external_profile_cannot_be_registered_as_an_owned_fixture(tmp_path):
    profile = json.loads((FIXTURE / 'profile.json').read_text())
    profile['name'] = 'external-repository'
    (tmp_path / 'profile.json').write_text(json.dumps(profile))
    shutil.copyfile(FIXTURE / 'checks.py', tmp_path / 'checks.py')
    service = FixtureSandboxSimulation(tmp_path / 'state')
    with pytest.raises(ValueError, match='owned fixtures'):
        service.register_profile(FIXTURE / 'repository', tmp_path / 'profile.json', (FIXTURE / 'repair.py').read_text())


def test_simulator_emits_no_resource_price_or_measured_duration(tmp_path):
    execution = request(tmp_path)
    with create_fixture_simulation(tmp_path / 'state', [FIXTURE]) as adapter:
        result = adapter.execute(execution, lambda _: None, run_id='run', phase='phase')
        assert result.elapsed_seconds is None
        assert result.synthetic
        assert adapter.execution_contract['repository_path'] == GUEST_REPOSITORY
