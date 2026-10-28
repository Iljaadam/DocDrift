"""Bounded model repair proposals: a one-shot baseline and a tool-using agent.

Both strategies only propose a replacement for the selected fence. Every
proposal passes the same static patch policy as a manual repair, and the engine
then runs the independent frozen checks. Neither strategy sees the profile,
expected outputs, checks, or known repair.

Live inference requires an explicitly constructed ``TokenFactoryClient``. Tests
and offline rehearsal use ``ScriptedModel``, whose responses are labelled
synthetic and never count as model evidence.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

import httpx

from .markdown import Example
from .policy import PolicyError, apply_replacement
from .snapshot import SnapshotError, file_hashes, safe_path, sha256


TOKEN_FACTORY_BASE_URL = 'https://api.tokenfactory.nebius.com/v1/'
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_DOCUMENT_CHARS = 32 * 1024
MAX_FILE_CHARS = 64 * 1024
MAX_TOOL_OUTPUT_CHARS = 4096
MAX_LISTED_FILES = 200


@dataclass(frozen=True)
class RepairBudget:
    max_model_calls: int = 8
    max_candidates: int = 2
    max_snippet_runs: int = 4
    max_malformed: int = 2
    max_completion_tokens: int = 2048
    max_total_tokens: int = 60_000


class InferenceError(RuntimeError):
    pass


class ModelClient(Protocol):
    model: str
    live: bool

    def complete(self, messages: list[dict], tools: list[dict] | None, max_tokens: int) -> dict: ...


def _http_transport(url: str, headers: dict[str, str], body: bytes, timeout: float) -> bytes:
    if url != TOKEN_FACTORY_BASE_URL + 'chat/completions':
        raise InferenceError('Live inference requires the fixed Token Factory HTTPS endpoint')
    try:
        # A redirect must never forward the bearer key or repeat a billed call.
        with httpx.Client(timeout=timeout, trust_env=False, follow_redirects=False) as client:
            with client.stream('POST', url, headers=headers, content=body) as response:
                if not 200 <= response.status_code < 300:
                    # Provider error bodies can echo request credentials.
                    raise InferenceError(f'Token Factory returned HTTP {response.status_code}')
                data = bytearray()
                for chunk in response.iter_bytes(chunk_size=64 * 1024):
                    data.extend(chunk)
                    if len(data) > MAX_RESPONSE_BYTES:
                        raise InferenceError('Token Factory response exceeds 1 MiB')
    except httpx.HTTPError as exc:
        raise InferenceError('Token Factory request failed') from exc
    return bytes(data)


class TokenFactoryClient:
    """OpenAI-compatible chat completions on Nebius Token Factory.

    One request per call and no automatic retry: every call may consume
    credits, so a failure stops the repair instead of silently resubmitting.
    """

    live = True

    def __init__(self, model: str, api_key: str, *, base_url: str = TOKEN_FACTORY_BASE_URL,
                 timeout: float = 120, transport: Callable[[str, dict, bytes, float], bytes] | None = None):
        if not model or not isinstance(model, str):
            raise ValueError('An explicit model ID is required')
        if not api_key:
            raise ValueError('NEBIUS_API_KEY is required for live inference')
        if base_url.rstrip('/') != TOKEN_FACTORY_BASE_URL.rstrip('/'):
            raise ValueError('Inference requires the fixed Token Factory HTTPS endpoint')
        self.model = model
        self._api_key = api_key
        self._url = base_url.rstrip('/') + '/chat/completions'
        self._timeout = timeout
        self._transport = transport or _http_transport

    def complete(self, messages: list[dict], tools: list[dict] | None, max_tokens: int) -> dict:
        body = {'model': self.model, 'messages': messages, 'temperature': 0, 'max_tokens': max_tokens}
        if tools:
            body['tools'] = tools
            body['tool_choice'] = 'auto'
        headers = {'Authorization': f'Bearer {self._api_key}', 'Content-Type': 'application/json', 'Accept': 'application/json'}
        raw = self._transport(self._url, headers, json.dumps(body).encode(), self._timeout)
        try:
            response = json.loads(raw)
            response['choices'][0]['message']
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise InferenceError('Malformed chat completion response') from exc
        return response


class ScriptedModel:
    """Replays prepared responses. Synthetic: never evidence of model behavior."""

    live = False

    def __init__(self, responses: list[dict], model: str = 'synthetic-scripted'):
        self.model = model
        self._responses = list(responses)
        self.requests: list[dict] = []

    def complete(self, messages: list[dict], tools: list[dict] | None, max_tokens: int) -> dict:
        self.requests.append({'messages': json.loads(json.dumps(messages)), 'tools': tools, 'max_tokens': max_tokens})
        if not self._responses:
            raise InferenceError('Scripted model has no response left')
        return self._responses.pop(0)


@dataclass
class RepairContext:
    """What the model may see: the pinned repository and the observed failure."""

    snapshot: Path
    document_path: str
    target: Example
    failure: dict
    run_python: Callable[[str], dict] | None = None
    _hashes: dict[str, str] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._hashes = file_hashes(self.snapshot)

    def document(self) -> str:
        return (self.snapshot / self.document_path).read_text()[:MAX_DOCUMENT_CHARS]

    def files(self) -> list[str]:
        return sorted(self._hashes)[:MAX_LISTED_FILES]

    def read(self, path: str) -> str:
        path = safe_path(path)
        if path not in self._hashes:
            raise SnapshotError(f'No such file in the pinned snapshot: {path}')
        content = (self.snapshot / path).read_bytes()
        if sha256(content) != self._hashes[path]:
            raise SnapshotError('Pinned snapshot changed during repair')
        return content.decode('utf-8', 'replace')[:MAX_FILE_CHARS]

    def gate(self, code: str) -> str | None:
        """Return a rejection reason, or None when the static patch policy accepts."""
        original = (self.snapshot / self.document_path).read_bytes()
        try:
            apply_replacement(self.document_path, original, self.target.id, self.target.source_hash, code)
        except (PolicyError, SyntaxError) as exc:
            return str(exc) or type(exc).__name__
        return None


SYSTEM_PROMPT = """You repair outdated Python examples in project documentation.
One fenced example no longer works against the pinned library source. Rewrite
only that example so it works with the current API and keeps its documented
purpose, inputs, and printed output format.

Rules:
- Change as little as possible. Keep every meaningful API call and import.
- Do not hardcode results, catch and hide exceptions, skip work, or exit early.
- Do not add Markdown fences inside the code.
- Inputs arrive the same way the original example reads them."""

ONE_SHOT_INSTRUCTION = 'Reply with the complete replacement example in a single ```python fenced block and nothing else.'

AGENT_INSTRUCTION = """Investigate with the tools: read the library source to find the
current API, optionally run candidate code, then call submit_replacement with the
complete replacement example. A rejected submission returns the reason. You have
a limited number of submissions."""

TOOLS = [
    {'type': 'function', 'function': {'name': 'list_files', 'description': 'List files in the pinned repository snapshot.', 'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False}}},
    {'type': 'function', 'function': {'name': 'read_file', 'description': 'Read a UTF-8 file from the pinned repository snapshot.', 'parameters': {'type': 'object', 'properties': {'path': {'type': 'string', 'description': 'Relative path from list_files'}}, 'required': ['path'], 'additionalProperties': False}}},
    {'type': 'function', 'function': {'name': 'run_python', 'description': 'Run Python code in an isolated offline sandbox with the repository importable and the example input set. Returns exit code, stdout, and stderr.', 'parameters': {'type': 'object', 'properties': {'code': {'type': 'string'}}, 'required': ['code'], 'additionalProperties': False}}},
    {'type': 'function', 'function': {'name': 'submit_replacement', 'description': 'Submit the complete replacement for the broken example.', 'parameters': {'type': 'object', 'properties': {'code': {'type': 'string'}}, 'required': ['code'], 'additionalProperties': False}}},
]

_FENCE = re.compile(r'```(?:python|py|python3)?[ \t]*\n(.*?)```', re.DOTALL)


def describe_failure(result: dict, observable_errors: list[str]) -> dict:
    """Summarise an observed baseline without revealing frozen expected values."""
    def tail(text: str) -> str:
        return text[-MAX_TOOL_OUTPUT_CHARS:]
    failure = {'exit_code': result.get('exit_code'), 'stdout_tail': tail(result.get('stdout', '')), 'stderr_tail': tail(result.get('stderr', ''))}
    if result.get('exit_code') == 0 and observable_errors:
        failure['finding'] = 'The process exited zero, but its printed output does not match what the documentation describes.'
    return failure


def _task_message(context: RepairContext) -> str:
    target = context.target
    return (f'Documentation file `{context.document_path}`:\n\n{context.document()}\n\n'
            f'The broken example is lines {target.start_line}-{target.end_line}:\n\n```python\n{target.code}```\n\n'
            f'Observed failure:\n```json\n{json.dumps(context.failure, indent=2, ensure_ascii=False)}\n```')


class _Session:
    def __init__(self, strategy: str, client: ModelClient, budget: RepairBudget):
        self.client, self.budget = client, budget
        self.outcome = {'strategy': strategy, 'model': client.model, 'live_inference': bool(client.live),
                        'status': 'incomplete', 'replacement': None, 'candidates': [],
                        'usage': {'model_calls': 0, 'prompt_tokens': 0, 'completion_tokens': 0, 'snippet_runs': 0, 'malformed_responses': 0},
                        'transcript': []}

    def call(self, messages: list[dict], tools: list[dict] | None) -> dict | None:
        usage = self.outcome['usage']
        if usage['model_calls'] >= self.budget.max_model_calls:
            self.outcome['status'] = 'budget_exhausted'
            return None
        if usage['prompt_tokens'] + usage['completion_tokens'] >= self.budget.max_total_tokens:
            self.outcome['status'] = 'budget_exhausted'
            return None
        usage['model_calls'] += 1
        try:
            response = self.client.complete(messages, tools, self.budget.max_completion_tokens)
        except InferenceError as exc:
            self.outcome['status'] = 'inference_error'
            self.outcome['finding'] = str(exc)
            return None
        reported = response.get('usage') or {}
        usage['prompt_tokens'] += int(reported.get('prompt_tokens') or 0)
        usage['completion_tokens'] += int(reported.get('completion_tokens') or 0)
        message = response['choices'][0]['message']
        self.outcome['transcript'].append({'role': 'assistant', 'content': message.get('content'), 'tool_calls': message.get('tool_calls')})
        return message

    def submit(self, context: RepairContext, code: str) -> str | None:
        reason = context.gate(code)
        self.outcome['candidates'].append({'code_sha256': sha256(code.encode()), 'code': code, 'static_verdict': 'rejected' if reason else 'accepted_static', 'reason': reason})
        if reason is None:
            self.outcome['status'] = 'proposed'
            self.outcome['replacement'] = code
        elif len(self.outcome['candidates']) >= self.budget.max_candidates:
            self.outcome['status'] = 'all_candidates_rejected'
        return reason

    def malformed(self, finding: str) -> bool:
        usage = self.outcome['usage']
        usage['malformed_responses'] += 1
        self.outcome['finding'] = finding
        if usage['malformed_responses'] >= self.budget.max_malformed:
            self.outcome['status'] = 'malformed_responses'
            return True
        return False


def _fenced_code(content: str | None) -> str | None:
    blocks = _FENCE.findall(content or '')
    return blocks[-1] if blocks else None


def one_shot_repair(context: RepairContext, client: ModelClient, budget: RepairBudget = RepairBudget()) -> dict:
    """Baseline: one call, no tools or feedback, one candidate."""
    session = _Session('one_shot', client, budget)
    messages = [{'role': 'system', 'content': SYSTEM_PROMPT}, {'role': 'user', 'content': _task_message(context) + '\n\n' + ONE_SHOT_INSTRUCTION}]
    message = session.call(messages, None)
    if message is not None:
        code = _fenced_code(message.get('content'))
        if code is None:
            session.outcome['status'] = 'malformed_responses'
            session.outcome['usage']['malformed_responses'] = 1
            session.outcome['finding'] = 'No fenced Python block in the response'
        elif session.submit(context, code) is not None:
            session.outcome['status'] = 'all_candidates_rejected'
    return session.outcome


def agent_repair(context: RepairContext, client: ModelClient, budget: RepairBudget = RepairBudget()) -> dict:
    """Bounded tool loop; stops on an accepted proposal or any budget limit."""
    session = _Session('agent', client, budget)
    outcome = session.outcome
    messages = [{'role': 'system', 'content': SYSTEM_PROMPT}, {'role': 'user', 'content': _task_message(context) + '\n\n' + AGENT_INSTRUCTION}]
    while outcome['status'] == 'incomplete':
        message = session.call(messages, TOOLS)
        if message is None:
            break
        tool_calls = message.get('tool_calls') or []
        messages.append({'role': 'assistant', 'content': message.get('content') or '', **({'tool_calls': tool_calls} if tool_calls else {})})
        if not tool_calls:
            code = _fenced_code(message.get('content'))
            if code is None:
                if not session.malformed('Response had neither a tool call nor a fenced replacement'):
                    messages.append({'role': 'user', 'content': 'Use the tools, and finish by calling submit_replacement.'})
                continue
            reason = session.submit(context, code)
            if reason is not None and outcome['status'] == 'incomplete':
                messages.append({'role': 'user', 'content': f'Rejected by patch policy: {reason}'})
            continue
        for call in tool_calls:
            result = _run_tool(session, context, call)
            outcome['transcript'].append({'role': 'tool', 'tool_call_id': call.get('id'), 'content': result})
            messages.append({'role': 'tool', 'tool_call_id': call.get('id'), 'content': result})
            if outcome['status'] != 'incomplete':
                break
    return outcome


def _run_tool(session: _Session, context: RepairContext, call: dict) -> str:
    function = call.get('function') or {}
    name = function.get('name')
    try:
        arguments = json.loads(function.get('arguments') or '{}')
        if not isinstance(arguments, dict):
            raise ValueError
    except ValueError:
        session.malformed(f'Malformed arguments for tool {name!r}')
        return 'Error: arguments must be a JSON object.'
    try:
        if name == 'list_files':
            return '\n'.join(context.files())
        if name == 'read_file':
            return context.read(str(arguments.get('path', '')))
        if name == 'run_python':
            usage = session.outcome['usage']
            if context.run_python is None:
                return 'Error: execution is unavailable in this run.'
            if usage['snippet_runs'] >= session.budget.max_snippet_runs:
                return 'Error: execution budget exhausted.'
            usage['snippet_runs'] += 1
            result = context.run_python(str(arguments.get('code', '')))
            return json.dumps({key: result.get(key) for key in ('exit_code', 'timed_out')} | {
                'stdout': (result.get('stdout') or '')[-MAX_TOOL_OUTPUT_CHARS:],
                'stderr': (result.get('stderr') or '')[-MAX_TOOL_OUTPUT_CHARS:]}, ensure_ascii=False)
        if name == 'submit_replacement':
            reason = session.submit(context, str(arguments.get('code', '')))
            return 'Accepted for independent verification.' if reason is None else f'Rejected by patch policy: {reason}'
    except (SnapshotError, OSError) as exc:
        return f'Error: {exc}'
    session.malformed(f'Unknown tool {name!r}')
    return f'Error: unknown tool {name!r}.'


STRATEGIES = {'one_shot': one_shot_repair, 'agent': agent_repair}
