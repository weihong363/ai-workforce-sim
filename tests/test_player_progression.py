from copy import deepcopy

import pytest

from game_modules.business_sim import progression, tasks

TASKS = tasks.get_seed_tasks()


def _tutorial_cfg(name: str) -> dict:
    cfg = dict(TASKS[name])
    cfg["_all_tasks"] = TASKS
    return cfg


@pytest.fixture
def fake_user_store(monkeypatch):
    users = {}
    events = {}

    def _copy_user(user: dict) -> dict:
        return deepcopy(user)

    def get_user_by_id(user_id: str, _db_url: str, module_name: str | None = None):
        user = users.get(user_id)
        return _copy_user(user) if user else None

    def check_username_exists(username: str, _db_url: str) -> bool:
        return any(u.get("username") == username for u in users.values())

    def create_user(
        user_id: str,
        username: str,
        database_url: str,
        wallet_balance: float = 120.0,
        module_name: str | None = None,
    ):
        if check_username_exists(username, database_url):
            raise ValueError(f"Username '{username}' already exists")
        users[user_id] = {
            "user_id": user_id,
            "username": username,
            "wallet_balance": wallet_balance,
            "tutorial_completed": False,
            "owned_agents": [{"agent_id": "junior_001", "preset": "junior_worker", "level": "junior"}],
            "tutorial_progress": {"completed_tasks": []},
            "task_history": [],
            "created_at": "now",
            "updated_at": "now",
        }
        events[user_id] = []
        return {"user_id": user_id, "username": username, "wallet_balance": wallet_balance, "created_at": "now"}

    def get_user_by_username(username: str, _db_url: str, module_name: str | None = None):
        for user in users.values():
            if user.get("username") == username:
                return _copy_user(user)
        return None

    def append_user_event(
        user_id: str,
        database_url: str,
        module_name: str | None,
        event_type: str,
        payload: dict,
        run_id: str | None = None,
        task_id: str | None = None,
        event_version: int = 1,
    ):
        user = users.get(user_id)
        if user is None:
            raise ValueError(f"User {user_id} not found")
        if event_type == "task_charged":
            user["wallet_balance"] = float(payload.get("wallet_after_cost", user["wallet_balance"]))
        elif event_type == "task_finished":
            user["wallet_balance"] = float(payload.get("wallet_after", user["wallet_balance"]))
            user["tutorial_completed"] = bool(payload.get("tutorial_completed", user["tutorial_completed"]))
            completed = payload.get("completed_tutorial_tasks", [])
            if not isinstance(completed, list):
                completed = []
            user["tutorial_progress"] = {"completed_tasks": completed}
            user["task_history"].append(dict(payload))
        events.setdefault(user_id, []).append(
            {"event_type": event_type, "payload": dict(payload), "run_id": run_id, "task_id": task_id, "event_version": event_version}
        )
        return {"event_id": f"evt_{len(events[user_id])}", "event_type": event_type, "payload": payload}

    monkeypatch.setattr(progression, "_require_database_url", lambda: "postgresql://fake")
    monkeypatch.setattr(progression.user_store, "get_user_by_id", get_user_by_id)
    monkeypatch.setattr(progression.user_store, "check_username_exists", check_username_exists)
    monkeypatch.setattr(progression.user_store, "create_user", create_user)
    monkeypatch.setattr(progression.user_store, "get_user_by_username", get_user_by_username)
    monkeypatch.setattr(progression.user_store, "append_user_event", append_user_event)

    return users


def test_new_user_initialization(fake_user_store) -> None:
    user = progression.init_user("player_new_001")
    assert user["user_id"] == "player_new_001"
    assert user["tutorial_completed"] is False
    assert float(user["wallet_balance"]) > 0
    assert len(user["owned_agents"]) == 1
    assert user["owned_agents"][0]["level"] == "junior"


def test_start_game_requires_existing_user(fake_user_store) -> None:
    with pytest.raises(ValueError):
        progression.start_game("player_missing_001")


def test_tutorial_unlock_flow(fake_user_store) -> None:
    user_id = "player_tutorial_001"
    progression.init_user(user_id)

    board_1 = progression.list_task_board(user_id, TASKS)
    assert board_1["locked"] is True
    assert board_1["tasks"][0]["task_id"] == "tsk_tutorial_1_define_the_ta_4e9617a3"

    progression.finalize_task_result(
        user_id=user_id,
        task_id="tsk_tutorial_1_define_the_ta_4e9617a3",
        task_config=_tutorial_cfg("tsk_tutorial_1_define_the_ta_4e9617a3"),
        run_id="run_tutorial_1",
        cost_spent=3.5,
        clarity_score=0.95,
        evaluation_score=95.0,
        missed_constraints=0,
    )
    board_2 = progression.list_task_board(user_id, TASKS)
    assert board_2["locked"] is True
    assert board_2["tasks"][0]["task_id"] == "tsk_tutorial_2_add_constrain_4ba1bced"

    progression.finalize_task_result(
        user_id=user_id,
        task_id="tsk_tutorial_2_add_constrain_4ba1bced",
        task_config=_tutorial_cfg("tsk_tutorial_2_add_constrain_4ba1bced"),
        run_id="run_tutorial_2",
        cost_spent=4.5,
        clarity_score=0.95,
        evaluation_score=95.0,
        missed_constraints=0,
    )
    board_3 = progression.list_task_board(user_id, TASKS)
    assert board_3["locked"] is False
    assert any(item["task_id"] == "tsk_assess_a_city_launch_for_d9bbd92d" for item in board_3["tasks"])


def test_wallet_deduction(fake_user_store) -> None:
    user_id = "player_wallet_001"
    progression.init_user(user_id)
    before = float(progression.get_user(user_id)["wallet_balance"])
    charge = progression.charge_task_cost(user_id, "tsk_tutorial_1_define_the_ta_4e9617a3", 5.0)
    assert charge["wallet_before"] == before
    assert charge["wallet_after_cost"] == round(before - 5.0, 2)


def test_reward_on_success(fake_user_store) -> None:
    user_id = "player_reward_001"
    progression.init_user(user_id)
    charge = progression.charge_task_cost(user_id, "tsk_tutorial_1_define_the_ta_4e9617a3", 3.0)
    result = progression.finalize_task_result(
        user_id=user_id,
        task_id="tsk_tutorial_1_define_the_ta_4e9617a3",
        task_config=_tutorial_cfg("tsk_tutorial_1_define_the_ta_4e9617a3"),
        run_id="run_reward_001",
        cost_spent=3.0,
        wallet_before=float(charge["wallet_before"]),
        clarity_score=0.9,
        evaluation_score=95.0,
        missed_constraints=0,
    )
    assert result["success"] is True
    assert result["reward_gained"] > 0
    assert result["wallet_before"] == float(charge["wallet_before"])
    assert result["wallet_after"] == round(float(charge["wallet_after_cost"]) + float(result["reward_gained"]), 2)
    assert result["net_result"] == round(float(result["reward_gained"]) - float(result["cost_spent"]), 2)


def test_no_reward_on_failure(fake_user_store) -> None:
    user_id = "player_fail_001"
    progression.init_user(user_id)
    charge = progression.charge_task_cost(user_id, "tsk_assess_a_city_launch_for_d9bbd92d", 8.0)
    result = progression.finalize_task_result(
        user_id=user_id,
        task_id="tsk_assess_a_city_launch_for_d9bbd92d",
        task_config={**TASKS["tsk_assess_a_city_launch_for_d9bbd92d"], "_all_tasks": TASKS},
        run_id="run_fail_001",
        cost_spent=8.0,
        wallet_before=float(charge["wallet_before"]),
        clarity_score=0.1,
        evaluation_score=70.0,
        missed_constraints=1,
    )
    assert result["success"] is False
    assert result["reward_gained"] == 0.0
    assert result["wallet_before"] == float(charge["wallet_before"])
    assert result["wallet_after"] == float(charge["wallet_after_cost"])
    assert result["net_result"] == -8.0


def test_prompt_clarity_affecting_outcome() -> None:
    cfg = TASKS["tsk_assess_a_city_launch_for_d9bbd92d"]
    unclear = progression.resolve_task_outcome(
        task_config=cfg,
        evaluation_score=75.0,
        clarity_score=0.1,
        missed_constraints=0,
    )
    clear = progression.resolve_task_outcome(
        task_config=cfg,
        evaluation_score=75.0,
        clarity_score=0.9,
        missed_constraints=0,
    )
    assert unclear["success"] is False
    assert clear["success"] is True
    assert clear["reward"] > unclear["reward"]


def test_soft_business_failure_conditions() -> None:
    cfg = {
        **TASKS["tsk_assess_a_city_launch_for_d9bbd92d"],
        "constraints": ["target customer", "pricing", "risk"],
        "min_constraint_hit_ratio": 0.8,
        "min_clarity_score": 0.25,
        "min_agent_task_fit_score": 0.7,
        "_agent_task_fit_score": 0.2,
    }
    outcome = progression.resolve_task_outcome(
        task_config=cfg,
        evaluation_score=92.0,
        clarity_score=0.2,
        missed_constraints=2,
    )
    assert outcome["success"] is False
    reasons = set(outcome.get("failure_reasons", []))
    assert "too few required constraint hits" in reasons
    assert "very low clarity score" in reasons
    assert "poor agent-task fit" in reasons


def test_tutorial_enforced_before_normal_tasks(fake_user_store) -> None:
    user_id = "player_tutorial_gate_001"
    progression.init_user(user_id)

    allowed, reason = progression.tutorial_allows_task(
        user_id=user_id,
        task_id="tsk_assess_a_city_launch_for_d9bbd92d",
        task_definitions=TASKS,
    )
    assert allowed is False
    assert "Complete tutorial tasks first" in reason


def test_task_board_separates_tutorial_and_normal(fake_user_store) -> None:
    user_id = "player_board_001"
    progression.init_user(user_id)

    board = progression.list_task_board(user_id, TASKS)
    assert "tutorial_tasks" in board
    assert "normal_tasks" in board
    assert "available_tasks" in board

    assert all(item.get("is_tutorial", False) for item in board["tutorial_tasks"])
    assert all(not item.get("is_tutorial", False) for item in board["normal_tasks"])
    assert len(board["available_tasks"]) == 1
    first_available = board["available_tasks"][0]
    assert "reward" in first_available
    assert "difficulty" in first_available
    assert "cost_estimate" in first_available


def test_task_board_handles_none_user(monkeypatch) -> None:
    monkeypatch.setattr(progression, "get_user", lambda _user_id: None)
    board = progression.list_task_board("player_none_001", TASKS)
    assert isinstance(board, dict)
    assert "available_tasks" in board


def test_task_board_handles_null_tutorial_progress(monkeypatch) -> None:
    monkeypatch.setattr(
        progression,
        "get_user",
        lambda _user_id: {"tutorial_progress": None, "tutorial_completed": False},
    )
    board = progression.list_task_board("player_null_progress_001", TASKS)
    assert isinstance(board, dict)
    assert "available_tasks" in board


def test_retry_has_previous_score_and_delta(fake_user_store) -> None:
    user_id = "player_retry_001"
    progression.init_user(user_id)

    charge1 = progression.charge_task_cost(user_id, "tsk_assess_a_city_launch_for_d9bbd92d", 8.0)
    first = progression.finalize_task_result(
        user_id=user_id,
        task_id="tsk_assess_a_city_launch_for_d9bbd92d",
        task_config={**TASKS["tsk_assess_a_city_launch_for_d9bbd92d"], "_all_tasks": TASKS},
        run_id="run_retry_001",
        cost_spent=8.0,
        wallet_before=float(charge1["wallet_before"]),
        clarity_score=0.3,
        evaluation_score=74.0,
        missed_constraints=1,
    )
    assert first["previous_score"] is None
    assert first["score_delta"] is None

    charge2 = progression.charge_task_cost(user_id, "tsk_assess_a_city_launch_for_d9bbd92d", 8.0)
    second = progression.finalize_task_result(
        user_id=user_id,
        task_id="tsk_assess_a_city_launch_for_d9bbd92d",
        task_config={**TASKS["tsk_assess_a_city_launch_for_d9bbd92d"], "_all_tasks": TASKS},
        run_id="run_retry_002",
        cost_spent=8.0,
        wallet_before=float(charge2["wallet_before"]),
        clarity_score=0.9,
        evaluation_score=88.0,
        missed_constraints=0,
    )
    assert isinstance(second["previous_score"], float)
    assert isinstance(second["score_delta"], float)
    assert second["score_delta"] > 0


def test_near_miss_detection() -> None:
    cfg = {
        **TASKS["tsk_assess_a_city_launch_for_d9bbd92d"],
        "constraints": ["target customer", "pricing", "risk"],
        "success_threshold": 72.0,
    }
    outcome = progression.resolve_task_outcome(
        task_config=cfg,
        evaluation_score=82.0,
        clarity_score=0.6,
        missed_constraints=1,
    )
    assert outcome["success"] is False
    assert outcome["near_miss"] is True
    assert "Almost success" in outcome["explanation"]


def test_task_unlock_rules_by_progress_stage(monkeypatch) -> None:
    task_definitions = {
        "t1": {"task_id": "t1", "is_tutorial": True, "tutorial_order": 1, "difficulty": "easy"},
        "e1": {"task_id": "e1", "is_tutorial": False, "difficulty": "easy"},
        "m1": {"task_id": "m1", "is_tutorial": False, "difficulty": "medium"},
        "h1": {"task_id": "h1", "is_tutorial": False, "difficulty": "hard"},
    }

    monkeypatch.setattr(
        progression,
        "get_user",
        lambda _uid: {
            "tutorial_completed": True,
            "wallet_balance": 90.0,
            "tasks_completed_count": 2,
            "task_history": [{"task_id": "x"}] * 2,
            "tutorial_progress": {"completed_tasks": ["t1"]},
        },
    )
    board_mid = progression.list_task_board("player_stage_mid", task_definitions)
    available_mid = {item["task_id"] for item in board_mid["available_tasks"]}
    locked_mid = {item["task_id"] for item in board_mid["locked_tasks"]}
    assert "e1" in available_mid
    assert "m1" in available_mid
    assert "h1" in locked_mid

    monkeypatch.setattr(
        progression,
        "get_user",
        lambda _uid: {
            "tutorial_completed": True,
            "wallet_balance": 160.0,
            "tasks_completed_count": 3,
            "task_history": [{"task_id": "x"}] * 3,
            "tutorial_progress": {"completed_tasks": ["t1"]},
        },
    )
    board_hard = progression.list_task_board("player_stage_hard", task_definitions)
    available_hard = {item["task_id"] for item in board_hard["available_tasks"]}
    assert "h1" in available_hard


def test_streak_bonus_applied_on_consecutive_success(fake_user_store) -> None:
    user_id = "player_streak_001"
    progression.init_user(user_id)
    cfg = {**TASKS["tsk_tutorial_1_define_the_ta_4e9617a3"], "_all_tasks": TASKS}

    c1 = progression.charge_task_cost(user_id, "tsk_tutorial_1_define_the_ta_4e9617a3", 3.0)
    r1 = progression.finalize_task_result(
        user_id=user_id,
        task_id="tsk_tutorial_1_define_the_ta_4e9617a3",
        task_config=cfg,
        run_id="run_streak_1",
        cost_spent=3.0,
        wallet_before=float(c1["wallet_before"]),
        clarity_score=0.9,
        evaluation_score=95.0,
        missed_constraints=0,
    )
    c2 = progression.charge_task_cost(user_id, "tsk_tutorial_1_define_the_ta_4e9617a3", 3.0)
    r2 = progression.finalize_task_result(
        user_id=user_id,
        task_id="tsk_tutorial_1_define_the_ta_4e9617a3",
        task_config=cfg,
        run_id="run_streak_2",
        cost_spent=3.0,
        wallet_before=float(c2["wallet_before"]),
        clarity_score=0.9,
        evaluation_score=95.0,
        missed_constraints=0,
    )
    c3 = progression.charge_task_cost(user_id, "tsk_tutorial_1_define_the_ta_4e9617a3", 3.0)
    r3 = progression.finalize_task_result(
        user_id=user_id,
        task_id="tsk_tutorial_1_define_the_ta_4e9617a3",
        task_config=cfg,
        run_id="run_streak_3",
        cost_spent=3.0,
        wallet_before=float(c3["wallet_before"]),
        clarity_score=0.9,
        evaluation_score=95.0,
        missed_constraints=0,
    )

    assert r1["streak_bonus_rate"] == 0.0
    assert r2["streak_bonus_rate"] == 0.05
    assert r3["streak_bonus_rate"] == 0.10
    assert r2["reward_gained"] > r1["reward_gained"]
    assert r3["reward_gained"] > r2["reward_gained"]
