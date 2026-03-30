from fastapi.testclient import TestClient

import api.app as app_module
import api.users as users_module


def test_health_endpoint() -> None:
    with TestClient(app_module.app) as client:
        health_resp = client.get("/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "ok"
    assert health_resp.json()["active_game_module"] == "business_sim"
    assert isinstance(health_resp.json()["use_mock_provider"], bool)


def test_run_task_requires_user_id() -> None:
    with TestClient(app_module.app) as client:
        response = client.post("/run-task", json={"task_id": "launch_coffee_subscription"})
    assert response.status_code == 422


def test_run_task_returns_standardized_success_response(monkeypatch) -> None:
    def fake_run_task(*args, **kwargs):
        return {
            "status": "success",
            "evaluation": {"final_score": 88.0},
            "total_cost": 4.2,
            "storage": {"run_id": "run_sync_ok_001"},
            "player_result": {
                "success": True,
                "reward_gained": 12.0,
                "cost_spent": 4.2,
                "explanation": "good clarity",
            },
            "player_feedback": {"failure_reasons": []},
        }

    monkeypatch.setattr(app_module, "run_task", fake_run_task)

    with TestClient(app_module.app) as client:
        response = client.post(
            "/run-task",
            json={"task_id": "launch_coffee_subscription", "user_id": "test_user_sync_001"},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["status"] == "success"
    assert payload["run_id"] == "run_sync_ok_001"
    assert payload["score"] == 88.0
    assert payload["reward"] == 12.0
    assert payload["cost"] == 4.2
    assert "feedback" in payload


def test_run_task_failure_returns_standardized_failed_response(monkeypatch) -> None:
    from core_engine.errors import ExecutionError

    monkeypatch.setattr(
        app_module,
        "run_task",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ExecutionError("invalid_model_output", "Empty model output at step 0.", {"run_id": "run_fail_001"})
        ),
    )

    with TestClient(app_module.app) as client:
        response = client.post(
            "/run-task",
            json={"task_id": "launch_coffee_subscription", "user_id": "test_user_sync_003"},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["status"] == "failed"
    assert payload["run_id"] == "run_fail_001"
    assert payload["error_reason"] == "invalid_model_output"


def test_runs_endpoint_not_found(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "get_run", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_module, "get_runtime_run", lambda *args, **kwargs: None)
    with TestClient(app_module.app) as client:
        resp = client.get("/runs/not_exists")
    assert resp.status_code == 404


def test_assets_endpoint_not_found(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "get_asset", lambda *args, **kwargs: None)
    with TestClient(app_module.app) as client:
        resp = client.get("/assets/not_exists")
    assert resp.status_code == 404


def test_debug_compare_and_benchmark_smoke(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "debug_compare_agents", lambda *args, **kwargs: {"ok": True})
    monkeypatch.setattr(app_module, "benchmark_models", lambda *args, **kwargs: {"ok": True})
    with TestClient(app_module.app) as client:
        cmp_resp = client.get("/debug/compare", params={"task_id": "launch_coffee_subscription"})
        bm_resp = client.post(
            "/debug/benchmark-models",
            json={"task_id": "launch_coffee_subscription", "agent_level": "mid", "models": ["mvp-default"]},
        )
    assert cmp_resp.status_code == 200
    assert bm_resp.status_code == 200


def test_debug_tuning_ui_page_smoke() -> None:
    with TestClient(app_module.app) as client:
        resp = client.get("/debug/tuning-ui")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "Tuning Panel" in resp.text
    assert "Benchmark Runner" in resp.text


def test_users_endpoints_npe_safety(monkeypatch) -> None:
    class _Progression:
        def check_username_exists(self, username: str):
            return False

        def init_user(self, user_id: str, username: str):
            return None

        def get_user_by_username(self, username: str):
            return None

        def get_user(self, user_id: str):
            return None

        def list_task_board(self, user_id: str, task_definitions: dict):
            return None

    class _Facade:
        module_name = "business_sim"
        progression = _Progression()

        @staticmethod
        def list_tasks():
            return None

    monkeypatch.setattr(users_module.ModuleFacade, "from_name", lambda *_args, **_kwargs: _Facade())

    with TestClient(app_module.app) as client:
        reg = client.post("/users/register", json={"username": "npe_case_user"})
        chk = client.get("/users/check-username/npe_case_user")
        byn = client.get("/users/by-username/npe_case_user")
        uid = client.get("/users/usr_npe")
        board = client.get("/users/usr_npe/task-board")
        tasks = client.get("/users/usr_npe/tasks")

    assert reg.status_code == 500
    assert "NoneType" not in str(reg.json())
    assert chk.status_code in {200, 500}
    assert "NoneType" not in str(chk.json())
    assert byn.status_code == 404
    assert uid.status_code == 404
    assert board.status_code == 200
    assert tasks.status_code == 200


def test_task_board_includes_all_tasks(monkeypatch) -> None:
    task_definitions = {
        "tutorial_define_goal": {
            "is_tutorial": True,
            "tutorial_order": 1,
            "reward": 10,
            "difficulty": "easy",
            "cost_estimate": 1.0,
        },
        "launch_coffee_subscription": {
            "is_tutorial": False,
            "reward": 30,
            "difficulty": "medium",
            "cost_estimate": 5.0,
        },
    }

    board = {
        "locked": True,
        "tutorial_tasks": [{"task_id": "tutorial_define_goal", **task_definitions["tutorial_define_goal"]}],
        "normal_tasks": [{"task_id": "launch_coffee_subscription", **task_definitions["launch_coffee_subscription"]}],
        "available_tasks": [{"task_id": "tutorial_define_goal", **task_definitions["tutorial_define_goal"]}],
        "tasks": [{"task_id": "tutorial_define_goal", **task_definitions["tutorial_define_goal"]}],
    }

    class _FakeProgression:
        def list_task_board(self, user_id: str, task_definitions: dict) -> dict:
            return board

    class _FakeFacade:
        module_name = "business_sim"
        progression = _FakeProgression()

        @staticmethod
        def list_tasks() -> dict:
            return task_definitions

    monkeypatch.setattr(users_module.ModuleFacade, "from_name", lambda *_args, **_kwargs: _FakeFacade())

    with TestClient(app_module.app) as client:
        resp = client.get("/users/player_001/task-board")
    assert resp.status_code == 200
    data = resp.json()
    assert "all_tasks" in data
    assert len(data["all_tasks"]) == 2
    assert data["all_tasks"][0]["task_id"] == "tutorial_define_goal"
