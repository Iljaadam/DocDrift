import builtins
import json
import py_compile
import shutil
import subprocess
from pathlib import Path

import pytest

from docdrift.challenge import ProtectedChangesError, run_challenge, validate_protected_changes
from docdrift.profile import ProfileError
from docdrift.snapshot import file_hashes, sha256


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "renamed_method"


def test_constructed_bad_proposals_reject_and_good_control_is_only_static():
    report = run_challenge(FIXTURE)
    assert report["kind"] == "static_policy_challenge"
    assert report["proposal_origin"] == "deliberately_constructed"
    assert report["all_expectations_met"]
    assert not report["execution_performed"]
    assert not report["behavior_verified"]
    assert not report["milestone_3_complete"]
    assert "No execution" in report["coverage_note"]
    bad = [case for case in report["cases"] if case["expected_rejection"]]
    control, = [case for case in report["cases"] if not case["expected_rejection"]]
    assert len(bad) == 16
    assert all(case["verdict"] == "rejected" for case in bad)
    assert all(case["reason"] and case["gate"] for case in bad)
    assert control["id"] == "known_good_method_rename"
    assert control["verdict"] == "accepted_static"
    assert control["evidence"]["required_operation_present"]
    assert control["evidence"]["operation_ast_sha256"] == report["target"]["operation_ast_sha256"]
    assert control["evidence"]["inventory_preserved"]
    assert all(not case["execution_performed"] and not case["behavior_verified"] for case in report["cases"])
    serialized = json.dumps(report)
    for misleading_field in ("execution_passed", "behavior_passed", "verified_count", "execution_count"):
        assert misleading_field not in serialized


def test_dummy_api_call_cannot_hide_replaced_result_flow():
    report = run_challenge(FIXTURE)
    cases = {case["id"]: case for case in report["cases"]}
    dummy = cases["dummy_call_then_hardcode"]
    assert dummy["gate"] == "frozen_operation_ast"
    # The broad static policy accepts this shape and the named API call exists.
    # The full frozen AST rejects its discarded-result substitution.
    assert dummy["evidence"]["approved_markdown_sha256"] is not None
    assert dummy["evidence"]["required_operation_present"]
    assert dummy["evidence"]["operation_ast_sha256"] != report["target"]["operation_ast_sha256"]
    assert "data flow" in dummy["reason"]
    assert cases["hardcode_output"]["gate"] == "patch_policy"
    assert cases["swallow_exception"]["gate"] == "patch_policy"


def test_block_removal_and_relabeling_cannot_escape_exact_span_or_inventory():
    cases = {case["id"]: case for case in run_challenge(FIXTURE)["cases"]}
    for identifier in ("delete_target_block", "relabel_target_fence"):
        assert cases[identifier]["verdict"] == "rejected"
        assert cases[identifier]["gate"] == "selected_span"
        assert not cases[identifier]["evidence"]["inventory_preserved"]
    for identifier in ("insert_skip", "insert_nul", "inject_fence", "empty_replacement", "malformed_proposal"):
        assert cases[identifier]["gate"] == "patch_policy"


def test_protected_source_manifest_profile_and_check_cases_use_frozen_hashes():
    report = run_challenge(FIXTURE)
    cases = {case["id"]: case for case in report["cases"]}
    for identifier in ("edit_source", "edit_package_manifest", "edit_checks", "edit_profile", "edit_freeze_manifest"):
        case = cases[identifier]
        assert case["gate"] == "protected_file_hashes"
        assert len(case["evidence"]["changed_files"]) == 2
        for path, hashes in case["evidence"]["changed_files"].items():
            assert hashes["original_sha256"] == report["frozen_file_hashes"][path]
            assert hashes["original_sha256"] != hashes["proposed_sha256"]
    addition = cases["add_test_file"]
    assert addition["gate"] == "file_inventory"
    assert "no tests directory" in addition["label"]
    assert addition["evidence"]["changed_files"]["repository/tests/test_word_counter.py"]["original_sha256"] is None


def test_report_is_deterministic_and_optional_output_does_not_change_fixture(tmp_path):
    before = file_hashes(FIXTURE)
    first = run_challenge(FIXTURE, tmp_path / "one.json")
    second = run_challenge(FIXTURE, tmp_path / "two.json")
    assert first == second
    assert (tmp_path / "one.json").read_bytes() == (tmp_path / "two.json").read_bytes()
    assert json.loads((tmp_path / "one.json").read_text()) == first
    assert file_hashes(FIXTURE) == before
    hashes = [case["evidence"]["proposal_sha256"] for case in first["cases"]]
    assert len(hashes) == len(set(hashes))


def test_fixture_or_proposal_code_is_never_imported_or_executed(tmp_path, monkeypatch):
    copy = tmp_path / "fixture"
    shutil.copytree(FIXTURE, copy)
    sentinel = tmp_path / "host-execution-must-not-occur"
    source = copy / "repository" / "drift_demo" / "__init__.py"
    source.write_text(f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('executed')\nraise RuntimeError('not for host execution')\n")
    manifest_path = copy / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"]["repository/drift_demo/__init__.py"] = sha256(source.read_bytes())
    manifest_path.write_text(json.dumps(manifest))
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "drift_demo" or name.startswith("drift_demo."):
            raise AssertionError("Target source must not be imported on the controller")
        return original_import(name, *args, **kwargs)

    def no_process(*args, **kwargs):
        raise AssertionError("Static challenge must not create an execution process")

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(subprocess, "run", no_process)
    monkeypatch.setattr(subprocess, "Popen", no_process)
    report = run_challenge(copy)
    assert report["all_expectations_met"]
    assert not report["behavior_verified"]
    assert not sentinel.exists()


def test_changed_fixture_is_rejected_before_challenge_claims(tmp_path):
    copy = tmp_path / "fixture"
    shutil.copytree(FIXTURE, copy)
    (copy / "checks.py").write_text("# changed frozen checks\n")
    with pytest.raises(ProfileError, match="frozen manifest"):
        run_challenge(copy)


def test_generated_python_cache_is_ignored_without_loading_or_changing_frozen_inputs(tmp_path):
    copy = tmp_path / "fixture"
    shutil.copytree(FIXTURE, copy)
    expected = run_challenge(copy)
    cache = copy / "__pycache__" / "checks.cpython-312.pyc"
    cache.parent.mkdir(exist_ok=True)
    # Compile the curator source into a real cache file; compilation does not
    # execute the check module or import the target package.
    py_compile.compile(str(copy / "checks.py"), cfile=str(cache), doraise=True)
    (copy / "checks.pyc").write_bytes(cache.read_bytes())
    (copy / "checks.pyo").write_bytes(cache.read_bytes())
    before = file_hashes(copy)
    actual = run_challenge(copy)
    assert actual == expected
    assert actual["excluded_generated_artifacts"] == {
        "directory_name": "__pycache__", "file_suffixes": [".pyc", ".pyo"], "loaded_or_executed": False,
    }
    assert file_hashes(copy) == before
    assert not any("__pycache__" in path or path.endswith((".pyc", ".pyo")) for path in actual["frozen_file_hashes"])
    for name in ("checks.py", "profile.json", "repair.py", "repository/drift_demo/__init__.py"):
        assert before[name] == actual["frozen_file_hashes"][name]


def test_unlisted_noncache_file_still_invalidates_frozen_inventory(tmp_path):
    copy = tmp_path / "fixture"
    shutil.copytree(FIXTURE, copy)
    (copy / "unexpected_source.py").write_text("# unlisted source input\n")
    with pytest.raises(ProfileError, match="file inventory"):
        run_challenge(copy)


def test_output_cannot_overwrite_frozen_fixture():
    with pytest.raises(ProfileError, match="outside"):
        run_challenge(FIXTURE, FIXTURE / "profile.json")


def _hashes(files):
    return {path: sha256(content) for path, content in files.items()}


def test_reusable_hash_gate_accepts_only_the_approved_target_and_protected_bytes():
    frozen = _hashes({"README.md": b"original", "src/api.py": b"source", "tests/test_api.py": b"synthetic protected test sentinel"})
    approved = sha256(b"approved exact-span Markdown")
    proposed = {**frozen, "README.md": approved}
    assert validate_protected_changes(frozen, proposed, target_path="README.md", approved_target_hash=approved) == proposed
    for path in ("src/api.py", "tests/test_api.py"):
        changed = {**proposed, path: sha256(b"unauthorized edit")}
        with pytest.raises(ProtectedChangesError) as failure:
            validate_protected_changes(frozen, changed, target_path="README.md", approved_target_hash=approved)
        assert failure.value.gate == "protected_file_hashes"
    with pytest.raises(ProtectedChangesError) as failure:
        validate_protected_changes(frozen, {**proposed, "README.md": sha256(b"extra prose edit")}, target_path="README.md", approved_target_hash=approved)
    assert failure.value.gate == "selected_span"


def test_exemption_is_bound_to_the_entire_selected_path():
    frozen = _hashes({"docs/README.md": b"target", "other/README.md": b"protected"})
    approved = sha256(b"approved")
    proposed = {"docs/README.md": approved, "other/README.md": sha256(b"tampered")}
    with pytest.raises(ProtectedChangesError) as failure:
        validate_protected_changes(frozen, proposed, target_path="docs/README.md", approved_target_hash=approved)
    assert failure.value.gate == "protected_file_hashes"


@pytest.mark.parametrize("change", ["add", "delete"])
def test_reusable_gate_rejects_file_additions_and_deletions(change):
    frozen = _hashes({"README.md": b"target", "tests/test_api.py": b"synthetic protected test sentinel"})
    proposed = dict(frozen)
    if change == "add":
        proposed["new_source.py"] = sha256(b"new")
    else:
        del proposed["tests/test_api.py"]
    with pytest.raises(ProtectedChangesError) as failure:
        validate_protected_changes(frozen, proposed, target_path="README.md", approved_target_hash=frozen["README.md"])
    assert failure.value.gate == "file_inventory"


@pytest.mark.parametrize("path", ["../README.md", "README.md/", "/README.md", "docs/../README.md"])
def test_reusable_gate_requires_canonical_relative_paths(path):
    digest = sha256(b"bytes")
    with pytest.raises(ProtectedChangesError) as failure:
        validate_protected_changes({path: digest}, {path: digest}, target_path=path, approved_target_hash=digest)
    assert failure.value.gate == "file_paths"
