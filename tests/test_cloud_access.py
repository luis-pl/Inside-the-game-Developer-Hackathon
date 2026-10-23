import hashlib
import json
import time

import pytest
from fastapi.testclient import TestClient

from inside_game.access import KeyRegistry
from inside_game.cloud import create_cloud_app
from inside_game.settings import Settings

OWNER = "ig_team_" + "a" * 48
AGENT = "ig_agent_" + "b" * 48
REVOKED = "ig_revoked_" + "c" * 48
EXPIRED = "ig_expired_" + "d" * 48


def record(id, key, role="developer", **extra):
    return {
        "id": id,
        "name": id,
        "role": role,
        "sha256": hashlib.sha256(key.encode()).hexdigest(),
        "expires_at": int(time.time()) + 3600,
        **extra,
    }


@pytest.fixture
def cloud(repository):
    records = (
        record("owner", OWNER),
        record(
            "data-agent", AGENT, "agent", operations=["get_shots", "get_tracking_frame"]
        ),
        record("revoked", REVOKED, enabled=False),
        record("expired", EXPIRED, expires_at=int(time.time()) - 1),
    )
    settings = Settings(local_access=False, credentials=records)
    app = create_cloud_app(settings, repository, "demo.example.com")
    with TestClient(app, base_url="https://demo.example.com") as client:
        yield client


@pytest.mark.parametrize("key", ["", "invalid" * 8, REVOKED, EXPIRED])
def test_cloud_rejects_missing_wrong_revoked_expired_keys(cloud, key):
    headers = {"Authorization": "Bearer " + key} if key else {}
    assert cloud.get("/api/whoami", headers=headers).status_code == 401
    assert (
        cloud.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers=headers,
        ).status_code
        == 401
    )


def test_individual_identity_and_role_enforcement(cloud):
    owner = {"Authorization": "Bearer " + OWNER}
    agent = {"Authorization": "Bearer " + AGENT}
    assert cloud.get("/api/whoami", headers=owner).json()["credential_id"] == "owner"
    assert cloud.get("/api/whoami", headers=agent).json()["role"] == "agent"
    assert (
        cloud.post(
            "/api/operations/get_shots", json={"match_id": 900001}, headers=agent
        ).status_code
        == 200
    )
    assert (
        cloud.post(
            "/api/operations/get_passes", json={"match_id": 900001}, headers=agent
        ).status_code
        == 403
    )
    # El GET de conveniencia no puede eludir la lista de operaciones permitidas.
    assert cloud.get("/api/matches", headers=agent).status_code == 403


def test_mcp_preserves_identity_and_filters_tools(cloud, caplog):
    headers = {
        "Authorization": "Bearer " + AGENT,
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2025-11-25",
    }
    result = cloud.post(
        "/mcp",
        headers=headers,
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    assert result.status_code == 200, result.text
    assert {t["name"] for t in result.json()["result"]["tools"]} == {
        "get_shots",
        "get_tracking_frame",
    }
    result = cloud.post(
        "/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "get_shots",
                "arguments": {"match_id": 900001, "view": "summary"},
            },
        },
    )
    assert result.status_code == 200, result.text
    payload = result.json()["result"]
    assert not payload["isError"]
    assert payload["structuredContent"]["data"]["summary"]["shots_on_target"] == 2
    entries = [
        json.loads(r.message) for r in caplog.records if r.message.startswith("{")
    ]
    assert any(
        e.get("event") == "analytics_request" and e.get("credential_id") == "data-agent"
        for e in entries
    )
    assert AGENT not in caplog.text and OWNER not in caplog.text
    assert not any(
        e.get("event") == "analytics_request"
        and e.get("status_code") == 200
        and e.get("credential_id") == "unauthenticated"
        for e in entries
    )
    denied = cloud.post(
        "/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "get_passes", "arguments": {"match_id": 900001}},
        },
    )
    assert denied.json()["result"]["isError"]
    assert "FORBIDDEN" in denied.text


def test_cloud_cannot_enable_local_or_shared_bypass(repository):
    with pytest.raises(ValueError):
        create_cloud_app(
            Settings(local_access=True, credentials=(record("owner", OWNER),)),
            repository,
            "demo.example.com",
        )
    with pytest.raises(ValueError):
        create_cloud_app(
            Settings(local_access=False, api_key=OWNER), repository, "demo.example.com"
        )


def test_hashes_only_and_configuration_validation():
    registry = KeyRegistry([record("owner", OWNER)])
    assert registry.verify(OWNER).id == "owner"
    assert registry.verify(hashlib.sha256(OWNER.encode()).hexdigest()) is None
    with pytest.raises(ValueError):
        KeyRegistry([record("owner", OWNER, role="admin")])
    with pytest.raises(ValueError):
        KeyRegistry([record("owner", OWNER, operations=["execute_sql"])])
