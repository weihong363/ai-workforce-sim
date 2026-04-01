from __future__ import annotations

from fastapi.testclient import TestClient

import api.app as app_module
import api.routes.agents as agents_route


def _payload(level: str = "junior") -> dict:
    return {
        "profile": {
            "description": "agent profile",
            "level": level,
            "skill": 0.5,
            "overtime_willingness": 0.4,
            "max_output_tokens": 120,
            "cost_weight": 1.0,
            "artificial_delay_ms": 100,
            "obedience": 0.7,
            "initiative": 0.4,
            "effort": 0.6,
            "affinity": 0.5,
        },
        "source": "manual",
    }


def test_admin_agent_crud_routes(monkeypatch) -> None:
    store: dict[str, dict] = {}

    class _Settings:
        database_url = "postgresql://fake"
        active_game_module = "business_sim"

    monkeypatch.setattr(agents_route, "get_settings", lambda: _Settings())

    def _list_agents(database_url: str, module_name: str):
        _ = (database_url, module_name)
        return [store[k] for k in sorted(store.keys())]

    def _get_agent(database_url: str, module_name: str, agent_name: str):
        _ = (database_url, module_name)
        return store.get(agent_name)

    def _create_agent(database_url: str, module_name: str, agent_name: str, profile: dict, source: str = "manual"):
        _ = database_url
        if agent_name in store:
            raise ValueError(f"Agent '{agent_name}' already exists")
        row = {"id": f"agt_{agent_name}", "module_name": module_name, "agent_name": agent_name, **profile,
               "source": source}
        store[agent_name] = row
        return row

    def _update_agent(database_url: str, module_name: str, agent_name: str, profile: dict, source: str = "manual"):
        _ = database_url
        if agent_name not in store:
            return None
        row = {"id": store[agent_name]["id"], "module_name": module_name, "agent_name": agent_name, **profile,
               "source": source}
        store[agent_name] = row
        return row

    def _delete_agent(database_url: str, module_name: str, agent_name: str) -> bool:
        _ = (database_url, module_name)
        return store.pop(agent_name, None) is not None

    monkeypatch.setattr(agents_route, "list_agents", _list_agents)
    monkeypatch.setattr(agents_route, "get_agent", _get_agent)
    monkeypatch.setattr(agents_route, "create_agent", _create_agent)
    monkeypatch.setattr(agents_route, "update_agent", _update_agent)
    monkeypatch.setattr(agents_route, "delete_agent", _delete_agent)

    body = {"agent_name": "planner_junior", **_payload("junior")}

    with TestClient(app_module.app) as client:
        created = client.post("/agents/admin", json=body)
        listed = client.get("/agents/admin")
        fetched = client.get("/agents/admin/planner_junior")
        updated = client.put("/agents/admin/planner_junior", json=_payload("senior"))
        deleted = client.delete("/agents/admin/planner_junior")
        refetch = client.get("/agents/admin/planner_junior")

    assert created.status_code == 200
    assert listed.status_code == 200
    assert fetched.status_code == 200
    assert updated.status_code == 200
    assert deleted.status_code == 200
    assert refetch.status_code == 404
    assert updated.json()["agent"]["level"] == "senior"


def test_user_agent_binding_routes(monkeypatch) -> None:
    class _Settings:
        database_url = "postgresql://fake"
        active_game_module = "business_sim"

    monkeypatch.setattr(agents_route, "get_settings", lambda: _Settings())

    user = {
        "user_id": "usr_1",
        "owned_agents": [{"agent_id": "uagt_1", "preset": "operator", "level": "junior", "status": "active"}],
    }

    monkeypatch.setattr(
        agents_route.user_store,
        "get_user_by_id",
        lambda user_id, database_url, module_name=None: dict(user) if user_id == "usr_1" else None,
    )
    monkeypatch.setattr(
        agents_route.user_store,
        "bind_agent_to_user",
        lambda **kwargs: {"agent_id": "uagt_2", "preset": "maverick", "level": "senior", "status": "active",
                          "affinity": 0.5},
    )
    monkeypatch.setattr(
        agents_route.user_store,
        "unbind_agent_from_user",
        lambda **kwargs: {"agent_id": kwargs["agent_id"], "deleted": True},
    )

    with TestClient(app_module.app) as client:
        listed = client.get("/agents/users/usr_1")
        bound = client.post("/agents/users/usr_1/bind", json={"agent_name": "maverick", "status": "active"})
        unbound = client.delete("/agents/users/usr_1/bind/uagt_2")

    assert listed.status_code == 200
    assert bound.status_code == 200
    assert unbound.status_code == 200


def test_agent_choices_and_lineup_routes(monkeypatch) -> None:
    class _Settings:
        database_url = "postgresql://fake"
        active_game_module = "business_sim"

    class _Agents:
        @staticmethod
        def list_selectable_agents():
            return [
                {"agent_name": "operator", "name": "Operator", "role_label": "Reliable Operator",
                 "visible_attributes": {"execution": 60}},
                {"agent_name": "maverick", "name": "Maverick", "role_label": "High-Risk Creative",
                 "visible_attributes": {"execution": 65}},
                {"agent_name": "slacker", "name": "Slacker", "role_label": "Cheap but Unstable",
                 "visible_attributes": {"execution": 35}},
            ]

    class _Facade:
        agents = _Agents()

    monkeypatch.setattr(agents_route, "get_settings", lambda: _Settings())
    monkeypatch.setattr(agents_route.ModuleFacade, "from_name", lambda *_a, **_k: _Facade())
    monkeypatch.setattr(
        agents_route.user_store,
        "set_user_agent_lineup",
        lambda **kwargs: kwargs["lineup_agents"],
    )

    with TestClient(app_module.app) as client:
        choices = client.get("/agents/choices")
        lineup = client.post("/agents/users/usr_1/lineup", json={"agent_names": ["operator", "maverick"]})

    assert choices.status_code == 200
    assert len(choices.json().get("agents", [])) == 3
    assert lineup.status_code == 200
    assert len(lineup.json().get("lineup", [])) == 2
