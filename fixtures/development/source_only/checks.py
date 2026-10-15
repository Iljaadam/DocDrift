"""Frozen curator oracle; never imports or executes the target package."""

import ast
import json


OPERATIONS = {
    "target": '''import json
import os

from drift_demo import OccurrenceIndex

words = json.loads(os.environ["DOCDRIFT_INPUT"])
result = OccurrenceIndex().positions(words, include_empty=True)
print(json.dumps(result, sort_keys=True))
''',
    "healthy": '''import json
import os

from drift_demo import TokenMetrics

words = json.loads(os.environ["DOCDRIFT_INPUT"])
result = TokenMetrics().measure(words)
print(json.dumps(result, sort_keys=True))
''',
}


def expected_result(input_json: str, role: str = "target"):
    words = json.loads(input_json)
    if not isinstance(words, list) or any(not isinstance(word, str) for word in words):
        raise ValueError("fixture inputs must be JSON arrays of strings")
    if role == "target":
        # Recompute each token's positions rather than using the package's
        # incremental defaultdict algorithm.
        return {word: [index for index in range(len(words)) if words[index] == word] for word in set(words)}
    if role == "healthy":
        characters = 0
        for word in words:
            for _ in word:
                characters += 1
        return {"tokens": len(words), "characters": characters}
    raise ValueError(f"unknown role: {role}")


def check_stdout(stdout: str, input_json: str, role: str = "target") -> list[str]:
    try:
        observed = json.loads(stdout)
        actual = json.dumps(observed, sort_keys=True, ensure_ascii=False, allow_nan=False)
        expected = json.dumps(expected_result(input_json, role), sort_keys=True, ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError):
        return ["stdout must contain one finite JSON value"]
    return [] if actual == expected else ["observed result differs from frozen behavior"]


def check_operation(source: str, role: str = "target") -> list[str]:
    """Check the curator's reference template, not all equivalent repairs."""
    if role not in OPERATIONS:
        raise ValueError(f"unknown role: {role}")
    try:
        actual = ast.dump(ast.parse(source), include_attributes=False)
    except SyntaxError:
        return ["example is not valid standalone Python"]
    expected = ast.dump(ast.parse(OPERATIONS[role]), include_attributes=False)
    return [] if actual == expected else ["reference API operation or data flow changed"]
