from game_modules.business_sim import progression, tasks


def _tutorial_cfg(name: str) -> dict:
    cfg = dict(tasks.TASKS[name])
    cfg["_all_tasks"] = tasks.TASKS
    return cfg


def test_new_user_initialization(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BUSINESS_SIM_USER_STATE_PATH", str(tmp_path / "users.json"))
    user = progression.init_user("player_new_001")
    assert user["user_id"] == "player_new_001"
    assert user["tutorial_completed"] is False
    assert float(user["wallet_balance"]) > 0
    assert len(user["owned_agents"]) == 1
    assert user["owned_agents"][0]["level"] == "junior"


def test_tutorial_unlock_flow(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BUSINESS_SIM_USER_STATE_PATH", str(tmp_path / "users.json"))
    user_id = "player_tutorial_001"
    progression.init_user(user_id)

    board_1 = progression.list_task_board(user_id, tasks.TASKS)
    assert board_1["locked"] is True
    assert board_1["tasks"][0]["task_name"] == "tutorial_define_goal"

    progression.finalize_task_result(
        user_id=user_id,
        task_name="tutorial_define_goal",
        task_config=_tutorial_cfg("tutorial_define_goal"),
        run_id="run_tutorial_1",
        cost_spent=3.5,
        clarity_score=0.95,
        evaluation_score=95.0,
        missed_constraints=0,
    )
    board_2 = progression.list_task_board(user_id, tasks.TASKS)
    assert board_2["locked"] is True
    assert board_2["tasks"][0]["task_name"] == "tutorial_add_constraints"

    progression.finalize_task_result(
        user_id=user_id,
        task_name="tutorial_add_constraints",
        task_config=_tutorial_cfg("tutorial_add_constraints"),
        run_id="run_tutorial_2",
        cost_spent=4.5,
        clarity_score=0.95,
        evaluation_score=95.0,
        missed_constraints=0,
    )
    board_3 = progression.list_task_board(user_id, tasks.TASKS)
    assert board_3["locked"] is False
    assert any(item["task_name"] == "launch_coffee_subscription" for item in board_3["tasks"])


def test_wallet_deduction(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BUSINESS_SIM_USER_STATE_PATH", str(tmp_path / "users.json"))
    user_id = "player_wallet_001"
    progression.init_user(user_id)
    before = float(progression.get_user(user_id)["wallet_balance"])
    charge = progression.charge_task_cost(user_id, "tutorial_define_goal", 5.0)
    assert charge["wallet_before"] == before
    assert charge["wallet_after_cost"] == round(before - 5.0, 2)


def test_reward_on_success(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BUSINESS_SIM_USER_STATE_PATH", str(tmp_path / "users.json"))
    user_id = "player_reward_001"
    progression.init_user(user_id)
    progression.charge_task_cost(user_id, "tutorial_define_goal", 3.0)
    result = progression.finalize_task_result(
        user_id=user_id,
        task_name="tutorial_define_goal",
        task_config=_tutorial_cfg("tutorial_define_goal"),
        run_id="run_reward_001",
        cost_spent=3.0,
        clarity_score=0.9,
        evaluation_score=95.0,
        missed_constraints=0,
    )
    assert result["success"] is True
    assert result["reward_gained"] > 0


def test_no_reward_on_failure(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BUSINESS_SIM_USER_STATE_PATH", str(tmp_path / "users.json"))
    user_id = "player_fail_001"
    progression.init_user(user_id)
    progression.charge_task_cost(user_id, "launch_coffee_subscription", 8.0)
    result = progression.finalize_task_result(
        user_id=user_id,
        task_name="launch_coffee_subscription",
        task_config={**tasks.TASKS["launch_coffee_subscription"], "_all_tasks": tasks.TASKS},
        run_id="run_fail_001",
        cost_spent=8.0,
        clarity_score=0.1,
        evaluation_score=70.0,
        missed_constraints=1,
    )
    assert result["success"] is False
    assert result["reward_gained"] == 0.0


def test_prompt_clarity_affecting_outcome() -> None:
    cfg = tasks.TASKS["launch_coffee_subscription"]
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
