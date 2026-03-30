"""Integration tests for the lifecycle state machine and lifecycle API."""
from __future__ import annotations

import pytest

from app.runtime.exceptions import InvalidTransitionError
from app.runtime.lifecycle import (
    IDLE,
    PAUSED,
    RUNNING,
    STOPPED,
    can_start,
    is_accepting_runs,
    next_state,
)
from tests.conftest import COMPANY_ID, HEADERS

# ---------------------------------------------------------------------------
# Unit tests — state machine
# ---------------------------------------------------------------------------

class TestLifecycleStateMachine:
    def test_idle_to_running(self):
        assert next_state(IDLE, "start") == RUNNING

    def test_running_to_paused(self):
        assert next_state(RUNNING, "pause") == PAUSED

    def test_running_to_stopped(self):
        assert next_state(RUNNING, "stop") == STOPPED

    def test_paused_to_running(self):
        assert next_state(PAUSED, "resume") == RUNNING

    def test_paused_to_stopped(self):
        assert next_state(PAUSED, "stop") == STOPPED

    def test_stopped_to_idle(self):
        assert next_state(STOPPED, "reset") == IDLE

    def test_invalid_idle_stop(self):
        with pytest.raises(InvalidTransitionError, match="Cannot 'stop' from state 'idle'"):
            next_state(IDLE, "stop")

    def test_invalid_running_start(self):
        with pytest.raises(InvalidTransitionError):
            next_state(RUNNING, "start")

    def test_invalid_stopped_start(self):
        with pytest.raises(InvalidTransitionError):
            next_state(STOPPED, "start")

    def test_can_start_idle(self):
        assert can_start(IDLE) is True

    def test_cannot_start_running(self):
        assert can_start(RUNNING) is False

    def test_is_accepting_runs_idle(self):
        assert is_accepting_runs(IDLE) is True

    def test_not_accepting_paused(self):
        assert is_accepting_runs(PAUSED) is False

    def test_not_accepting_stopped(self):
        assert is_accepting_runs(STOPPED) is False


# ---------------------------------------------------------------------------
# Integration tests — lifecycle HTTP endpoints
# ---------------------------------------------------------------------------

def _create_agent(client) -> str:
    resp = client.post(
        "/agents",
        json={
            "name": "test-bot",
            "role": "engineer",
            "adapter_type": "claude_local",
            "adapter_config": {"cwd": "/tmp"},
        },
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


class TestLifecycleEndpoints:
    def test_pause_idle_agent_is_rejected(self, client):
        agent_id = _create_agent(client)
        resp = client.post(f"/agents/{agent_id}/pause", headers=HEADERS)
        # idle → pause is not a valid transition
        assert resp.status_code == 409

    def test_resume_idle_agent_is_rejected(self, client):
        agent_id = _create_agent(client)
        resp = client.post(f"/agents/{agent_id}/resume", headers=HEADERS)
        assert resp.status_code == 409

    def test_stop_idle_agent_is_rejected(self, client):
        agent_id = _create_agent(client)
        resp = client.post(f"/agents/{agent_id}/stop", headers=HEADERS)
        assert resp.status_code == 409

    def test_set_instructions_path(self, client):
        agent_id = _create_agent(client)
        resp = client.patch(
            f"/agents/{agent_id}/instructions-path",
            json={"path": "agents/test/AGENTS.md"},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["instructions_path"] == "agents/test/AGENTS.md"

    def test_clear_instructions_path(self, client):
        agent_id = _create_agent(client)
        client.patch(
            f"/agents/{agent_id}/instructions-path",
            json={"path": "agents/test/AGENTS.md"},
            headers=HEADERS,
        )
        resp = client.patch(
            f"/agents/{agent_id}/instructions-path",
            json={"path": None},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["instructions_path"] is None

    def test_get_budget(self, client):
        agent_id = _create_agent(client)
        resp = client.get(f"/agents/{agent_id}/budget", headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert "tokens_used" in data
        assert "should_pause" in data

    def test_start_agent_not_found(self, client):
        resp = client.post(
            "/agents/nonexistent-id/start",
            json={"trigger": "manual"},
            headers=HEADERS,
        )
        assert resp.status_code == 404
