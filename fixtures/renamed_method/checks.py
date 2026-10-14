"""Curator-owned independent checks, kept outside the patchable repository.

These checks cover exact word counts and the healthy summary for the three
frozen inputs. They do not import or execute the target package. Operation
preservation deliberately uses a narrow AST contract for this owned fixture.
"""

import ast
import json


_TARGET_OPERATION = '''import json
import os
from drift_demo import WordCounter
words = json.loads(os.environ["DOCDRIFT_INPUT"])
result = WordCounter().count(words)
print(json.dumps(result, sort_keys=True))
'''

_HEALTHY_OPERATION = '''import json
import os
from drift_demo import WordCounter
words = json.loads(os.environ["DOCDRIFT_INPUT"])
counts = WordCounter().count(words)
result = {"distinct": len(counts), "total": sum(counts.values())}
print(json.dumps(result, sort_keys=True))
'''


def expected_result(input_json: str, role: str = "target") -> dict[str, int]:
    """Compute the oracle from input values without using drift_demo."""
    words = json.loads(input_json)
    if not isinstance(words, list) or any(not isinstance(word, str) for word in words):
        raise ValueError("fixture input must be a JSON array of strings")
    unique = set(words)
    if role == "target":
        return {word: words.count(word) for word in unique}
    if role == "healthy":
        return {"distinct": len(unique), "total": len(words)}
    raise ValueError(f"unknown example role: {role}")


def check_stdout(stdout: str, input_json: str, role: str = "target") -> list[str]:
    """Compare an observed process stream to independently computed behavior."""
    try:
        observed = json.loads(stdout)
    except (ValueError, TypeError):
        return ["stdout must contain exactly one JSON value"]
    expected = expected_result(input_json, role)
    # bool is a subclass of int, so equality alone would accept true for 1.
    if not isinstance(observed, dict) or any(type(value) is not int for value in observed.values()):
        return ["stdout must be a JSON object with integer counts"]
    if observed != expected:
        return ["observed result differs from the frozen behavior oracle"]
    return []


def check_operation(source: str, role: str = "target") -> list[str]:
    """Require the actual API operation, input flow, and observed result flow."""
    templates = {"target": _TARGET_OPERATION, "healthy": _HEALTHY_OPERATION}
    if role not in templates:
        raise ValueError(f"unknown example role: {role}")
    try:
        actual = ast.dump(ast.parse(source), include_attributes=False)
    except SyntaxError:
        return ["example is not valid standalone Python"]
    expected = ast.dump(ast.parse(templates[role]), include_attributes=False)
    if actual != expected:
        return ["example does not preserve the frozen WordCounter.count operation and data flow"]
    return []
