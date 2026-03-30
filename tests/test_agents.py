"""Integration tests for the Agent CRUD API."""
from tests.conftest import COMPANY_ID, HEADERS


# ---------------------------------------------------------------------------
# POST /agents
# ---------------------------------------------------------------------------

def test_create_agent_minimal(client):
    resp = client.post(
        "/agents",
        json={"name": "Dev Bot", "role": "engineer", "adapter_type": "claude_local"},
        headers=HEADERS,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Dev Bot"
    assert data["role"] == "engineer"
    assert data["adapter_type"] == "claude_local"
    assert data["status"] == "idle"
    assert data["company_id"] == COMPANY_ID
    assert data["skills"] == []
    assert data["chain_of_command"] == []


def test_create_agent_with_skills(client):
    resp = client.post(
        "/agents",
        json={
            "name": "Skill Bot",
            "role": "researcher",
            "adapter_type": "codex_local",
            "skills": [
                {"skill_id": "paperclip", "skill_version": "1.0.0"},
                {"skill_id": "web-search"},
            ],
            "budget": {"max_usd": 10.0, "pause_at_pct": 80},
        },
        headers=HEADERS,
    )
    assert resp.status_code == 201
    data = resp.json()
    skills = data["skills"]
    assert len(skills) == 2
    assert skills[0]["skill_id"] == "paperclip"
    assert skills[0]["position"] == 0
    assert skills[1]["skill_id"] == "web-search"
    assert skills[1]["position"] == 1


def test_create_agent_missing_header(client):
    resp = client.post(
        "/agents",
        json={"name": "Bot", "role": "engineer", "adapter_type": "claude_local"},
    )
    assert resp.status_code == 422  # missing required header


def test_create_agent_invalid_role(client):
    resp = client.post(
        "/agents",
        json={"name": "Bot", "role": "wizard", "adapter_type": "claude_local"},
        headers=HEADERS,
    )
    assert resp.status_code == 422


def test_create_agent_invalid_adapter_type(client):
    resp = client.post(
        "/agents",
        json={"name": "Bot", "role": "engineer", "adapter_type": "unknown_adapter"},
        headers=HEADERS,
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /agents
# ---------------------------------------------------------------------------

def test_list_agents_empty(client):
    resp = client.get("/agents", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_agents_returns_only_own_company(client):
    client.post(
        "/agents",
        json={"name": "Mine", "role": "engineer", "adapter_type": "claude_local"},
        headers=HEADERS,
    )
    resp = client.get("/agents", headers={"X-Company-Id": "other-company"})
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_agents_filter_by_role(client):
    client.post("/agents", json={"name": "Eng", "role": "engineer", "adapter_type": "claude_local"}, headers=HEADERS)
    client.post("/agents", json={"name": "Res", "role": "researcher", "adapter_type": "claude_local"}, headers=HEADERS)

    resp = client.get("/agents?role=researcher", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["role"] == "researcher"


def test_list_agents_filter_by_status(client):
    client.post("/agents", json={"name": "A", "role": "engineer", "adapter_type": "claude_local"}, headers=HEADERS)
    r = client.post("/agents", json={"name": "B", "role": "engineer", "adapter_type": "claude_local"}, headers=HEADERS)
    agent_id = r.json()["id"]
    client.patch(f"/agents/{agent_id}", json={"status": "paused"}, headers=HEADERS)

    resp = client.get("/agents?status=paused", headers=HEADERS)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


# ---------------------------------------------------------------------------
# GET /agents/:id
# ---------------------------------------------------------------------------

def test_get_agent(client):
    r = client.post(
        "/agents",
        json={"name": "Bot", "role": "cto", "adapter_type": "claude_local"},
        headers=HEADERS,
    )
    agent_id = r.json()["id"]

    resp = client.get(f"/agents/{agent_id}", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["id"] == agent_id


def test_get_agent_not_found(client):
    resp = client.get("/agents/nonexistent-id", headers=HEADERS)
    assert resp.status_code == 404


def test_get_agent_wrong_company(client):
    r = client.post(
        "/agents",
        json={"name": "Bot", "role": "engineer", "adapter_type": "claude_local"},
        headers=HEADERS,
    )
    agent_id = r.json()["id"]
    resp = client.get(f"/agents/{agent_id}", headers={"X-Company-Id": "other-company"})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /agents/:id
# ---------------------------------------------------------------------------

def test_update_agent_name(client):
    r = client.post(
        "/agents",
        json={"name": "Old Name", "role": "engineer", "adapter_type": "claude_local"},
        headers=HEADERS,
    )
    agent_id = r.json()["id"]

    resp = client.patch(f"/agents/{agent_id}", json={"name": "New Name"}, headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"


def test_update_agent_skills(client):
    r = client.post(
        "/agents",
        json={
            "name": "Bot",
            "role": "engineer",
            "adapter_type": "claude_local",
            "skills": [{"skill_id": "old-skill"}],
        },
        headers=HEADERS,
    )
    agent_id = r.json()["id"]

    resp = client.patch(
        f"/agents/{agent_id}",
        json={"skills": [{"skill_id": "new-skill-a"}, {"skill_id": "new-skill-b"}]},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    skills = resp.json()["skills"]
    assert len(skills) == 2
    assert skills[0]["skill_id"] == "new-skill-a"
    assert skills[1]["skill_id"] == "new-skill-b"


def test_update_agent_status(client):
    r = client.post(
        "/agents",
        json={"name": "Bot", "role": "engineer", "adapter_type": "claude_local"},
        headers=HEADERS,
    )
    agent_id = r.json()["id"]

    resp = client.patch(f"/agents/{agent_id}", json={"status": "paused"}, headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["status"] == "paused"


def test_update_agent_not_found(client):
    resp = client.patch("/agents/missing", json={"name": "X"}, headers=HEADERS)
    assert resp.status_code == 404


def test_update_agent_invalid_status(client):
    r = client.post(
        "/agents",
        json={"name": "Bot", "role": "engineer", "adapter_type": "claude_local"},
        headers=HEADERS,
    )
    agent_id = r.json()["id"]
    resp = client.patch(f"/agents/{agent_id}", json={"status": "flying"}, headers=HEADERS)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /agents/:id
# ---------------------------------------------------------------------------

def test_delete_agent(client):
    r = client.post(
        "/agents",
        json={"name": "Temp Bot", "role": "engineer", "adapter_type": "claude_local"},
        headers=HEADERS,
    )
    agent_id = r.json()["id"]

    resp = client.delete(f"/agents/{agent_id}", headers=HEADERS)
    assert resp.status_code == 204

    # Soft-deleted agent should no longer be visible
    resp = client.get(f"/agents/{agent_id}", headers=HEADERS)
    assert resp.status_code == 404

    # Should not appear in list
    resp = client.get("/agents", headers=HEADERS)
    assert all(a["id"] != agent_id for a in resp.json())


def test_delete_agent_not_found(client):
    resp = client.delete("/agents/ghost", headers=HEADERS)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /agents/:id/runs
# ---------------------------------------------------------------------------

def test_list_runs_empty(client):
    r = client.post(
        "/agents",
        json={"name": "Bot", "role": "engineer", "adapter_type": "claude_local"},
        headers=HEADERS,
    )
    agent_id = r.json()["id"]

    resp = client.get(f"/agents/{agent_id}/runs", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_runs_for_wrong_company(client):
    r = client.post(
        "/agents",
        json={"name": "Bot", "role": "engineer", "adapter_type": "claude_local"},
        headers=HEADERS,
    )
    agent_id = r.json()["id"]

    resp = client.get(f"/agents/{agent_id}/runs", headers={"X-Company-Id": "other"})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

def test_health(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
