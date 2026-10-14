"""Frozen curator oracle: never imports or executes the target package."""

import ast
import json


OPERATIONS = {'target': 'import json\nimport os\n\nfrom drift_demo import TokenJoiner\n\nwords = json.loads(os.environ["DOCDRIFT_INPUT"])\nresult = TokenJoiner().join(words)\nprint(json.dumps(result, sort_keys=True))\n', 'healthy': 'import json\nimport os\n\nfrom drift_demo import TokenJoiner\n\nwords = json.loads(os.environ["DOCDRIFT_INPUT"])\njoined = TokenJoiner().join(words)\nresult = {"joined": joined, "length": len(joined)}\nprint(json.dumps(result, sort_keys=True))\n'}


def expected_result(input_json: str, role: str = "target"):
    words = _words(input_json)
    joined = ""
    for index, word in enumerate(words):
        if index:
            joined += "|"
        joined += word
    if role == "target":
        return joined
    if role == "healthy":
        return {"joined": joined, "length": sum(len(word) for word in words) + max(len(words) - 1, 0)}
    raise ValueError(f"unknown role: {role}")


def _words(input_json: str) -> list[str]:
    words = json.loads(input_json)
    if not isinstance(words, list) or any(not isinstance(word, str) for word in words):
        raise ValueError("fixture inputs must be JSON arrays of strings")
    return words


def check_stdout(stdout: str, input_json: str, role: str = "target") -> list[str]:
    try:
        observed = json.loads(stdout)
        actual = json.dumps(observed, sort_keys=True, ensure_ascii=False, allow_nan=False)
        expected = json.dumps(expected_result(input_json, role), sort_keys=True, ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError):
        return ["stdout must contain one finite JSON value"]
    return [] if actual == expected else ["observed result differs from frozen behavior"]


def check_operation(source: str, role: str = "target") -> list[str]:
    if role not in OPERATIONS:
        raise ValueError(f"unknown role: {role}")
    try:
        actual = ast.dump(ast.parse(source), include_attributes=False)
    except SyntaxError:
        return ["example is not valid standalone Python"]
    expected = ast.dump(ast.parse(OPERATIONS[role]), include_attributes=False)
    return [] if actual == expected else ["meaningful API operation or data flow changed"]
