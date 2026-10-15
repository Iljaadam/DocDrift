"""Validate the additive development fixture without executing its package."""

import ast
import hashlib
import json
import runpy
import tomllib
from pathlib import Path

import pytest

from docdrift.markdown import extract_examples
from docdrift.policy import apply_replacement
from docdrift.profile import check_result, load_profile, operation_reaches_output
from docdrift.repair import RepairContext, ScriptedModel, agent_repair, one_shot_repair
from docdrift.snapshot import file_hashes


FIXTURE = Path(__file__).resolve().parents[1] / 'fixtures/development/source_only'
REPOSITORY = FIXTURE / 'repository'


def examples():
    return extract_examples('README.md', (REPOSITORY / 'README.md').read_bytes())


@pytest.fixture
def curator_checks():
    # Trusted external oracle, not the patchable package.
    return runpy.run_path(str(FIXTURE / 'checks.py'))


def test_fixture_freeze_covers_every_artifact_and_records_development_provenance():
    manifest = json.loads((FIXTURE / 'manifest.json').read_text())
    actual = {path.relative_to(FIXTURE).as_posix() for path in FIXTURE.rglob('*') if path.is_file() and path.name != 'manifest.json' and '__pycache__' not in path.parts}
    assert manifest['algorithm'] == 'sha256'
    assert set(manifest['files']) == actual
    assert all(hashlib.sha256((FIXTURE / name).read_bytes()).hexdigest() == digest for name, digest in manifest['files'].items())
    provenance = json.loads((FIXTURE / 'provenance.json').read_text())
    assert provenance['ownership'] == 'owned'
    assert provenance['split'] == 'development'
    assert provenance['model_evaluation_status_at_freeze'] == 'not_run'
    assert provenance['behavior_verified_at_freeze'] is False
    assert 'guessing remains possible' in provenance['claim_limit']


def test_source_defines_current_api_but_documentation_has_no_current_target_neighbor():
    document = (REPOSITORY / 'README.md').read_text()
    target, healthy = examples()
    assert [item.status for item in [target, healthy]] == ['candidate', 'candidate']
    assert 'OccurrenceIndex().build(words)' in target.code
    assert '.positions(' not in document and 'include_empty' not in document
    assert 'OccurrenceIndex' not in healthy.code
    assert 'TokenMetrics().measure(words)' in healthy.code
    package = ast.parse((REPOSITORY / 'drift_demo/__init__.py').read_text())
    index = next(node for node in package.body if isinstance(node, ast.ClassDef) and node.name == 'OccurrenceIndex')
    methods = [node for node in index.body if isinstance(node, ast.FunctionDef)]
    assert [method.name for method in methods] == ['positions']
    assert [argument.arg for argument in methods[0].args.kwonlyargs] == ['include_empty']
    assert isinstance(methods[0].args.kw_defaults[0], ast.Constant)
    assert methods[0].args.kw_defaults[0].value is False
    assert (FIXTURE / 'repair.py').read_text() == target.code.replace('.build(words)', '.positions(words, include_empty=True)')


def test_profile_is_dependency_free_and_oracle_is_external_to_repository():
    profile, frozen_files = load_profile(FIXTURE / 'profile.json')
    assert profile['python'] == '3.12'
    assert profile['setup'] == {'kind': 'source_tree', 'dependencies': []}
    assert profile['target'] == {'path': 'README.md', 'ordinal': 0}
    assert set(frozen_files) == {'profile.json', 'checks.py'}
    project = tomllib.loads((REPOSITORY / 'pyproject.toml').read_text())
    assert project['project']['dependencies'] == []
    assert not (REPOSITORY / 'checks.py').exists()
    assert not (REPOSITORY / 'profile.json').exists()
    assert not (REPOSITORY / 'repair.py').exists()
    oracle = ast.parse((FIXTURE / 'checks.py').read_text())
    assert all(not isinstance(node, ast.ImportFrom) or node.module != 'drift_demo' for node in ast.walk(oracle))
    assert all(alias.name != 'drift_demo' for node in ast.walk(oracle) if isinstance(node, ast.Import) for alias in node.names)


@pytest.mark.parametrize('role', ['target', 'healthy'])
def test_frozen_inputs_match_independent_oracle_and_current_flow_contract(curator_checks, role):
    profile, _ = load_profile(FIXTURE / 'profile.json')
    spec = next(item for item in profile['examples'] if item['role'] == role)
    source = (FIXTURE / 'repair.py').read_text() if role == 'target' else examples()[1].code
    assert len(spec['cases']) == len({case['env']['DOCDRIFT_INPUT'] for case in spec['cases']}) == 3
    assert curator_checks['check_operation'](source, role) == []
    assert operation_reaches_output(source, spec['required_call'])
    for case in spec['cases']:
        expected = curator_checks['expected_result'](case['env']['DOCDRIFT_INPUT'], role)
        assert expected == case['expected_json']
        assert curator_checks['check_stdout'](json.dumps(expected), case['env']['DOCDRIFT_INPUT'], role) == []
        # A synthetic observation verifies the static acceptance contract only.
        observed = {'state': 'completed', 'exit_code': 0, 'stdout': json.dumps(expected), 'timed_out': False}
        checks = check_result(observed, case, source, spec['required_call'], spec['operation_ast_sha256'])
        assert checks['behavior_passed'] and checks['known_repair_ast_match']


def test_varied_case_requires_exact_token_positions_including_empty_tokens(curator_checks):
    profile, _ = load_profile(FIXTURE / 'profile.json')
    spec = profile['examples'][0]
    case = spec['cases'][2]
    assert json.loads(case['env']['DOCDRIFT_INPUT']) == ['', 'é', 'é', 'E', 'two words', ' ', '']
    expected = case['expected_json']
    assert expected == {'': [0, 6], 'é': [1, 2], 'E': [3], 'two words': [4], ' ': [5]}
    wrong = {key: value for key, value in expected.items() if key}
    source = (FIXTURE / 'repair.py').read_text().replace(', include_empty=True', '')
    observed = {'state': 'completed', 'exit_code': 0, 'stdout': json.dumps(wrong), 'timed_out': False}
    checked = check_result(observed, case, source, spec['required_call'], spec['operation_ast_sha256'])
    assert checked['execution_passed'] and not checked['observable_passed']
    assert not checked['behavior_passed']
    assert curator_checks['check_stdout'](json.dumps(wrong), case['env']['DOCDRIFT_INPUT'])
    assert curator_checks['check_stdout']('{"": [false, 6], "é": [1, 2], "E": [3], "two words": [4], " ": [5]}', case['env']['DOCDRIFT_INPUT'])


def test_one_fence_repair_preserves_healthy_example_and_protected_source():
    original = (REPOSITORY / 'README.md').read_bytes()
    target, healthy = examples()
    before = file_hashes(REPOSITORY)
    patch = apply_replacement('README.md', original, target.id, target.source_hash, (FIXTURE / 'repair.py').read_text())
    repaired_examples = extract_examples('README.md', patch)
    assert repaired_examples[1].code == healthy.code
    assert repaired_examples[0].code == (FIXTURE / 'repair.py').read_text()
    assert file_hashes(REPOSITORY) == before


def test_source_evidence_is_available_through_agent_tools_but_not_initial_prompt():
    repair = (FIXTURE / 'repair.py').read_text()
    # An illustrative synthetic failure; actual reproduction belongs to Docker.
    context = RepairContext(REPOSITORY, 'README.md', examples()[0], {'exit_code': 1, 'stdout_tail': '', 'stderr_tail': "AttributeError: 'OccurrenceIndex' object has no attribute 'build'"})
    one_shot = ScriptedModel([{'choices': [{'message': {'content': f'```python\n{repair}```'}}]}])
    assert one_shot_repair(context, one_shot)['status'] == 'proposed'
    initial_prompt = json.dumps(one_shot.requests[0]['messages'])
    assert '.positions(' not in initial_prompt
    assert 'include_empty' not in initial_prompt
    assert 'expected_json' not in initial_prompt
    assert 'checks.py' not in context.files() and 'repair.py' not in context.files()
    agent = ScriptedModel([
        {'choices': [{'message': {'tool_calls': [{'id': 'read-source', 'type': 'function', 'function': {'name': 'read_file', 'arguments': json.dumps({'path': 'drift_demo/__init__.py'})}}]}}]},
        {'choices': [{'message': {'tool_calls': [{'id': 'submit', 'type': 'function', 'function': {'name': 'submit_replacement', 'arguments': json.dumps({'code': repair})}}]}}]},
    ])
    outcome = agent_repair(context, agent)
    assert outcome['status'] == 'proposed' and outcome['live_inference'] is False
    source_reply = next(item for item in agent.requests[1]['messages'] if item['role'] == 'tool')
    assert 'def positions' in source_reply['content'] and 'include_empty: bool = False' in source_reply['content']
