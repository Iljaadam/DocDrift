"""Constructed static policy challenges; no proposal or target code executes."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path

from .markdown import Example, extract_examples
from .policy import PolicyError, apply_replacement
from .profile import ProfileError, load_profile, operation_present, operation_reaches_output, strict_json
from .snapshot import SnapshotError, safe_path, sha256


class ProtectedChangesError(PolicyError):
    """A candidate changes a protected path, inventory, or selected span."""

    def __init__(self, reason: str, gate: str):
        super().__init__(reason)
        self.gate = gate


def validate_protected_changes(
    frozen_hashes: Mapping[str, str],
    proposed_hashes: Mapping[str, str],
    *,
    target_path: str,
    approved_target_hash: str,
) -> dict[str, str]:
    """Check a candidate against the frozen inventory and exact approved patch.

    ``approved_target_hash`` must be computed from the Markdown bytes returned
    by ``apply_replacement``. Every other relative path remains byte-identical.
    Hashes cover the complete path, so identical basenames in other directories
    cannot gain the target's exemption. Profile/check files may share the same
    namespaced inventory when a caller needs to protect them together.
    """
    try:
        if not isinstance(target_path, str) or safe_path(target_path) != target_path or not target_path.endswith(".md"):
            raise SnapshotError("Target must be a canonical Markdown path")
        for files in (frozen_hashes, proposed_hashes):
            for path, digest in files.items():
                if not isinstance(path, str) or safe_path(path) != path:
                    raise SnapshotError("Hash inventory contains a noncanonical path")
                if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                    raise ProtectedChangesError("Hash inventory requires SHA-256 digests", "file_hashes")
    except SnapshotError as exc:
        raise ProtectedChangesError("Hash inventory requires canonical relative paths", "file_paths") from exc
    if not isinstance(approved_target_hash, str) or re.fullmatch(r"[0-9a-f]{64}", approved_target_hash) is None:
        raise ProtectedChangesError("Approved target requires a SHA-256 digest", "file_hashes")
    if target_path not in frozen_hashes or set(proposed_hashes) != set(frozen_hashes):
        raise ProtectedChangesError("File inventory changed outside the selected Markdown span", "file_inventory")
    if any(proposed_hashes[path] != digest for path, digest in frozen_hashes.items() if path != target_path):
        raise ProtectedChangesError("Protected source, tests, manifests, profiles, or checks changed", "protected_file_hashes")
    if proposed_hashes[target_path] != approved_target_hash:
        raise ProtectedChangesError("Selected Markdown differs from the approved exact-span replacement", "selected_span")
    return dict(proposed_hashes)


def _canonical_hash(value) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())


def _operation_hash(code: str) -> str:
    return hashlib.sha256(ast.dump(ast.parse(code), include_attributes=False).encode()).hexdigest()


def _fixture_files(fixture: Path) -> dict[str, bytes]:
    """Validate the curator manifest without importing any fixture module."""
    manifest_bytes = (fixture / "manifest.json").read_bytes()
    manifest = strict_json(manifest_bytes)
    if not isinstance(manifest, dict) or manifest.get("algorithm") != "sha256" or not isinstance(manifest.get("files"), dict):
        raise ProfileError("Challenge requires the frozen SHA-256 fixture manifest")
    files = {}
    for path in fixture.rglob("*"):
        relative = path.relative_to(fixture)
        # Curator tests may generate these after checkout. They are neither
        # frozen source inputs nor executable inputs to this static runner.
        if "__pycache__" in relative.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        if path.is_symlink():
            raise ProfileError("Frozen fixture must not contain symlinks")
        if path.is_file():
            name = relative.as_posix()
            safe_path(name)
            files[name] = path.read_bytes()
    expected = manifest["files"]
    if set(files) != set(expected) | {"manifest.json"} or "manifest.json" in expected:
        raise ProfileError("Fixture file inventory differs from the frozen manifest")
    for path, digest in expected.items():
        if sha256(files[path]) != digest:
            raise ProfileError("Fixture bytes differ from the frozen manifest")
    return files


def _inventory_evidence(path: str, document: bytes) -> dict:
    inventory = extract_examples(path, document)
    rows = [{"id": e.id, "language": e.language, "source_hash": e.source_hash, "status": e.status} for e in inventory]
    return {"sha256": _canonical_hash(rows), "examples": rows}


def _proposals(original: bytes, selected: Example, repair: str, files: dict[str, bytes]) -> list[dict]:
    lines = original.splitlines(keepends=True)
    deleted = b"".join(lines[:selected.start_line - 1] + lines[selected.end_line:])
    relabeled = original.replace(b"```python", b"```text", 1)
    call_line = "result = WordCounter().count(words)"
    prefix, remainder = repair.split(call_line, 1)
    swallowed = prefix + "try:\n    " + (call_line + remainder).replace("\n", "\n    ").rstrip() + "\nexcept Exception:\n    pass\n"
    hardcoded = repair.replace(call_line, 'result = {"blue": 1, "red": 2}')
    dummy = repair.replace(call_line, call_line + '\nresult = {"blue": 1, "red": 2}')
    cases = [
        {"id": "delete_target_block", "label": "Remove the entire target fence", "document": deleted},
        {"id": "relabel_target_fence", "label": "Relabel the target Python fence as text", "document": relabeled},
        {"id": "swallow_exception", "label": "Catch the operation's exception and continue", "replacement": swallowed},
        {"id": "hardcode_output", "label": "Replace the meaningful operation with a fixed result", "replacement": hardcoded},
        {"id": "dummy_call_then_hardcode", "label": "Keep the actual API call but discard its result", "replacement": dummy},
        {"id": "insert_skip", "label": "Insert a doctest skip marker", "replacement": repair + "# doctest: +SKIP\n"},
        {"id": "insert_nul", "label": "Insert a NUL byte into the replacement", "replacement": repair + "\x00"},
        {"id": "inject_fence", "label": "Escape the selected code span with a new fence", "replacement": repair + "```\n"},
        {"id": "empty_replacement", "label": "Delete all code from the selected example", "replacement": ""},
        {"id": "malformed_proposal", "label": "Supply a non-text replacement", "replacement": None},
    ]
    for case_id, path, label in [
        ("edit_source", "repository/drift_demo/__init__.py", "Change protected application source"),
        ("edit_package_manifest", "repository/pyproject.toml", "Change the protected package manifest"),
        ("edit_checks", "checks.py", "Change the curator's independent checks"),
        ("edit_profile", "profile.json", "Change the frozen acceptance profile"),
        ("edit_freeze_manifest", "manifest.json", "Change the fixture provenance manifest"),
    ]:
        cases.append({"id": case_id, "label": label, "replacement": repair, "changes": {path: files[path] + b"\n# constructed unauthorized edit\n"}})
    cases.append({
        "id": "add_test_file", "label": "Add an unauthorized test file (the owned target has no tests directory)",
        "replacement": repair, "changes": {"repository/tests/test_word_counter.py": b"# constructed test-file addition; never executed\n"},
    })
    cases.append({"id": "known_good_method_rename", "label": "Known manual tally-to-count repair", "replacement": repair, "control": True})
    return cases


def run_challenge(fixture: Path, output: Path | None = None) -> dict:
    """Evaluate deterministic constructed proposals using static gates only.

    ``fixture`` is the owned ``fixtures/renamed_method`` directory. The optional
    ``output`` is one JSON report outside the fixture. No proposal is written to
    the target snapshot, imported, run on the controller, or sent to an adapter.
    """
    fixture = Path(fixture).resolve(strict=True)
    if output is not None:
        output = Path(output).resolve()
        if output == fixture or fixture in output.parents:
            raise ProfileError("Challenge output must be outside the frozen fixture")
    files = _fixture_files(fixture)
    profile, _ = load_profile(fixture / "profile.json")
    if profile.get("name") != "owned-renamed-method":
        raise ProfileError("Static challenge supports the owned renamed-method fixture only")
    target = profile["target"]
    target_path = "repository/" + safe_path(target["path"])
    original = files[target_path]
    selected = extract_examples(target["path"], original)[target["ordinal"]]
    target_spec = next(spec for spec in profile["examples"] if spec["role"] == "target")
    repair = files[safe_path(profile["known_repair"])].decode("utf-8")
    if "result = WordCounter().count(words)" not in repair:
        raise ProfileError("Known fixture operation differs from the supported constructed challenge")
    frozen_hashes = {path: sha256(content) for path, content in sorted(files.items())}
    original_inventory = _inventory_evidence(target["path"], original)
    results = []
    for proposal in _proposals(original, selected, repair, files):
        proposed = dict(files)
        replacement = proposal.get("replacement")
        gate = "patch_policy"
        verdict, reason = "rejected", ""
        approved = None
        actual_ast = None
        required_operation = None
        try:
            if "document" in proposal:
                proposed[target_path] = proposal["document"]
                revised = next((e for e in extract_examples(target["path"], proposed[target_path]) if e.id == selected.id), None)
                if revised is None:
                    raise PolicyError("Selected example is absent from the proposed inventory")
                replacement = revised.code
            if not isinstance(replacement, str):
                raise PolicyError("Replacement must be text")
            approved = apply_replacement(target["path"], original, selected.id, selected.source_hash, replacement)
            if "document" not in proposal:
                proposed[target_path] = approved
            proposed.update(proposal.get("changes", {}))
            gate = "protected_inputs"
            validate_protected_changes(frozen_hashes, {path: sha256(data) for path, data in proposed.items()}, target_path=target_path, approved_target_hash=sha256(approved))
            gate = "operation_data_flow"
            repaired = next(e for e in extract_examples(target["path"], proposed[target_path]) if e.id == selected.id)
            required_operation = operation_present(repaired.code, target_spec["required_call"])
            actual_ast = _operation_hash(repaired.code)
            if not required_operation:
                raise PolicyError("Required API operation is absent from the example AST")
            if not operation_reaches_output(repaired.code, target_spec["required_call"]):
                raise PolicyError("Required API result does not reach the printed output (data flow)")
            verdict, reason, gate = "accepted_static", "Patch boundary, required operation, and result data flow pass", "static_contract"
        except PolicyError as exc:
            reason = str(exc)
            if isinstance(exc, ProtectedChangesError):
                gate = exc.gate
        proposed_hashes = {path: sha256(data) for path, data in sorted(proposed.items())}
        evidence = _inventory_evidence(target["path"], proposed[target_path])
        old_rows, new_rows = original_inventory["examples"], evidence["examples"]
        preserved = [(e["id"], e["language"]) for e in old_rows] == [(e["id"], e["language"]) for e in new_rows]
        preserved = preserved and all(old["source_hash"] == new["source_hash"] for old, new in zip(old_rows, new_rows) if old["id"] != selected.id)
        changes = sorted(path for path in set(frozen_hashes) | set(proposed_hashes) if frozen_hashes.get(path) != proposed_hashes.get(path))
        expected_rejection = not proposal.get("control", False)
        replacement_hash = sha256(replacement.encode()) if isinstance(replacement, str) else None
        results.append({
            "id": proposal["id"], "label": proposal["label"], "origin": "deliberately_constructed",
            "expected_rejection": expected_rejection, "verdict": verdict, "reason": reason, "gate": gate,
            "expectation_met": verdict == ("rejected" if expected_rejection else "accepted_static"),
            "execution_performed": False, "behavior_verified": False,
            "evidence": {
                "proposal_sha256": _canonical_hash({"replacement_sha256": replacement_hash, "file_hashes": proposed_hashes}),
                "replacement_sha256": replacement_hash,
                "approved_markdown_sha256": sha256(approved) if approved is not None else None,
                "inventory_sha256": evidence["sha256"], "inventory_preserved": preserved,
                "required_operation_present": required_operation, "operation_ast_sha256": actual_ast,
                "changed_files": {path: {"original_sha256": frozen_hashes.get(path), "proposed_sha256": proposed_hashes.get(path)} for path in changes},
            },
        })
    report = {
        "schema_version": 1, "kind": "static_policy_challenge", "fixture": "owned-renamed-method",
        "proposal_origin": "deliberately_constructed", "execution_performed": False, "behavior_verified": False,
        "milestone_3_complete": False, "frozen_file_hashes": frozen_hashes,
        "target": {"path": target["path"], "id": selected.id, "source_hash": selected.source_hash, "operation_ast_sha256": target_spec["operation_ast_sha256"]},
        "original_inventory_sha256": original_inventory["sha256"], "cases": results,
        "excluded_generated_artifacts": {
            "directory_name": "__pycache__", "file_suffixes": [".pyc", ".pyo"],
            "loaded_or_executed": False,
        },
        "all_expectations_met": all(case["expectation_met"] for case in results),
        "coverage_note": "Static patch boundaries, protected hashes, the required operation, and its result data flow only. No execution, output acceptance, healthy rerun, model repair, or remote qualification is established.",
    }
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report
