"""Independent no-network regressions for the zero-spend adapter boundary."""

from uuid import uuid4

import httpx
import pytest

from docdrift.nebius import NebiusSandboxAdapter, RemoteExecutionRequest, RemoteMutationsDisabled
from docdrift.remote_journal import SubmissionJournal


class RecordingTransport(httpx.BaseTransport):
    """A non-mock transport that records attempts without opening a socket."""

    def __init__(self):
        self.requests = []

    def handle_request(self, request):
        self.requests.append(request)
        return httpx.Response(201, json={"uuid": str(uuid4())})


def test_public_simulation_flag_cannot_unlock_a_live_configured_client(tmp_path):
    transport = RecordingTransport()
    journal = SubmissionJournal(tmp_path / "state")
    with NebiusSandboxAdapter("offline-test-key", "offline-test-project", transport=transport, journal=journal) as adapter:
        with pytest.raises(AttributeError):
            adapter.offline_simulation = True
        with pytest.raises(RemoteMutationsDisabled):
            adapter.submit(RemoteExecutionRequest(str(uuid4()), "/usr/bin/python3"), lambda _: None, run_id="run", phase="original")
    assert transport.requests == []
    assert journal.for_run("run") == []


@pytest.mark.parametrize("action", ["prepare", "submit", "cancel", "direct_post"])
def test_forcing_private_simulation_marker_still_cannot_mutate_nonmock_transport(tmp_path, action):
    transport = RecordingTransport()
    journal = SubmissionJournal(tmp_path / "state")
    operation_id = str(uuid4())
    with NebiusSandboxAdapter("offline-test-key", "offline-test-project", transport=transport, journal=journal) as adapter:
        adapter._offline_simulation = True
        adapter._accepted[operation_id] = str(uuid4())
        with pytest.raises(RemoteMutationsDisabled):
            if action == "prepare":
                adapter.prepare({"/work/docdrift/example.py": b"print('offline')\n"})
            elif action == "submit":
                adapter.submit(RemoteExecutionRequest(str(uuid4()), "/usr/bin/python3"), lambda _: None, run_id="run", phase="original")
            elif action == "cancel":
                adapter.cancel(operation_id)
            else:
                adapter._request("POST", "instances", payload={})
    assert transport.requests == []
    assert journal.for_run("run") == []


@pytest.mark.parametrize("foreign_mount", [False, True])
def test_transport_reconfiguration_cannot_unlock_mutations_on_offline_adapter(tmp_path, foreign_mount):
    mock_requests = []

    def handler(request):
        mock_requests.append(request)
        return httpx.Response(201, json={"uuid": str(uuid4())})

    mock = httpx.MockTransport(handler)
    foreign = RecordingTransport()
    journal = SubmissionJournal(tmp_path / "state")
    with NebiusSandboxAdapter("offline-test-key", "offline-test-project", transport=mock, offline_simulation=True, journal=journal) as adapter:
        adapter._client.close()
        adapter._client = httpx.Client(
            base_url="https://api.tokenfactory.nebius.com/sandboxes/v1/",
            transport=mock if foreign_mount else foreign,
            mounts={"https://api.tokenfactory.nebius.com": foreign} if foreign_mount else {},
            trust_env=False,
        )
        with pytest.raises(RemoteMutationsDisabled):
            adapter.submit(RemoteExecutionRequest(str(uuid4()), "/usr/bin/python3"), lambda _: None, run_id="run", phase="original")
    assert foreign.requests == []
    assert mock_requests == []
    assert journal.for_run("run") == []
