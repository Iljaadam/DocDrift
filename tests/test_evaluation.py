"""Evaluation harness over the frozen inventory with contract doubles.

The adapter double never executes code: it maps each example's exact source to
the outcome the curator contract predicts. The oracle model is synthetic and
returns the known repair, so these tests check plumbing and scoring only.
"""

import ast
import json
from pathlib import Path

import pytest

from docdrift.adapters import ExecutionResult
from docdrift.engine import start_run
from docdrift.evaluation import evaluate, evaluate_fixture, markdown_summary
from docdrift.markdown import extract_examples
from docdrift.policy import PolicyError
from docdrift.repair import ScriptedModel


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / 'fixtures' / 'evaluation' / 'index.json'
IMAGE_ID = 'sha256:' + 'b' * 64


def _key(code):
    return ast.dump(ast.parse(code))


def _contracts():
    """Map example AST → per-input outputs, following the frozen profiles."""
    outcomes = {}
    for case in json.loads(INDEX.read_text())['cases']:
        if case['kind'] != 'broken':
            continue
        profile = json.loads((ROOT / case['profile']).read_text())
        examples = extract_examples('README.md', (ROOT / case['repository'] / 'README.md').read_bytes())
        for spec in profile['examples']:
            outputs = {item['env']['DOCDRIFT_INPUT']: (0, json.dumps(item['expected_json'])) for item in spec['cases']}
            code = (ROOT / case['known_repair']).read_text() if spec['role'] == 'target' else examples[spec['ordinal']].code
            outcomes[_key(code)] = outputs
            if spec['role'] == 'target':
                broken = examples[spec['ordinal']].code
                failure = (1, '') if case['predicted_original_failure'] == 'process_exit' else (0, '"wrong shape"')
                outcomes[_key(broken)] = {item['env']['DOCDRIFT_INPUT']: failure for item in spec['cases']}
    return outcomes


class ContractAdapter:
    def __init__(self):
        self.contracts = _contracts()
        self.requests = []

    def preflight(self, image):
        return {'image_id': IMAGE_ID, 'python_version': 'Python 3.12.0', 'network': 'none'}

    def execute(self, request, on_accepted):
        identifier = f'{len(self.requests) + 1:064x}'
        self.requests.append(request)
        on_accepted(identifier)
        return self.observe(identifier)

    def observe(self, identifier, timeout_seconds=30):
        request = self.requests[int(identifier, 16) - 1]
        exit_code, stdout = self.contracts.get(_key(request.code), {}).get(request.environment['DOCDRIFT_INPUT'], (1, ''))
        stderr = '' if exit_code == 0 else 'AttributeError: simulated contract failure\n'
        return ExecutionResult('completed', exit_code, stdout, stderr, identifier, IMAGE_ID, 0.1)

    def cancel(self, identifier):
        pass


class OracleModel(ScriptedModel):
    """Synthetic: answers with the curator's known repair for the prompted document."""

    def __init__(self, tools=False):
        super().__init__([], model='synthetic-oracle')
        self.tools = tools
        self.repairs = {}
        for case in json.loads(INDEX.read_text())['cases']:
            if case['kind'] == 'broken':
                self.repairs[(ROOT / case['repository'] / 'README.md').read_text()] = (ROOT / case['known_repair']).read_text()

    def complete(self, messages, tools, max_tokens):
        self.requests.append({'messages': messages, 'tools': tools})
        repair = next(code for document, code in self.repairs.items() if document in messages[1]['content'])
        if tools:
            call = {'id': 'submit', 'type': 'function', 'function': {'name': 'submit_replacement', 'arguments': json.dumps({'code': repair})}}
            message = {'role': 'assistant', 'content': None, 'tool_calls': [call]}
        else:
            message = {'role': 'assistant', 'content': f'```python\n{repair}```'}
        return {'choices': [{'message': message}], 'usage': {'prompt_tokens': 10, 'completion_tokens': 5}}


def run(tmp_path, strategies, **options):
    return evaluate(INDEX, strategies, tmp_path / 'state', adapter=ContractAdapter(), image='python:3.12-slim', **options)


def test_execution_only_baseline_needs_no_model_and_skips_held_out_by_default(tmp_path):
    report = run(tmp_path, ['execution_only'])
    cases = {row['case'] for row in report['rows']}
    assert not cases & {'renamed_import_broken', 'changed_return_shape_broken', 'renamed_import_healthy'}
    summary = report['summary']['execution_only']
    assert summary['broken_cases'] == 2 and summary['drift_detected'] == 2
    assert summary['false_drift_reports'] == 0 and summary['healthy_cases'] == 2
    assert summary['correct_abstentions'] == summary['unsupported_or_setup_cases'] == 4
    assert summary['unsupported_incorrectly_verified'] == 0 and summary['model_calls'] == 0
    assert report['evidence'] == 'no_model' and report['execution_backend'] == 'ContractAdapter'
    assert all(row['outcome'] == 'pending_reproduction' and not row['scored'] for row in report['rows'] if row['split'] == 'reference')


def test_frozen_checks_catch_the_exit_zero_drift_that_execution_only_misses(tmp_path):
    client = OracleModel()
    report = run(tmp_path, ['execution_only', 'one_shot'], client=client, include_held_out=True)
    rows = {(row['case'], row['strategy']): row for row in report['rows']}
    assert rows['changed_return_shape_broken', 'execution_only']['detected'] is False
    assert rows['changed_return_shape_broken', 'one_shot']['detected'] is True
    assert report['summary']['execution_only']['drift_detected'] == 3
    assert report['summary']['one_shot']['drift_detected'] == 4


@pytest.mark.parametrize('strategy', ['one_shot', 'agent'])
def test_model_strategies_verify_through_the_shared_engine_and_are_labelled_synthetic(tmp_path, strategy):
    report = run(tmp_path, [strategy], client=OracleModel())
    summary = report['summary'][strategy]
    assert report['evidence'] == 'synthetic_not_evidence'
    assert summary['behavior_verified_repairs'] == summary['broken_cases'] == 2
    assert summary['false_drift_reports'] == 0 and summary['model_calls'] == 2
    for row in report['rows']:
        if row.get('run_id'):
            saved = json.loads((tmp_path / 'state' / 'runs' / row['run_id'] / 'report.json').read_text())
            assert saved['repair_source'] == f'synthetic_{strategy}'
            assert saved['usage']['inference_calls'] == 1 and saved['usage']['paid_calls'] == 0
            assert (tmp_path / 'state' / 'runs' / row['run_id'] / 'repair.json').is_file()
    assert 'synthetic_not_evidence' in markdown_summary(report)


def test_model_strategies_require_a_client(tmp_path):
    with pytest.raises(ValueError):
        run(tmp_path, ['agent'])
    with pytest.raises(ValueError):
        run(tmp_path, ['guess'])


def test_single_fixture_repair_command_path(tmp_path):
    fixture = ROOT / 'fixtures' / 'renamed_method'
    row = evaluate_fixture(fixture, 'agent', OracleModel(), tmp_path / 'state', 'python:3.12-slim', adapter=ContractAdapter())
    assert row['outcome'] == 'behavior_verified' and row['evidence'] == 'synthetic_not_evidence'


def test_engine_rejects_a_repair_record_that_does_not_match_the_replacement(tmp_path):
    from docdrift.cli import demo_repository
    fixture = ROOT / 'fixtures' / 'renamed_method'
    repository = tmp_path / 'repository'
    demo_repository(fixture / 'repository', repository)
    record = {'strategy': 'agent', 'replacement': 'print(1)\n', 'usage': {'model_calls': 1}, 'live_inference': False}
    with pytest.raises(PolicyError):
        start_run(repository, 'HEAD', fixture / 'profile.json', fixture / 'repair.py', tmp_path / 'state', IMAGE_ID, ContractAdapter(), repair_record=record)
