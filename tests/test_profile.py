"""Freeze declarative coverage and separate execution from behavior evidence."""

import ast
import hashlib
import json
from pathlib import Path

import pytest

from docdrift.profile import ProfileError, check_result, freeze_profile, load_profile, operation_present


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "renamed_method"


@pytest.fixture
def profile_file(tmp_path):
    (tmp_path / "profile.json").write_bytes((FIXTURE / "profile.json").read_bytes())
    (tmp_path / "checks.py").write_bytes((FIXTURE / "checks.py").read_bytes())
    return tmp_path / "profile.json"


def _mutate(path, update):
    data = json.loads(path.read_text())
    update(data)
    path.write_text(json.dumps(data))


def test_freeze_copies_exact_profile_and_check_bytes(profile_file, tmp_path):
    profile, files = load_profile(profile_file)
    hashes = freeze_profile(files, tmp_path / "frozen")
    assert profile["name"] == "owned-renamed-method"
    assert set(files) == {"profile.json", "checks.py"}
    for name, content in files.items():
        assert (tmp_path / "frozen" / name).read_bytes() == content
        assert hashes[name] == hashlib.sha256(content).hexdigest()


def test_loading_checks_never_executes_curator_code(profile_file):
    (profile_file.parent / "checks.py").write_text("raise RuntimeError('must never execute during profile loading')\n")
    _, files = load_profile(profile_file)
    assert files["checks.py"].startswith(b"raise RuntimeError")


@pytest.mark.parametrize("setup", [{"kind": "pip", "dependencies": []}, {"kind": "source_tree", "dependencies": ["httpx"]}, {"kind": "source_tree", "dependencies": [], "command": "python setup.py"}])
def test_reject_undefined_or_dependency_install_setup(profile_file, setup):
    _mutate(profile_file, lambda data: data.update(setup=setup))
    with pytest.raises(ProfileError, match="dependency-free"):
        load_profile(profile_file)


def test_reject_secret_environment_fields(profile_file):
    _mutate(profile_file, lambda data: data["examples"][0]["cases"][0]["env"].update(AWS_SECRET_ACCESS_KEY="forbidden"))
    with pytest.raises(ProfileError, match="nonsecret"):
        load_profile(profile_file)


def test_require_frozen_complete_ast_coverage(profile_file):
    _mutate(profile_file, lambda data: data["examples"][0].pop("operation_ast_sha256"))
    with pytest.raises(ProfileError, match="AST digest"):
        load_profile(profile_file)


def test_require_exactly_one_target(profile_file):
    _mutate(profile_file, lambda data: data["examples"][1].update(role="target"))
    with pytest.raises(ProfileError, match="Exactly one"):
        load_profile(profile_file)


def test_reject_duplicate_example_selection(profile_file):
    _mutate(profile_file, lambda data: data["examples"].append(data["examples"][0]))
    with pytest.raises(ProfileError, match="duplicate"):
        load_profile(profile_file)


def test_reject_symlinked_acceptance_checks(profile_file, tmp_path):
    check_path = profile_file.parent / "checks.py"
    check_path.unlink()
    other = tmp_path / "actual_checks.py"
    other.write_text("pass\n")
    check_path.symlink_to(other)
    with pytest.raises(ProfileError, match="regular external check"):
        load_profile(profile_file)


def test_loaded_check_filename_can_be_reloaded_after_freeze(profile_file, tmp_path):
    # A loader may reject alternate names for this bounded slice. If it admits
    # one, freezing must preserve enough information for resume to load it.
    check_path = profile_file.parent / "checks.py"
    check_path.rename(profile_file.parent / "custom_checks.py")
    _mutate(profile_file, lambda data: data.update(checks="custom_checks.py"))
    try:
        profile, files = load_profile(profile_file)
    except ProfileError:
        return
    frozen = tmp_path / "frozen"
    freeze_profile(files, frozen)
    restored, _ = load_profile(frozen / "profile.json")
    assert restored == profile


@pytest.mark.parametrize("nonfinite", [float("nan"), float("inf"), -float("inf")])
def test_reject_nonfinite_json_expectations(profile_file, nonfinite):
    _mutate(profile_file, lambda data: data["examples"][0]["cases"][0].update(expected_json=nonfinite))
    with pytest.raises(ProfileError):
        load_profile(profile_file)


def test_reject_expectation_exponent_that_overflows_to_infinity(profile_file):
    _mutate(profile_file, lambda data: data["examples"][0]["cases"][0].update(expected_json=float("nan")))
    profile_file.write_text(profile_file.read_text().replace("NaN", "1e999"))
    with pytest.raises(ProfileError):
        load_profile(profile_file)


@pytest.mark.parametrize("ordinal", [False, True])
def test_boolean_is_not_an_example_ordinal(profile_file, ordinal):
    index = int(ordinal)
    _mutate(profile_file, lambda data: data["examples"][index].update(ordinal=ordinal))
    with pytest.raises(ProfileError):
        load_profile(profile_file)


def _observed(stdout="{}", **changes):
    result = {"state": "completed", "exit_code": 0, "stdout": stdout, "stderr": "", "timed_out": False, "stdout_truncated": False, "stderr_truncated": False}
    result.update(changes)
    return result


@pytest.fixture
def contract():
    code = (FIXTURE / "repair.py").read_text()
    spec = json.loads((FIXTURE / "profile.json").read_text())["examples"][0]
    return code, spec["cases"][0], spec["required_call"], spec["operation_ast_sha256"]


def test_observed_output_and_frozen_operation_are_independent(contract):
    code, case, call, digest = contract
    valid = check_result(_observed(), case, code, call, digest)
    assert valid["execution_passed"] and valid["behavior_passed"]
    hardcoded = code.replace("result = WordCounter().count(words)", "WordCounter().count(words)\nresult = {}")
    assert operation_present(hardcoded, call)
    rejected = check_result(_observed(), case, hardcoded, call, digest)
    assert rejected["execution_passed"] and not rejected["behavior_passed"]
    assert any("data flow" in error for error in rejected["errors"])


@pytest.mark.parametrize("result", [_observed(state="running"), _observed(exit_code=1), _observed(timed_out=True), _observed(stdout_truncated=True), _observed(stderr_truncated=True)])
def test_incomplete_failed_or_truncated_results_never_verify(contract, result):
    code, case, call, digest = contract
    assert not check_result(result, case, code, call, digest)["behavior_passed"]


def test_boolean_exit_status_cannot_establish_execution(contract):
    code, case, call, digest = contract
    checked = check_result(_observed(exit_code=False), case, code, call, digest)
    assert not checked["execution_passed"]
    assert not checked["behavior_passed"]


@pytest.mark.parametrize("stdout", ["success", '{}\nadditional output', '"success"', "[]", "null"])
def test_reject_nonmatching_or_extra_observed_output(contract, stdout):
    code, case, call, digest = contract
    checked = check_result(_observed(stdout), case, code, call, digest)
    assert checked["execution_passed"]
    assert not checked["behavior_passed"]


@pytest.mark.parametrize("stdout", ['{"red": true}', '{"red": 1.0}'])
def test_preserve_observed_json_value_types(contract, stdout):
    code, _, call, digest = contract
    case = {"expected_json": {"red": 1}}
    assert not check_result(_observed(stdout), case, code, call, digest)["behavior_passed"]


@pytest.mark.parametrize("nonfinite", ["NaN", "Infinity", "-Infinity"])
def test_observed_nonfinite_json_never_verifies(contract, nonfinite):
    code, _, call, digest = contract
    case = {"expected_json": json.loads(nonfinite)}
    assert not check_result(_observed(nonfinite), case, code, call, digest)["behavior_passed"]


def test_formatting_changes_preserve_ast_hash(contract):
    code, case, call, digest = contract
    formatted = "# Curator-preserving formatting change\n\n" + code
    actual = hashlib.sha256(ast.dump(ast.parse(formatted), include_attributes=False).encode()).hexdigest()
    assert actual == digest
    assert check_result(_observed(), case, formatted, call, digest)["behavior_passed"]
