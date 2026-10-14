"""Frozen evaluation contracts, with no target package execution on the host."""

import ast
import hashlib
import json
import runpy
import tomllib
from collections import Counter
from pathlib import Path

import pytest

from docdrift.markdown import extract_examples
from docdrift.profile import ProfileError, check_result, load_profile


REPOSITORY = Path(__file__).resolve().parents[1]
EVALUATION = REPOSITORY / "fixtures" / "evaluation"
SUPPORTED = ("renamed_import", "changed_keyword", "changed_return_shape")


def _index():
    return json.loads((EVALUATION / "index.json").read_text())


def _examples(name):
    return extract_examples("README.md", (EVALUATION / name / "repository" / "README.md").read_bytes())


def _checks(name):
    path = EVALUATION / name / "checks.py"
    # Only frozen controller-owned curator code executes here. The target
    # repository is excluded and never appears on sys.path.
    tree = ast.parse(path.read_text())
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert imports == {"ast", "json"}
    assert not any(isinstance(node, ast.ImportFrom) for node in ast.walk(tree))
    return runpy.run_path(str(path))


def test_index_freezes_plan_counts_without_claiming_evaluation():
    index = _index()
    assert index["status"] == "frozen_not_evaluated"
    assert index["case_count"] == len(index["cases"]) == 14
    assert len({case["id"] for case in index["cases"]}) == 14
    owned = [case for case in index["cases"] if case["ownership"] == "owned"]
    assert Counter(case["kind"] for case in owned) == {"broken": 4, "healthy": 3, "unsupported": 3, "setup_failure": 1}
    assert all(case["reproduction_status"] == "not_run" and case["behavior_verified"] is False for case in index["cases"])
    assert not any("result" in case or "score" in case or "execution_passed" in case for case in index["cases"])


def test_two_broken_cases_and_their_shared_snapshot_are_held_out():
    index = _index()
    held_out = {case["id"] for case in index["cases"] if case["kind"] == "broken" and case["split"] == "held_out"}
    assert held_out == set(index["held_out_broken"]) == {"renamed_import_broken", "changed_return_shape_broken"}
    snapshots = {case["repository"] for case in index["cases"] if case["id"] in held_out}
    assert all(case["split"] == "held_out" for case in index["cases"] if case["ownership"] == "owned" and case["repository"] in snapshots)


def test_public_cases_remain_pending_with_pinned_commits_and_no_oracles():
    public = [case for case in _index()["cases"] if case["ownership"] == "public"]
    assert len(public) == 3
    assert {case["commit"] for case in public} == {"fee5aa338d3bd7a9e36c269e33b496a7848edc44", "a00cb2eed0704cd6d2071b2004c37e95ccc86ee5"}
    assert Counter(case["kind"] for case in public) == {"healthy": 2, "unsupported": 1}
    for case in public:
        assert case["label"] == "pending_reproduction"
        assert case["example"]["ordinal"] is None
        assert case["selection_status"] == "pending_inventory"
        assert case["environment_status"] == case["license_status"] == "unconfirmed"
        assert case["profile"] is None and case["known_repair"] is None
        assert "expected_json" not in case


def test_freeze_manifest_covers_every_new_artifact():
    manifest = json.loads((EVALUATION / "manifest.json").read_text())
    assert manifest["algorithm"] == "sha256"
    actual = {
        path.relative_to(EVALUATION).as_posix()
        for path in EVALUATION.rglob("*")
        if path.is_file() and path.name != "manifest.json" and "__pycache__" not in path.parts
    }
    assert set(manifest["files"]) == actual
    for name, digest in manifest["files"].items():
        assert hashlib.sha256((EVALUATION / name).read_bytes()).hexdigest() == digest


def test_existing_fixture_is_referenced_by_its_unchanged_freeze():
    manifest_hash = hashlib.sha256((REPOSITORY / "fixtures" / "renamed_method" / "manifest.json").read_bytes()).hexdigest()
    references = [case for case in _index()["cases"] if case.get("fixture") == "fixtures/renamed_method"]
    assert len(references) == 2
    assert all(case["fixture_manifest_sha256"] == manifest_hash for case in references)


@pytest.mark.parametrize("name", SUPPORTED)
def test_supported_profiles_have_independent_varied_oracles_and_ast_contracts(name):
    directory = EVALUATION / name
    profile, frozen_files = load_profile(directory / "profile.json")
    checks = _checks(name)
    examples = _examples(name)
    assert set(frozen_files) == {"profile.json", "checks.py"}
    assert profile["setup"] == {"kind": "source_tree", "dependencies": []}
    assert profile["python"] == "3.12"
    assert all(example.status == "candidate" for example in examples)
    assert len(examples) == len(profile["examples"])
    for spec in profile["examples"]:
        role = spec["role"]
        source = (directory / "repair.py").read_text() if role == "target" else examples[spec["ordinal"]].code
        canonical = ast.dump(ast.parse(source), include_attributes=False)
        assert hashlib.sha256(canonical.encode()).hexdigest() == spec["operation_ast_sha256"]
        assert checks["check_operation"](source, role) == []
        assert len(spec["cases"]) == len({case["env"]["DOCDRIFT_INPUT"] for case in spec["cases"]}) == 3
        for case in spec["cases"]:
            expected = checks["expected_result"](case["env"]["DOCDRIFT_INPUT"], role)
            assert expected == case["expected_json"]
            assert checks["check_stdout"](json.dumps(expected), case["env"]["DOCDRIFT_INPUT"], role) == []
        assert checks["check_operation"]('print("success")\n', role)


def test_renamed_import_baseline_refers_to_an_absent_symbol():
    directory = EVALUATION / "renamed_import"
    package = ast.parse((directory / "repository" / "drift_demo" / "__init__.py").read_text())
    classes = {node.name for node in package.body if isinstance(node, ast.ClassDef)}
    original = _examples("renamed_import")[0].code
    original_import = next(node for node in ast.parse(original).body if isinstance(node, ast.ImportFrom))
    assert original_import.module == "drift_demo"
    assert original_import.names[0].name == "TextJoiner"
    assert "TextJoiner" not in classes and "TokenJoiner" in classes
    assert (directory / "repair.py").read_text() == original.replace("TextJoiner", "TokenJoiner")


def test_changed_keyword_baseline_uses_an_absent_keyword():
    directory = EVALUATION / "changed_keyword"
    package = ast.parse((directory / "repository" / "drift_demo" / "__init__.py").read_text())
    method = next(node for node in ast.walk(package) if isinstance(node, ast.FunctionDef) and node.name == "sort")
    keyword_names = {argument.arg for argument in method.args.kwonlyargs}
    original = _examples("changed_keyword")[0].code
    call = next(node for node in ast.walk(ast.parse(original)) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "sort")
    assert {keyword.arg for keyword in call.keywords} == {"reverse"}
    assert keyword_names == {"descending"}
    assert (directory / "repair.py").read_text() == original.replace("reverse=True", "descending=True")


def test_return_shape_contract_detects_zero_exit_observable_failure():
    directory = EVALUATION / "changed_return_shape"
    profile, _ = load_profile(directory / "profile.json")
    spec = profile["examples"][0]
    case = next(case for case in spec["cases"] if case["id"] == "repeated")
    original = _examples("changed_return_shape")[0].code
    package = ast.parse((directory / "repository" / "drift_demo" / "__init__.py").read_text())
    returned = next(node.value for node in ast.walk(package) if isinstance(node, ast.Return))
    assert isinstance(returned, ast.Dict)
    assert {key.value for key in returned.keys} == {"total", "distinct"}
    # A curator-specified observed result, not an execution of the fixture.
    observed = {"state": "completed", "exit_code": 0, "stdout": '{"distinct": 2, "total": 3}', "timed_out": False}
    checked = check_result(observed, case, original, spec["required_call"], spec["operation_ast_sha256"])
    assert checked["execution_passed"] and not checked["observable_passed"]
    assert "Observed JSON differs from the frozen expected value" in checked["observable_errors"]
    assert case["expected_json"] == 3
    assert (directory / "repair.py").read_text() == original.replace("TokenStats().measure(words)", 'TokenStats().measure(words)["total"]')


@pytest.mark.parametrize("name", ("unsupported_secret_service", "unsupported_ipython", "unsupported_sketch"))
def test_unsupported_cases_are_inventory_only(name):
    directory = EVALUATION / name
    contract = json.loads((directory / "contract.json").read_text())
    examples = _examples(name)
    assert len(examples) == 1
    assert examples[0].status == contract["expected_inventory_status"] == "unsupported"
    assert contract["reason_contains"] in examples[0].reason
    assert contract["execution_authorized"] is False
    assert not (directory / "profile.json").exists()
    assert not (directory / "repair.py").exists()


def test_setup_case_is_rejected_before_backend_execution():
    directory = EVALUATION / "setup_failure"
    contract = json.loads((directory / "contract.json").read_text())
    project = tomllib.loads((directory / "repository" / "pyproject.toml").read_text())
    assert project["build-system"] == {"requires": [], "build-backend": "drift_build", "backend-path": ["."]}
    assert not (directory / "repository" / contract["missing_prerequisite"]).exists()
    backend = ast.parse((directory / "repository" / "drift_build.py").read_text())
    assert any(isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call) and isinstance(node.exc.func, ast.Name) and node.exc.func.id == "FileNotFoundError" for node in ast.walk(backend))
    with pytest.raises(ProfileError, match="dependency-free source imports"):
        load_profile(directory / "profile.json")
    assert contract["execution_authorized"] is False
    assert contract["reproduction_status"] == "not_run"
    assert not (directory / "repair.py").exists()


def test_all_new_owned_repositories_have_the_frozen_mit_license():
    license_bytes = (REPOSITORY / "fixtures" / "renamed_method" / "repository" / "LICENSE").read_bytes()
    directories = [path for path in EVALUATION.iterdir() if path.is_dir()]
    assert len(directories) == 7
    assert all((directory / "repository" / "LICENSE").read_bytes() == license_bytes for directory in directories)
