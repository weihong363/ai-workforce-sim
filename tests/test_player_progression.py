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


def test_tutorial_unlock_flow(fake_user_store) -> None:
    user_id = "player_tutorial_001"
    progression.init_user(user_id)

    board_1 = progression.list_task_board(user_id, TASKS)
    assert board_1["locked"] is True
    assert board_1["tasks"][0]["task_id"] == "tutorial_define_goal"

    progression.finalize_task_result(
        user_id=user_id,
        task_id="tutorial_define_goal",
        task_config=_tutorial_cfg("tutorial_define_goal"),
        run_id="run_tutorial_1",
        cost_spent=3.5,
        clarity_score=0.95,
        evaluation_score=95.0,
        missed_constraints=0,
    )
    board_2 = progression.list_task_board(user_id, TASKS)
    assert board_2["locked"] is True
    assert board_2["tasks"][0]["task_id"] == "tutorial_add_constraints"

    progression.finalize_task_result(
        user_id=user_id,
        task_id="tutorial_add_constraints",
        task_config=_tutorial_cfg("tutorial_add_constraints"),
        run_id="run_tutorial_2",
        cost_spent=4.5,
        clarity_score=0.95,
        evaluation_score=95.0,
        missed_constraints=0,
    )
    board_3 = progression.list_task_board(user_id, TASKS)
    assert board_3["locked"] is False
    assert any(item["task_id"] == "launch_coffee_subscription" for item in board_3["tasks"])


def test_wallet_deduction(fake_user_store) -> None:
    user_id = "player_wallet_001"
    progression.init_user(user_id)
    before = float(progression.get_user(user_id)["wallet_balance"])
    charge = progression.charge_task_cost(user_id, "tutorial_define_goal", 5.0)
    assert charge["wallet_before"] == before
    assert charge["wallet_after_cost"] == round(before - 5.0, 2)


def test_reward_on_success(fake_user_store) -> None:
    user_id = "player_reward_001"
    progression.init_user(user_id)
    progression.charge_task_cost(user_id, "tutorial_define_goal", 3.0)
    result = progression.finalize_task_result(
        user_id=user_id,
        task_id="tutorial_define_goal",
        task_config=_tutorial_cfg("tutorial_define_goal"),
        run_id="run_reward_001",
        cost_spent=3.0,
        clarity_score=0.9,
        evaluation_score=95.0,
        missed_constraints=0,
    )
    assert result["success"] is True
    assert result["reward_gained"] > 0


def test_no_reward_on_failure(fake_user_store) -> None:
    user_id = "player_fail_001"
    progression.init_user(user_id)
    progression.charge_task_cost(user_id, "launch_coffee_subscription", 8.0)
    result = progression.finalize_task_result(
        user_id=user_id,
        task_id="launch_coffee_subscription",
        task_config={**TASKS["launch_coffee_subscription"], "_all_tasks": TASKS},
        run_id="run_fail_001",
        cost_spent=8.0,
        clarity_score=0.1,
        evaluation_score=70.0,
        missed_constraints=1,
    )
    assert result["success"] is False
    assert result["reward_gained"] == 0.0


def test_prompt_clarity_affecting_outcome() -> None:
    cfg = TASKS["launch_coffee_subscription"]
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


def test_tutorial_enforced_before_normal_tasks(fake_user_store) -> None:
    user_id = "player_tutorial_gate_001"
    progression.init_user(user_id)

    allowed, reason = progression.tutorial_allows_task(
        user_id=user_id,
        task_id="launch_coffee_subscription",
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
