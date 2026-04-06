from fastapi.testclient import TestClient

import api.app as app_module
import api.routes.debug as debug_routes
import api.routes.game as game_routes
import api.routes.runs as runs_routes
import api.routes.tasks as tasks_routes
import api.routes.users as users_module


def test_health_endpoint() -> None:
    with TestClient(app_module.app) as client:
        health_resp = client.get("/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "ok"
    assert health_resp.json()["active_game_module"] == "business_sim"
    assert isinstance(health_resp.json()["use_mock_provider"], bool)


def test_run_task_requires_user_id() -> None:
    with TestClient(app_module.app) as client:
        response = client.post("/run-task", json={"task_id": "tsk_assess_a_city_launch_for_d9bbd92d"})
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
                "wallet_before": 100.0,
                "wallet_after": 107.8,
                "net_result": 7.8,
                "explanation": "good clarity",
            },
            "player_feedback": {"failure_reasons": []},
        }

    monkeypatch.setattr(runs_routes, "run_task", fake_run_task)

    with TestClient(app_module.app) as client:
        response = client.post(
            "/run-task",
            json={"task_id": "tsk_assess_a_city_launch_for_d9bbd92d", "user_id": "test_user_sync_001"},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["status"] == "success"
    assert payload["run_id"] == "run_sync_ok_001"
    assert payload["score"] == 88.0
    assert payload["reward"] == 12.0
    assert payload["cost"] == 4.2
    assert payload["wallet_before"] == 100.0
    assert payload["wallet_after"] == 107.8
    assert payload["net_result"] == 7.8
    assert "feedback" in payload


def test_run_task_failure_returns_standardized_failed_response(monkeypatch) -> None:
    from core_engine.errors import ExecutionError

    monkeypatch.setattr(
        runs_routes,
        "run_task",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ExecutionError("invalid_model_output", "Empty model output at step 0.", {"run_id": "run_fail_001"})
        ),
    )

    with TestClient(app_module.app) as client:
        response = client.post(
            "/run-task",
            json={"task_id": "tsk_assess_a_city_launch_for_d9bbd92d", "user_id": "test_user_sync_003"},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["status"] == "failed"
    assert payload["run_id"] == "run_fail_001"
    assert payload["error_reason"] == "invalid_model_output"
    assert payload["wallet_before"] == 0.0
    assert payload["wallet_after"] == 0.0
    assert payload["net_result"] == 0.0
    assert payload["feedback"]["issues"] == ["empty output"]


def test_run_task_insufficient_balance_returns_clean_failed_response(monkeypatch) -> None:
    from core_engine.errors import ExecutionError

    monkeypatch.setattr(
        runs_routes,
        "run_task",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ExecutionError(
                "insufficient_wallet",
                "Insufficient wallet balance. required=8.0, available=1.0",
                {"run_id": "run_fail_wallet_001", "required_cost": 8.0, "available_balance": 1.0},
            )
        ),
    )

    with TestClient(app_module.app) as client:
        response = client.post(
            "/run-task",
            json={"task_id": "tsk_assess_a_city_launch_for_d9bbd92d", "user_id": "test_user_sync_004"},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["status"] == "failed"
    assert payload["error_reason"] == "insufficient_wallet"
    assert payload["wallet_before"] == 1.0
    assert payload["wallet_after"] == 1.0
    assert payload["cost"] == 0.0
    assert payload["feedback"]["issues"] == ["insufficient balance"]


def test_run_task_parsing_failure_returns_clean_failed_response(monkeypatch) -> None:
    from core_engine.errors import ExecutionError

    monkeypatch.setattr(
        runs_routes,
        "run_task",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ExecutionError(
                "parsing_failed",
                "Model output parsing failed for required JSON format.",
                {"run_id": "run_fail_parse_001"},
            )
        ),
    )

    with TestClient(app_module.app) as client:
        response = client.post(
            "/run-task",
            json={"task_id": "tsk_hard_mode_structured_str_31cee1d4", "user_id": "test_user_sync_005"},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["status"] == "failed"
    assert payload["error_reason"] == "parsing_failed"
    assert payload["feedback"]["issues"] == ["parsing failure"]


def test_runs_endpoint_not_found(monkeypatch) -> None:
    monkeypatch.setattr(runs_routes, "get_run", lambda *args, **kwargs: None)
    monkeypatch.setattr(runs_routes, "get_runtime_run", lambda *args, **kwargs: None)
    with TestClient(app_module.app) as client:
        resp = client.get("/runs/not_exists")
    assert resp.status_code == 404


def test_assets_endpoint_not_found(monkeypatch) -> None:
    monkeypatch.setattr(runs_routes, "get_asset", lambda *args, **kwargs: None)
    with TestClient(app_module.app) as client:
        resp = client.get("/assets/not_exists")
    assert resp.status_code == 404


def test_debug_compare_and_benchmark_smoke(monkeypatch) -> None:
    monkeypatch.setattr(debug_routes, "debug_compare_agents", lambda *args, **kwargs: {"ok": True})
    monkeypatch.setattr(debug_routes, "benchmark_models", lambda *args, **kwargs: {"ok": True})
    with TestClient(app_module.app) as client:
        cmp_resp = client.get("/debug/compare", params={"task_id": "tsk_assess_a_city_launch_for_d9bbd92d"})
        bm_resp = client.post(
            "/debug/benchmark-models",
            json={"task_id": "tsk_assess_a_city_launch_for_d9bbd92d", "agent_level": "mid", "models": ["mvp-default"]},
        )
    assert cmp_resp.status_code == 200
    assert bm_resp.status_code == 200


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
        tasks = client.get("/tasks", params={"user_id": "usr_npe"})

    assert reg.status_code == 500
    assert "NoneType" not in str(reg.json())
    assert chk.status_code in {200, 500}
    assert "NoneType" not in str(chk.json())
    assert byn.status_code == 404
    assert uid.status_code == 404
    assert tasks.status_code == 200


def test_tasks_endpoint_includes_visible_tasks(monkeypatch) -> None:
    task_definitions = {
        "tsk_tutorial_1_define_the_ta_4e9617a3": {
            "is_tutorial": True,
            "tutorial_order": 1,
            "reward": 10,
            "difficulty": "easy",
            "cost_estimate": 1.0,
        },
        "tsk_assess_a_city_launch_for_d9bbd92d": {
            "is_tutorial": False,
            "reward": 30,
            "difficulty": "medium",
            "cost_estimate": 5.0,
        },
    }

    board = {
        "locked": True,
        "tutorial_tasks": [{"task_id": "tsk_tutorial_1_define_the_ta_4e9617a3",
                            **task_definitions["tsk_tutorial_1_define_the_ta_4e9617a3"]}],
        "normal_tasks": [{"task_id": "tsk_assess_a_city_launch_for_d9bbd92d",
                          **task_definitions["tsk_assess_a_city_launch_for_d9bbd92d"]}],
        "available_tasks": [{"task_id": "tsk_tutorial_1_define_the_ta_4e9617a3",
                             **task_definitions["tsk_tutorial_1_define_the_ta_4e9617a3"]}],
        "tasks": [{"task_id": "tsk_tutorial_1_define_the_ta_4e9617a3",
                   **task_definitions["tsk_tutorial_1_define_the_ta_4e9617a3"]}],
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
        resp = client.get("/tasks", params={"user_id": "player_001"})
    assert resp.status_code == 200
    data = resp.json()
    assert "tasks" in data
    assert len(data["tasks"]) == 1
    assert data["tasks"][0]["task_id"] == "tsk_tutorial_1_define_the_ta_4e9617a3"
    assert "available" in data
    assert "locked" in data


def test_tasks_language_endpoints_unlock_condition(monkeypatch) -> None:
    task_definitions = {
        "tsk_tutorial_1": {
            "is_tutorial": True,
            "title": "Tutorial",
            "difficulty": "easy",
            "cost_estimate": 1.0,
            "reward": 10.0,
        }
    }
    board = {
        "locked": True,
        "available_tasks": [],
        "locked_tasks": [
            {"task_id": "tsk_tutorial_1", **task_definitions["tsk_tutorial_1"],
             "unlock_condition": "Complete tutorial tasks"}
        ],
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

    monkeypatch.setattr(tasks_routes.ModuleFacade, "from_name", lambda *_a, **_k: _FakeFacade())
    monkeypatch.setattr(tasks_routes, "build_zh_overlay_by_origin", lambda **_k: {})

    with TestClient(app_module.app) as client:
        en_resp = client.get("/tasks", params={"user_id": "player_001"})
        zh_resp = client.get("/tasks-temp-zh", params={"user_id": "player_001"})

    assert en_resp.status_code == 200
    assert zh_resp.status_code == 200
    assert en_resp.json()["locked"][0]["unlock_condition"] == "Complete tutorial tasks"
    assert zh_resp.json()["locked"][0]["unlock_condition"] == "先完成教程任务"


def test_run_task_supports_zh_localized_response(monkeypatch) -> None:
    def fake_run_task(*args, **kwargs):
        return {
            "status": "success",
            "evaluation": {"final_score": 83.0},
            "total_cost": 1.2,
            "storage": {"run_id": "run_sync_ok_zh_001"},
            "player_result": {
                "success": True,
                "reward_gained": 12.0,
                "cost_spent": 1.2,
                "wallet_before": 100.0,
                "wallet_after": 110.8,
                "net_result": 10.8,
                "explanation": "Task succeeded.",
            },
            "player_feedback": {"failure_reasons": []},
        }

    monkeypatch.setattr(runs_routes, "run_task", fake_run_task)

    with TestClient(app_module.app) as client:
        response = client.post(
            "/run-task?lang=zh-CN",
            json={"task_id": "tsk_assess_a_city_launch_for_d9bbd92d", "user_id": "test_user_sync_zh_001"},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["lang"] == "zh-CN"
    assert payload["status"] == "成功"
    assert payload["message"] == "做得很好！"


def test_game_start_endpoint(monkeypatch) -> None:
    class _Progression:
        def start_game(self, user_id: str, username: str | None = None) -> dict:
            return {
                "user_id": user_id,
                "wallet_balance": 30.0,
                "workers": ["junior"],
                "tutorial_completed": False,
                "tasks_completed_count": 0,
            }

    class _Facade:
        progression = _Progression()

    monkeypatch.setattr(game_routes.ModuleFacade, "from_name", lambda *_args, **_kwargs: _Facade())

    with TestClient(app_module.app) as client:
        resp = client.post("/game/start", json={"user_id": "usr_game_start_001"})

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["user_id"] == "usr_game_start_001"
    assert payload["wallet_balance"] == 30.0
    assert payload["workers"] == ["junior"]
    assert payload["tutorial_completed"] is False
    assert payload["tasks_completed_count"] == 0


def test_game_start_returns_404_when_user_missing(monkeypatch) -> None:
    class _Progression:
        def start_game(self, user_id: str, username: str | None = None) -> dict:
            raise ValueError("User not found. Please register first via /users/register.")

    class _Facade:
        progression = _Progression()

    monkeypatch.setattr(game_routes.ModuleFacade, "from_name", lambda *_args, **_kwargs: _Facade())

    with TestClient(app_module.app) as client:
        resp = client.post("/game/start", json={"user_id": "usr_missing_001"})
    assert resp.status_code == 404


def test_play_page_route_exists() -> None:
    with TestClient(app_module.app) as client:
        resp = client.get("/play")
    assert resp.status_code == 200
    assert "Run your own AI workforce" in resp.text
    assert "You were once a CEO." in resp.text
    assert "Interpreting instruction..." in resp.text
    assert "Agent Output" in resp.text
