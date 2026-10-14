"""Repair strategies against scripted (synthetic) model responses; no inference."""

import json
from pathlib import Path

import pytest

from docdrift.cli import demo_repository
from docdrift.markdown import extract_examples
from docdrift.repair import (TOKEN_FACTORY_BASE_URL, InferenceError, RepairBudget, RepairContext, ScriptedModel,
                             TokenFactoryClient, agent_repair, one_shot_repair)
from docdrift.snapshot import resolve_local


FIXTURE = Path(__file__).resolve().parents[1] / 'fixtures' / 'renamed_method'
REPAIR = (FIXTURE / 'repair.py').read_text()
FAILURE = {'exit_code': 1, 'stdout_tail': '', 'stderr_tail': "AttributeError: 'WordCounter' object has no attribute 'tally'\n"}


def reply(content=None, tool_calls=None, prompt=100, completion=20):
    message = {'role': 'assistant', 'content': content}
    if tool_calls:
        message['tool_calls'] = tool_calls
    return {'choices': [{'message': message}], 'usage': {'prompt_tokens': prompt, 'completion_tokens': completion}}


def tool(name, index=0, **arguments):
    return {'id': f'call-{name}-{index}', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(arguments)}}


@pytest.fixture
def context(tmp_path):
    repository, snapshot = tmp_path / 'repository', tmp_path / 'snapshot'
    demo_repository(FIXTURE / 'repository', repository)
    resolve_local(repository, 'HEAD', snapshot)
    target = extract_examples('README.md', (snapshot / 'README.md').read_bytes())[0]
    runs = []

    def run_python(code):
        runs.append(code)
        return {'exit_code': 0, 'stdout': '{}', 'stderr': '', 'timed_out': False}
    result = RepairContext(snapshot, 'README.md', target, FAILURE, run_python=run_python)
    result.runs = runs
    return result


def test_one_shot_accepts_a_policy_compliant_fenced_replacement(context):
    model = ScriptedModel([reply(f'Here:\n```python\n{REPAIR}```')])
    outcome = one_shot_repair(context, model)
    assert outcome['status'] == 'proposed'
    assert outcome['replacement'] == REPAIR
    assert outcome['live_inference'] is False
    assert outcome['usage'] == {'model_calls': 1, 'prompt_tokens': 100, 'completion_tokens': 20, 'snippet_runs': 0, 'malformed_responses': 0}
    assert model.requests[0]['tools'] is None


def test_one_shot_without_a_fence_is_malformed_and_proposes_nothing(context):
    outcome = one_shot_repair(context, ScriptedModel([reply('Use count instead of tally.')]))
    assert outcome['status'] == 'malformed_responses'
    assert outcome['replacement'] is None


def test_one_shot_hardcoded_output_is_rejected_by_static_policy(context):
    outcome = one_shot_repair(context, ScriptedModel([reply('```python\nprint("{}")\n```')]))
    assert outcome['status'] == 'all_candidates_rejected'
    assert outcome['candidates'][0]['static_verdict'] == 'rejected'


def test_prompt_never_contains_profile_checks_or_expected_values(context):
    model = ScriptedModel([reply(f'```python\n{REPAIR}```')])
    one_shot_repair(context, model)
    prompt = json.dumps(model.requests[0]['messages'])
    assert 'expected_json' not in prompt and 'operation_ast_sha256' not in prompt
    assert 'profile.json' not in context.files() and 'checks.py' not in context.files()


def test_agent_investigates_runs_code_and_recovers_from_a_rejection(context):
    model = ScriptedModel([
        reply(tool_calls=[tool('list_files'), tool('read_file', path='drift_demo/__init__.py')]),
        reply(tool_calls=[tool('run_python', code=REPAIR)]),
        reply(tool_calls=[tool('submit_replacement', code='print("{}")\n')]),
        reply(tool_calls=[tool('submit_replacement', 1, code=REPAIR)]),
    ])
    outcome = agent_repair(context, model)
    assert outcome['status'] == 'proposed' and outcome['replacement'] == REPAIR
    assert [item['static_verdict'] for item in outcome['candidates']] == ['rejected', 'accepted_static']
    assert outcome['usage']['model_calls'] == 4 and outcome['usage']['snippet_runs'] == 1
    assert context.runs == [REPAIR]
    tool_messages = [m for m in model.requests[1]['messages'] if m['role'] == 'tool']
    assert 'README.md' in tool_messages[0]['content'] and 'def count' in tool_messages[1]['content']
    assert model.requests[3]['messages'][-1]['content'].startswith('Rejected by patch policy')


def test_agent_cannot_read_outside_the_pinned_snapshot(context):
    model = ScriptedModel([reply(tool_calls=[tool('read_file', path='../profile.json')]), reply(f'```python\n{REPAIR}```')])
    outcome = agent_repair(context, model)
    assert model.requests[1]['messages'][-1]['content'].startswith('Error: Unsafe snapshot path')
    assert outcome['status'] == 'proposed'


def test_agent_stops_at_the_model_call_budget(context):
    model = ScriptedModel([reply(tool_calls=[tool('list_files', index)]) for index in range(10)])
    outcome = agent_repair(context, model, RepairBudget(max_model_calls=3))
    assert outcome['status'] == 'budget_exhausted' and outcome['replacement'] is None
    assert len(model.requests) == 3


def test_agent_stops_at_the_token_budget(context):
    model = ScriptedModel([reply(tool_calls=[tool('list_files', index)], prompt=600) for index in range(10)])
    outcome = agent_repair(context, model, RepairBudget(max_total_tokens=1000))
    assert outcome['status'] == 'budget_exhausted' and len(model.requests) == 2


def test_agent_snippet_runs_are_bounded(context):
    calls = [reply(tool_calls=[tool('run_python', index, code='print(1)')]) for index in range(3)]
    outcome = agent_repair(context, ScriptedModel(calls), RepairBudget(max_model_calls=3, max_snippet_runs=2))
    assert outcome['usage']['snippet_runs'] == 2 and len(context.runs) == 2


def test_agent_stops_after_two_rejected_candidates(context):
    bad = 'print("{}")\n'
    model = ScriptedModel([reply(tool_calls=[tool('submit_replacement', 0, code=bad)]), reply(tool_calls=[tool('submit_replacement', 1, code='')])])
    outcome = agent_repair(context, model)
    assert outcome['status'] == 'all_candidates_rejected' and outcome['replacement'] is None


def test_agent_stops_on_repeated_malformed_responses(context):
    model = ScriptedModel([reply('thinking...'), reply(tool_calls=[{'id': 'x', 'type': 'function', 'function': {'name': 'read_file', 'arguments': '{not json'}}])])
    outcome = agent_repair(context, model)
    assert outcome['status'] == 'malformed_responses'


def test_inference_error_stops_without_retry(context):
    outcome = agent_repair(context, ScriptedModel([]))
    assert outcome['status'] == 'inference_error' and outcome['usage']['model_calls'] == 1


def test_token_factory_client_sends_one_bounded_openai_compatible_request():
    sent = []

    def transport(url, headers, body, timeout):
        sent.append((url, headers, json.loads(body)))
        return json.dumps(reply('ok')).encode()
    client = TokenFactoryClient('nvidia/example-model', 'secret', transport=transport)
    client.complete([{'role': 'user', 'content': 'hi'}], [{'type': 'function'}], 256)
    [(url, headers, body)] = sent
    assert url == TOKEN_FACTORY_BASE_URL + 'chat/completions'
    assert headers['Authorization'] == 'Bearer secret'
    assert body == {'model': 'nvidia/example-model', 'messages': [{'role': 'user', 'content': 'hi'}], 'temperature': 0, 'max_tokens': 256, 'tools': [{'type': 'function'}], 'tool_choice': 'auto'}
    assert client.live is True


def test_token_factory_client_requires_explicit_model_and_key_and_rejects_malformed_responses():
    with pytest.raises(ValueError):
        TokenFactoryClient('', 'secret')
    with pytest.raises(ValueError):
        TokenFactoryClient('nvidia/example-model', '')
    client = TokenFactoryClient('nvidia/example-model', 'secret', transport=lambda *args: b'{"choices": []}')
    with pytest.raises(InferenceError):
        client.complete([], None, 10)
