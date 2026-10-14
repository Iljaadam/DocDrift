import base64
import json
import subprocess
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from docdrift.adapters import AdapterError, ExecutionRequest, LocalDockerAdapter


IMAGE_ID = "sha256:" + "a" * 64
OPERATION_ID = "b" * 64


class DockerFake:
    def __init__(self, *, status="exited", exit_code=0, python="Python 3.12.8", stdout="answer\n", stderr="", truncated=False):
        self.status = status
        self.exit_code = exit_code
        self.python = python
        self.stdout = stdout
        self.stderr = stderr
        self.truncated = truncated
        self.labels = {"docdrift.managed": "true", "docdrift.log-limit": "262144"}
        self.commands = []
        self.timeout = False

    def __call__(self, command, **kwargs):
        assert kwargs["stdin"] == subprocess.DEVNULL
        assert kwargs.get("shell", False) is False
        self.commands.append(command)
        action = command[1]
        output = ""
        if action == "image":
            output = json.dumps({"Id": IMAGE_ID, "Os": "linux"})
        elif action == "run":
            output = self.python + "\n"
        elif action == "create":
            output = OPERATION_ID + "\n"
            self.status = "created"
            for index, item in enumerate(command):
                if item == "--label":
                    key, value = command[index + 1].split("=", 1)
                    self.labels[key] = value
        elif action == "start":
            self.status = "running"
        elif action == "wait":
            if self.timeout:
                raise subprocess.TimeoutExpired(command, kwargs["timeout"])
            self.status = "exited"
            output = str(self.exit_code) + "\n"
        elif action == "stop":
            self.status = "exited"
            self.exit_code = 143
        elif action == "inspect":
            output = json.dumps({"State": {"Status": self.status, "ExitCode": self.exit_code},
                                 "Config": {"Labels": self.labels}, "Image": IMAGE_ID})
        elif action == "logs":
            output = json.dumps({
                "format": "docdrift-local-v1", "exit_code": self.exit_code,
                "stdout": base64.b64encode(self.stdout.encode()).decode(),
                "stderr": base64.b64encode(self.stderr.encode()).decode(),
                "stdout_truncated": self.truncated, "stderr_truncated": False,
                "elapsed_seconds": 0.25,
            })
        return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")


def request(tmp_path, **overrides):
    snapshot = tmp_path / "repo"
    snapshot.mkdir(exist_ok=True)
    (snapshot / "module.py").write_text("VALUE = 3\n")
    values = {"snapshot": snapshot, "code": "import module; print(module.VALUE)",
              "environment": {"DOCDRIFT_INPUT": "[1,2]"}, "image": "owned-python:3.12"}
    values.update(overrides)
    return ExecutionRequest(**values)


def test_submit_persists_before_start_and_pins_isolated_fresh_snapshot(tmp_path):
    fake = DockerFake()
    adapter = LocalDockerAdapter(tmp_path / "operations")
    example = request(tmp_path)
    accepted = []

    def persist(operation_id):
        assert operation_id == OPERATION_ID
        assert all(command[1] != "start" for command in fake.commands)
        accepted.append(operation_id)

    with patch("docdrift.adapters.subprocess.run", fake):
        result = adapter.execute(example, persist)
    assert accepted == [OPERATION_ID]
    assert result.exit_code == 0
    assert result.stdout == "answer\n"
    assert result.state == "completed"
    assert result.image_id == IMAGE_ID
    create = next(command for command in fake.commands if command[1] == "create")
    assert create[-4:] == [IMAGE_ID, "-B", "/work/capture.py", "262144"]
    assert create[create.index("--network") + 1] == "none"
    assert create[create.index("--user") + 1] == "65534:65534"
    assert "--read-only" in create and "no-new-privileges" in create and "ALL" in create
    assert "--pull" in create and create[create.index("--pull") + 1] == "never"
    assert "compress=false" in create
    mounts = [create[index + 1] for index, item in enumerate(create) if item == "--mount"]
    assert len(mounts) == 2 and all(mount.endswith(",readonly") for mount in mounts)
    assert str(example.snapshot) not in " ".join(mounts)
    assert all("docker.sock" not in mount and ".aws" not in mount for mount in mounts)
    snapshot = next((tmp_path / "operations").glob("*/snapshot"))
    (example.snapshot / "module.py").write_text("CHANGED = True\n")
    assert (snapshot / "module.py").read_text() == "VALUE = 3\n"
    assert all(command[1] not in {"pull", "build"} for command in fake.commands)


def test_persistence_error_retains_created_operation_without_starting(tmp_path):
    fake = DockerFake()
    adapter = LocalDockerAdapter(tmp_path / "operations")

    def persist(operation_id):
        raise RuntimeError("ledger write failed")

    with patch("docdrift.adapters.subprocess.run", fake):
        with pytest.raises(AdapterError) as raised:
            adapter.submit(request(tmp_path), persist)
    assert raised.value.operation_id == OPERATION_ID
    assert fake.status == "created"
    assert all(command[1] != "start" for command in fake.commands)


def test_resume_starts_same_known_created_container_without_resubmitting(tmp_path):
    fake = DockerFake(status="created")
    with patch("docdrift.adapters.subprocess.run", fake):
        result = LocalDockerAdapter(tmp_path).observe(OPERATION_ID)
    assert result.state == "completed"
    assert [command for command in fake.commands if command[1] == "start"] == [["docker", "start", OPERATION_ID]]
    assert all(command[1] not in {"run", "create"} for command in fake.commands)


def test_timeout_stops_known_operation_and_never_reports_success(tmp_path):
    fake = DockerFake(status="running")
    fake.timeout = True
    with patch("docdrift.adapters.subprocess.run", fake):
        result = LocalDockerAdapter(tmp_path).observe(OPERATION_ID, timeout_seconds=1)
    assert result.timed_out
    assert result.state == "timed_out"
    assert any(command[1] == "stop" for command in fake.commands)
    assert result.operation_id == OPERATION_ID


def test_resume_does_not_restart_an_expired_runtime_budget(tmp_path):
    fake = DockerFake(status="running")
    fake.labels["docdrift.timeout"] = "30"

    def docker(command, **kwargs):
        response = fake(command, **kwargs)
        if command[1] == "inspect":
            metadata = json.loads(response.stdout)
            metadata["State"]["StartedAt"] = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
            return subprocess.CompletedProcess(command, 0, json.dumps(metadata), "")
        return response

    with patch("docdrift.adapters.subprocess.run", docker):
        result = LocalDockerAdapter(tmp_path).observe(OPERATION_ID)
    assert result.state == "timed_out"
    assert all(command[1] != "wait" for command in fake.commands)
    assert any(command[1] == "stop" for command in fake.commands)


def test_recovered_late_completed_result_is_a_timeout(tmp_path):
    fake = DockerFake(status="exited")
    fake.labels["docdrift.timeout"] = "30"

    def docker(command, **kwargs):
        response = fake(command, **kwargs)
        if command[1] == "logs":
            payload = json.loads(response.stdout)
            payload["elapsed_seconds"] = 60
            return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")
        return response

    with patch("docdrift.adapters.subprocess.run", docker):
        result = LocalDockerAdapter(tmp_path).observe(OPERATION_ID)
    assert result.exit_code == 0
    assert result.timed_out and result.state == "timed_out"


def test_request_freezes_a_copy_of_its_environment(tmp_path):
    environment = {"DOCDRIFT_INPUT": "initial"}
    example = request(tmp_path, environment=environment)
    environment["DOCDRIFT_INPUT"] = "changed"
    assert example.environment["DOCDRIFT_INPUT"] == "initial"
    with pytest.raises(TypeError):
        example.environment["DOCDRIFT_INPUT"] = "changed"


def test_missing_capture_is_incomplete_even_when_container_exit_is_zero(tmp_path):
    fake = DockerFake()

    def docker(command, **kwargs):
        response = fake(command, **kwargs)
        if command[1] == "logs":
            return subprocess.CompletedProcess(command, 0, stdout="success", stderr="")
        return response

    with patch("docdrift.adapters.subprocess.run", docker):
        result = LocalDockerAdapter(tmp_path).observe(OPERATION_ID)
    assert result.exit_code == 0
    assert result.state == "error"
    assert result.stdout_truncated and result.stderr_truncated
    assert "incomplete" in result.stderr


def test_decodes_logs_with_explicit_per_stream_bounds(tmp_path):
    fake = DockerFake(stdout="abcdef", stderr="failure")
    fake.labels["docdrift.log-limit"] = "4"
    with patch("docdrift.adapters.subprocess.run", fake):
        result = LocalDockerAdapter(tmp_path).observe(OPERATION_ID)
    assert result.stdout == "abcd" and result.stderr == "fail"
    assert result.stdout_truncated and result.stderr_truncated


def test_refuses_host_credentials_symlinks_and_foreign_operations(tmp_path):
    example = request(tmp_path, environment={"NEBIUS_API_KEY": "secret"})
    fake = DockerFake()
    with patch("docdrift.adapters.subprocess.run", fake):
        with pytest.raises(ValueError, match="DOCDRIFT_INPUT"):
            LocalDockerAdapter(tmp_path / "operations").submit(example, lambda op: None)
    assert fake.commands == []
    example = request(tmp_path)
    (example.snapshot / "escape").symlink_to("/etc/passwd")
    with patch("docdrift.adapters.subprocess.run", fake):
        with pytest.raises(ValueError, match="Symlinks"):
            LocalDockerAdapter(tmp_path / "operations").submit(example, lambda op: None)
    (example.snapshot / "escape").unlink()
    (example.snapshot / ".aws").mkdir()
    with patch("docdrift.adapters.subprocess.run", fake):
        with pytest.raises(ValueError, match="prohibited"):
            LocalDockerAdapter(tmp_path / "operations").submit(example, lambda op: None)
    fake.labels["docdrift.managed"] = "false"
    with patch("docdrift.adapters.subprocess.run", fake):
        with pytest.raises(AdapterError, match="outside DocDrift"):
            LocalDockerAdapter(tmp_path).cancel(OPERATION_ID)
    assert all(command[1] != "stop" for command in fake.commands)


def test_preflight_requires_existing_python312_and_never_pulls(tmp_path):
    fake = DockerFake(python="Python 3.11.10")
    with patch("docdrift.adapters.subprocess.run", fake):
        with pytest.raises(AdapterError, match="Python 3.12"):
            LocalDockerAdapter(tmp_path).preflight("old-python:local")
    assert all(command[1] not in {"pull", "build"} for command in fake.commands)
    probe = next(command for command in fake.commands if command[1] == "run")
    assert probe[probe.index("--pull") + 1] == "never"
    assert probe[probe.index("--network") + 1] == "none"


def test_cancel_does_not_remove_finished_logs_and_cleanup_is_explicit(tmp_path):
    fake = DockerFake()
    with patch("docdrift.adapters.subprocess.run", fake):
        adapter = LocalDockerAdapter(tmp_path)
        adapter.cancel(OPERATION_ID)
        assert all(command[1] not in {"stop", "rm"} for command in fake.commands)
        adapter.cleanup(OPERATION_ID)
    assert any(command[1] == "rm" for command in fake.commands)
