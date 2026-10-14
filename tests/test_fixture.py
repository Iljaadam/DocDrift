"""Validate the frozen owned contract without executing its target package."""

import ast
import hashlib
import json
import runpy
from pathlib import Path

import pytest


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "renamed_method"


@pytest.fixture
def curator_checks():
    # This file is controller-owned trusted code outside the target snapshot.
    return runpy.run_path(str(FIXTURE / "checks.py"))


def _examples():
    markdown = (FIXTURE / "repository" / "README.md").read_text()
    return [section.split("```", 1)[0] for section in markdown.split("```python\n")[1:]]


def test_freeze_manifest_covers_all_fixture_artifacts():
    manifest = json.loads((FIXTURE / "manifest.json").read_text())
    assert manifest["algorithm"] == "sha256"
    actual_files = {
        str(path.relative_to(FIXTURE))
        for path in FIXTURE.rglob("*")
        if path.is_file() and path.name != "manifest.json" and "__pycache__" not in path.parts
    }
    assert set(manifest["files"]) == actual_files
    for name, frozen_hash in manifest["files"].items():
        assert hashlib.sha256((FIXTURE / name).read_bytes()).hexdigest() == frozen_hash


def test_original_documents_method_absent_from_frozen_api():
    source = (FIXTURE / "repository" / "drift_demo" / "__init__.py").read_text()
    package_tree = ast.parse(source)
    counter = next(node for node in package_tree.body if isinstance(node, ast.ClassDef))
    methods = {node.name for node in counter.body if isinstance(node, ast.FunctionDef)}
    assert counter.name == "WordCounter"
    assert methods == {"count"}
    examples = _examples()
    assert len(examples) == 2
    calls = [node.func.attr for node in ast.walk(ast.parse(examples[0])) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
    assert "tally" in calls
    assert "count" not in calls


def test_profile_cases_are_independent_and_varied(curator_checks):
    profile = json.loads((FIXTURE / "profile.json").read_text())
    assert profile["target"] == {"path": "README.md", "ordinal": 0}
    assert [(example["ordinal"], example["role"]) for example in profile["examples"]] == [(0, "target"), (1, "healthy")]
    for example in profile["examples"]:
        assert len(example["cases"]) >= 3
        assert len({case["env"]["DOCDRIFT_INPUT"] for case in example["cases"]}) == len(example["cases"])
        for case in example["cases"]:
            expected = curator_checks["expected_result"](case["env"]["DOCDRIFT_INPUT"], example["role"])
            assert expected == case["expected_json"]
            assert curator_checks["check_stdout"](json.dumps(expected), case["env"]["DOCDRIFT_INPUT"], example["role"]) == []


def test_operation_contract_requires_real_count_and_healthy_flow(curator_checks):
    original, healthy = _examples()
    repair = (FIXTURE / "repair.py").read_text()
    assert curator_checks["check_operation"](original)
    assert curator_checks["check_operation"](repair) == []
    assert curator_checks["check_operation"](healthy, "healthy") == []
    assert repair == original.replace(".tally(words)", ".count(words)")
    assert curator_checks["check_operation"](repair.replace("result = WordCounter().count(words)", 'result = {"red": 2, "blue": 1}'))
    assert curator_checks["check_operation"]('print("success")\n')


def test_declarative_ast_hash_matches_complete_operation_contract(curator_checks):
    profile = json.loads((FIXTURE / "profile.json").read_text())
    original, healthy = _examples()
    sources = {"target": (FIXTURE / "repair.py").read_text(), "healthy": healthy}
    for example in profile["examples"]:
        source = sources[example["role"]]
        canonical_ast = ast.dump(ast.parse(source), include_attributes=False)
        template_ast = ast.dump(
            ast.parse(curator_checks[f"_{example['role'].upper()}_OPERATION"]),
            include_attributes=False,
        )
        assert canonical_ast == template_ast
        assert hashlib.sha256(canonical_ast.encode()).hexdigest() == example["operation_ast_sha256"]
    original_ast = ast.dump(ast.parse(original), include_attributes=False)
    assert hashlib.sha256(original_ast.encode()).hexdigest() != profile["examples"][0]["operation_ast_sha256"]


def test_behavior_contract_rejects_superficial_success(curator_checks):
    check = curator_checks["check_stdout"]
    varied = '["red", "blue", "red"]'
    assert check('"success"', varied)
    assert check('{}', varied)
    assert check('{"red": 2, "blue": true}', varied)
    assert check('{"red": 2, "blue": 1}\nextra output', varied)
    assert check('{"red": 2, "blue": 1}', '[]')
