from fastapi.testclient import TestClient

import api.app as app_module
import api.routes.tasks as tasks_route_module
import api.run_task as run_task_module
from game_modules.business_sim import progression, tasks


def test_seed_tasks_follow_standard_schema() -> None:
    seed = tasks.get_seed_tasks()
    assert seed
    required = {
        "task_id",
        "title",
        "description",
        "difficulty",
        "base_reward",
        "estimated_cost",
        "required_constraints",
        "success_threshold",
        "tutorial_only",
    }
    for task_id, cfg in seed.items():
        item = tasks.to_public_task(task_id, cfg)
        assert required.issubset(set(item.keys()))


def test_tasks_endpoint_respects_tutorial_visibility(monkeypatch) -> None:
    task_defs = {
        "tsk_tutorial_1_define_the_ta_4e9617a3": tasks.normalize_task(
            "tsk_tutorial_1_define_the_ta_4e9617a3",
            {
                "title": "Tutorial Goal",
                "description": "tutorial",
                "difficulty": "easy",
                "base_reward": 10.0,
                "estimated_cost": 2.0,
                "required_constraints": ["target customer"],
                "tutorial_only": True,
                "workflow": ["operator"],
            },
        ),
        "tsk_assess_a_city_launch_for_d9bbd92d": tasks.normalize_task(
            "tsk_assess_a_city_launch_for_d9bbd92d",
            {
                "title": "Launch Coffee",
                "description": "normal",
                "difficulty": "medium",
                "base_reward": 30.0,
                "estimated_cost": 8.0,
                "required_constraints": ["pricing", "risk"],
                "tutorial_only": False,
                "workflow": ["operator", "maverick"],
            },
        ),
    }

    class _Progression:
        def list_task_board(self, user_id: str, task_definitions: dict) -> dict:
            if user_id == "user_new":
                return {
                    "locked": True,
                    "tasks": [{"task_id": "tsk_tutorial_1_define_the_ta_4e9617a3",
                               **task_definitions["tsk_tutorial_1_define_the_ta_4e9617a3"]}],
                }
            return {
                "locked": False,
                "tasks": [{"task_id": "tsk_assess_a_city_launch_for_d9bbd92d",
                           **task_definitions["tsk_assess_a_city_launch_for_d9bbd92d"]}],
            }

    class _Tasks:
        @staticmethod
        def to_public_task(task_id: str, task_cfg: dict) -> dict:
            return tasks.to_public_task(task_id, task_cfg)

    class _Facade:
        progression = _Progression()
        tasks = _Tasks()

        @staticmethod
        def list_tasks() -> dict:
            return task_defs

    monkeypatch.setattr(tasks_route_module.ModuleFacade, "from_name", lambda *_args, **_kwargs: _Facade())

    with TestClient(app_module.app) as client:
        new_resp = client.get("/tasks", params={"user_id": "user_new"})
        old_resp = client.get("/tasks", params={"user_id": "user_old"})

    assert new_resp.status_code == 200
    assert old_resp.status_code == 200
    assert new_resp.json()["tasks"][0]["task_id"] == "tsk_tutorial_1_define_the_ta_4e9617a3"
    assert old_resp.json()["tasks"][0]["task_id"] == "tsk_assess_a_city_launch_for_d9bbd92d"


def test_task_detail_endpoint_visibility(monkeypatch) -> None:
    task_defs = {
        "tsk_tutorial_1_define_the_ta_4e9617a3": tasks.normalize_task(
            "tsk_tutorial_1_define_the_ta_4e9617a3",
            {"description": "tutorial", "tutorial_only": True, "required_constraints": ["target customer"]},
        ),
        "tsk_assess_a_city_launch_for_d9bbd92d": tasks.normalize_task(
            "tsk_assess_a_city_launch_for_d9bbd92d",
            {"description": "normal", "tutorial_only": False, "required_constraints": ["pricing", "risk"]},
        ),
    }

    class _Progression:
        def list_task_board(self, user_id: str, task_definitions: dict) -> dict:
            return {"locked": True, "tasks": [{"task_id": "tsk_tutorial_1_define_the_ta_4e9617a3",
                                               **task_definitions["tsk_tutorial_1_define_the_ta_4e9617a3"]}]}

    class _Tasks:
        @staticmethod
        def to_public_task(task_id: str, task_cfg: dict) -> dict:
            return tasks.to_public_task(task_id, task_cfg)

    class _Facade:
        progression = _Progression()
        tasks = _Tasks()

        @staticmethod
        def list_tasks() -> dict:
            return task_defs

    monkeypatch.setattr(tasks_route_module.ModuleFacade, "from_name", lambda *_args, **_kwargs: _Facade())

    with TestClient(app_module.app) as client:
        ok_resp = client.get("/tasks/tsk_tutorial_1_define_the_ta_4e9617a3", params={"user_id": "user_new"})
        miss_resp = client.get("/tasks/tsk_assess_a_city_launch_for_d9bbd92d", params={"user_id": "user_new"})

    assert ok_resp.status_code == 200
    assert ok_resp.json()["tutorial_only"] is True
    assert miss_resp.status_code == 404


def test_success_threshold_is_applied_from_task_definition() -> None:
    cfg = tasks.normalize_task(
        "threshold_task",
        {
            "description": "check threshold",
            "success_threshold": 90.0,
            "required_constraints": [],
            "tutorial_only": False,
            "base_reward": 20.0,
        },
    )
    result = progression.resolve_task_outcome(
        task_config=cfg,
        evaluation_score=85.0,
        clarity_score=1.0,
        missed_constraints=0,
    )
    assert result["success"] is False


def test_benchmark_models_uses_same_task_id_path(monkeypatch) -> None:
    captured = {}

    class _Facade:
        class _Agents:
            AGENTS = {"operator": {}, "maverick": {}}

        agents = _Agents()

    monkeypatch.setattr(run_task_module.ModuleFacade, "from_name", lambda *_args, **_kwargs: _Facade())

    def _fake_run_task(*args, **kwargs):
        captured["task_id"] = kwargs.get("task_id")
        return {
            "workflow_results": [{"provider": "mock", "model": "mock-model", "output": "ok"}],
            "comparison_fields": {
                "output_length": 2,
                "missed_constraints": 0,
                "deviation_detected": False,
                "final_score": 90.0,
                "token_usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                "cost": 0.01,
            },
            "constraint_assessment": {"failed_rules": []},
        }

    monkeypatch.setattr(run_task_module, "run_task", _fake_run_task)

    payload = run_task_module.benchmark_models(
        task_id="tsk_assess_a_city_launch_for_d9bbd92d",
        module_name="business_sim",
        agent_level="junior",
        models=["mvp-default"],
    )
    assert payload["task_id"] == "tsk_assess_a_city_launch_for_d9bbd92d"
    assert captured["task_id"] == "tsk_assess_a_city_launch_for_d9bbd92d"


def test_tasks_catalog_endpoint_returns_global_overview(monkeypatch) -> None:
    task_defs = {
        "tsk_tutorial_1_define_the_ta_4e9617a3": tasks.normalize_task(
            "tsk_tutorial_1_define_the_ta_4e9617a3",
            {"description": "tutorial", "tutorial_only": True, "required_constraints": ["target customer"]},
        ),
        "tsk_assess_a_city_launch_for_d9bbd92d": tasks.normalize_task(
            "tsk_assess_a_city_launch_for_d9bbd92d",
            {"description": "normal", "tutorial_only": False, "required_constraints": ["pricing", "risk"]},
        ),
    }

    class _Facade:
        class _Tasks:
            @staticmethod
            def to_public_task(task_id: str, task_cfg: dict) -> dict:
                return tasks.to_public_task(task_id, task_cfg)

        tasks = _Tasks()

        @staticmethod
        def list_tasks() -> dict:
            return task_defs

    monkeypatch.setattr(tasks_route_module.ModuleFacade, "from_name", lambda *_args, **_kwargs: _Facade())

    with TestClient(app_module.app) as client:
        resp = client.get("/tasks-catalog")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total_tasks"] == 2
    assert payload["tutorial_tasks"] == 1
    assert payload["normal_tasks"] == 1


def test_admin_task_management_crud_endpoints(monkeypatch) -> None:
    store: dict[str, dict] = {}

    class _Tasks:
        @staticmethod
        def to_public_task(task_id: str, task_cfg: dict) -> dict:
            return tasks.to_public_task(task_id, task_cfg)

        @staticmethod
        def upsert_task_definition(task_config: dict, task_id: str | None = None, source: str = "manual") -> dict:
            assigned = task_id or tasks.generate_task_id(task_config)
            cfg = tasks.normalize_task(assigned, task_config)
            store[str(cfg["task_id"])] = cfg
            return cfg

        @staticmethod
        def delete_task_definition(task_id: str) -> bool:
            return store.pop(task_id, None) is not None

    class _Facade:
        tasks = _Tasks()

        @staticmethod
        def list_tasks() -> dict:
            return dict(store)

        @staticmethod
        def get_task(task_id: str) -> dict:
            if task_id not in store:
                raise ValueError(f"Unknown task: {task_id}")
            return dict(store[task_id])

    monkeypatch.setattr(tasks_route_module.ModuleFacade, "from_name", lambda *_args, **_kwargs: _Facade())

    create_body = {
        "task_config": {
            "title": "Custom Launch Plan",
            "description": "Plan a custom launch.",
            "difficulty": "medium",
            "base_reward": 50,
            "estimated_cost": 10,
            "required_constraints": ["target customer", "pricing", "risk"],
            "success_threshold": 75,
            "tutorial_only": False,
        },
        "source": "manual",
    }
    with TestClient(app_module.app) as client:
        created = client.post("/task/admin", json=create_body)
        listed = client.get("/task/admin")
        created_task_id = created.json()["task_id"]
        got = client.get(f"/task/admin/{created_task_id}")
        updated = client.put(
            f"/task/admin/{created_task_id}",
            json={
                "task_config": {
                    **create_body["task_config"],
                    "base_reward": 60,
                },
                "source": "manual",
            },
        )
        deleted = client.delete(f"/task/admin/{created_task_id}")

    assert created.status_code == 200
    assert listed.status_code == 200
    assert got.status_code == 200
    assert updated.status_code == 200
    assert deleted.status_code == 200
    assert updated.json()["public"]["base_reward"] == 60.0


def test_benchmark_matrix_rejects_task_definition_override_by_default(monkeypatch) -> None:
    monkeypatch.delenv("ALLOW_DEBUG_TASK_DEFINITION_OVERRIDE", raising=False)
    from core_engine.config import get_settings

    get_settings.cache_clear()
    try:
        run_task_module.benchmark_matrix(
            task_id="tsk_assess_a_city_launch_for_d9bbd92d",
            module_name="business_sim",
            task_definition={"description": "override should be blocked"},
        )
    except ValueError as exc:
        assert "task_definition override is disabled" in str(exc)
    else:
        raise AssertionError("Expected ValueError when task_definition override is disabled")


def test_admin_create_task_rejects_unknown_workflow_agent() -> None:
    bad_config = {
        "task_config": {
            "title": "Invalid Workflow Task",
            "description": "Task with unknown agent",
            "difficulty": "easy",
            "base_reward": 10,
            "estimated_cost": 2,
            "required_constraints": [],
            "success_threshold": 60,
            "tutorial_only": False,
            "workflow": ["non_existing_agent"],
        },
        "source": "manual",
    }
    with TestClient(app_module.app) as client:
        resp = client.post("/task/admin", json=bad_config)
    assert resp.status_code == 400
    assert "unknown agents" in str(resp.json().get("detail", "")).lower()


def test_manual_upsert_uses_ulid_style_id_and_no_post_persist_read(monkeypatch) -> None:
    captured: dict = {}

    def _fake_upsert(database_url: str, module_name: str, task_id: str, task_config: dict,
                     source: str = "manual") -> None:
        captured["database_url"] = database_url
        captured["module_name"] = module_name
        captured["task_id"] = task_id
        captured["task_config"] = dict(task_config)
        captured["source"] = source

    monkeypatch.setattr(tasks, "_require_database_url", lambda: "postgresql://fake")
    monkeypatch.setattr(tasks, "db_upsert_task", _fake_upsert)
    monkeypatch.setattr(tasks, "get_task",
                        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("should not re-read")))

    saved = tasks.upsert_task_definition(
        task_config={
            "title": "Manual Task",
            "description": "Do work",
            "difficulty": "easy",
            "base_reward": 10,
            "estimated_cost": 1,
            "required_constraints": [],
            "success_threshold": 60,
            "tutorial_only": False,
            "workflow": ["operator"],
        },
        source="manual",
    )
    task_id = str(saved.get("task_id", ""))
    assert task_id.startswith("tsk_task_")
    assert len(task_id) > 16
    assert captured["task_id"] == task_id
