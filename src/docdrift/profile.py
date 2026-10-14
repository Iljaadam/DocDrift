"""Declarative, curator-authored checks; no profile code runs on the controller."""

from __future__ import annotations

import ast
import hashlib
import json
import math
from pathlib import Path

from .snapshot import safe_path, sha256


class ProfileError(ValueError):
    pass


def strict_json(value: str | bytes):
    def invalid(constant):
        raise ProfileError(f'Non-finite JSON value is forbidden: {constant}')
    def finite_float(number):
        result = float(number)
        if not math.isfinite(result):
            raise ProfileError('Non-finite JSON number is forbidden')
        return result
    def unique_object(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ProfileError(f'Duplicate JSON key is forbidden: {key}')
            result[key] = item
        return result
    return json.loads(value, parse_constant=invalid, parse_float=finite_float, object_pairs_hook=unique_object)


def load_profile(path: Path) -> tuple[dict, dict[str, bytes]]:
    content = path.read_bytes()
    if len(content) > 256 * 1024:
        raise ProfileError('Profile exceeds 256 KiB')
    data = strict_json(content)
    if data.get('version') != 1 or data.get('python') != '3.12':
        raise ProfileError('Requires profile v1 and Python 3.12')
    if data.get('setup') != {'kind': 'source_tree', 'dependencies': []}:
        raise ProfileError('This slice supports declared dependency-free source imports only')
    docs = data.get('documentation', [])
    if not 1 <= len(docs) <= 5 or len(set(docs)) != len(docs):
        raise ProfileError('Select one to five unique Markdown files')
    for document in docs:
        if not safe_path(document).endswith('.md'):
            raise ProfileError('Documentation must be Markdown')
    examples = data.get('examples', [])
    if not 1 <= len(examples) <= 8:
        raise ProfileError('Select one to eight examples')
    seen = set()
    targets = []
    for example in examples:
        key = (example['path'], example['ordinal'])
        if key in seen or example['path'] not in docs or type(example['ordinal']) is not int or example['ordinal'] < 0:
            raise ProfileError('Invalid or duplicate example selection')
        seen.add(key)
        if example.get('role') not in {'target', 'healthy'}:
            raise ProfileError('Example role must be target or healthy')
        if example['role'] == 'target':
            targets.append(key)
        cases = example.get('cases', [])
        if not 1 <= len(cases) <= 4 or len({case['id'] for case in cases}) != len(cases):
            raise ProfileError('Require one to four uniquely named cases per example')
        for case in cases:
            if set(case.get('env', {})) != {'DOCDRIFT_INPUT'} or not isinstance(case['env']['DOCDRIFT_INPUT'], str) or len(case['env']['DOCDRIFT_INPUT']) > 8192:
                raise ProfileError('Only bounded, nonsecret DOCDRIFT_INPUT is permitted')
            if 'expected_json' not in case:
                raise ProfileError('Each case needs an independent expected_json value')
        call = example.get('required_call', {})
        if set(call) != {'receiver', 'method'} or not all(isinstance(value, str) and value.isidentifier() for value in call.values()):
            raise ProfileError('Require a named receiver class and method for operation coverage')
        digest = example.get('operation_ast_sha256', '')
        if len(digest) != 64 or any(char not in '0123456789abcdef' for char in digest):
            raise ProfileError('Require a frozen AST digest covering the complete operation and data flow')
    target = data.get('target', {})
    if type(target.get('ordinal')) is not int:
        raise ProfileError('Target ordinal must be an integer')
    if targets != [(target.get('path'), target.get('ordinal'))]:
        raise ProfileError('Exactly one selected target is required')
    check_name = safe_path(data['checks'])
    if check_name == 'profile.json':
        raise ProfileError('Check file must be separate from the profile')
    check_path = path.parent / check_name
    if check_path.is_symlink() or not check_path.is_file() or check_path.stat().st_size > 256 * 1024:
        raise ProfileError('Require a bounded regular external check file')
    return data, {'profile.json': content, check_name: check_path.read_bytes()}


def freeze_profile(files: dict[str, bytes], destination: Path) -> dict[str, str]:
    destination.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for name, content in files.items():
        safe_path(name)
        (destination / name).parent.mkdir(parents=True, exist_ok=True)
        (destination / name).write_bytes(content)
        hashes[name] = sha256(content)
    return hashes


def operation_present(code: str, call: dict[str, str]) -> bool:
    """Conservative syntactic coverage, backed separately by observed output checks."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False
    receiver, method = call['receiver'], call['method']
    bound = {node.targets[0].id for node in ast.walk(tree) if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id == receiver}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or node.func.attr != method:
            continue
        value = node.func.value
        if isinstance(value, ast.Name) and value.id in bound:
            return True
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == receiver:
            return True
    return False


def check_result(result: dict, case: dict, code: str, call: dict, operation_ast_sha256: str) -> dict:
    execution = result.get('state') == 'completed' and type(result.get('exit_code')) is int and result['exit_code'] == 0 and not result.get('timed_out')
    errors = []
    if not execution:
        errors.append('Execution did not complete with exit zero')
    if result.get('stdout_truncated') or result.get('stderr_truncated'):
        errors.append('Captured output was truncated')
    try:
        observed = strict_json(result.get('stdout', ''))
        # Canonical JSON preserves the difference between true, 1, and 1.0.
        if json.dumps(observed, sort_keys=True, ensure_ascii=False, allow_nan=False) != json.dumps(case['expected_json'], sort_keys=True, ensure_ascii=False, allow_nan=False):
            errors.append('Observed JSON differs from the frozen expected value')
    except (ValueError, TypeError):
        errors.append('Stdout is not a single JSON value')
    observable_errors = list(errors)
    if not operation_present(code, call):
        errors.append('Required API operation is absent from the example AST')
    try:
        actual_ast = hashlib.sha256(ast.dump(ast.parse(code), include_attributes=False).encode()).hexdigest()
    except SyntaxError:
        actual_ast = ''
    if actual_ast != operation_ast_sha256:
        errors.append('Operation or data flow differs from the frozen AST contract')
    return {'execution_passed': execution, 'observable_passed': execution and not observable_errors, 'observable_errors': observable_errors, 'behavior_passed': execution and not errors, 'coverage': ['exact_json_output', 'required_api_call_ast', 'exact_operation_ast'], 'errors': errors}
