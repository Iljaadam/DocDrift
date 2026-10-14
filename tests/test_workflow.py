"""Focused guards for pre-run context validation and the manual spending gate.

These checks cover this workflow's simple block structure; actionlint remains
the full YAML, expression, and GitHub Actions schema validator.
"""

from pathlib import Path
import re

import pytest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml"
# Official context availability for jobs.<job_id>.env. Runner and step contexts
# exist later, after scheduling, so they cannot be used at this scope.
JOB_ENV_CONTEXTS = {"github", "needs", "strategy", "matrix", "vars", "secrets", "inputs"}


def block(text: str, key: str, indent: int) -> list[str]:
    lines = text.splitlines()
    start = lines.index(" " * indent + key + ":") + 1
    result = []
    for line in lines[start:]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        level = len(line) - len(line.lstrip())
        if level <= indent:
            break
        result.append(line)
    return result


def assert_job_environment_contexts(text: str) -> None:
    environment = "\n".join(block(text, "env", 4))
    expressions = re.findall(r"\$\{\{(.*?)\}\}", environment, re.DOTALL)
    for expression in expressions:
        references = set(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*(?=[.\[])", expression))
        unavailable = references - JOB_ENV_CONTEXTS
        assert not unavailable, f"Contexts unavailable at job env scope: {sorted(unavailable)}"


def test_job_environment_uses_available_contexts_and_a_literal_cache_path():
    workflow = WORKFLOW.read_text()
    assert_job_environment_contexts(workflow)
    cache_line = next(line for line in block(workflow, "env", 4) if line.strip().startswith("UV_CACHE_DIR:"))
    cache = cache_line.split(":", 1)[1].strip().strip("\"'")
    assert cache.startswith("/") and "${{" not in cache


@pytest.mark.parametrize("context", ["runner", "job", "steps", "env"])
def test_unavailable_context_regression_is_detected_before_github_validation(context):
    workflow = WORKFLOW.read_text()
    changed = workflow.replace("UV_CACHE_DIR: /tmp/docdrift-uv-cache", f"UV_CACHE_DIR: ${{{{ {context}.temp }}}}/docdrift-uv-cache")
    assert changed != workflow, "Regression fixture must replace the actual job environment setting"
    with pytest.raises(AssertionError, match="unavailable at job env scope"):
        assert_job_environment_contexts(changed)


def test_manual_workflow_has_no_automatic_event_and_defaults_to_no_runner():
    workflow = WORKFLOW.read_text()
    events = [line.strip().removesuffix(":") for line in block(workflow, "on", 0)
              if len(line) - len(line.lstrip()) == 2]
    assert events == ["workflow_dispatch"]
    confirmation = "\n".join(block(workflow, "free_actions_quota_confirmed", 6))
    assert "type: boolean" in confirmation and "default: false" in confirmation
    job = block(workflow, "validate", 2)
    assert "    if: ${{ inputs.free_actions_quota_confirmed == true }}" in job
    assert "    runs-on: ubuntu-latest" in job
