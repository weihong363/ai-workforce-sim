"""Minimal player progression loop for business_sim (event-sourced persistence)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from core_engine import user_store
from core_engine.config import get_settings

DEFAULT_STARTING_WALLET = 120.0
DEFAULT_GAME_START_WALLET = 30.0


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_database_url() -> str:
    db_url = get_settings().database_url
    if not db_url:
        raise RuntimeError("DATABASE_URL is required for player progression persistence")
    return db_url


def _module_name() -> str:
    return get_settings().active_game_module


def _ensure_user(
        user_id: str,
        username: Optional[str] = None,
        starting_wallet: float = DEFAULT_STARTING_WALLET,
) -> Dict[str, object]:
    db_url = _require_database_url()
    module_name = _module_name()
    existing = user_store.get_user_by_id(user_id, db_url, module_name=module_name)
    if existing is not None:
        return existing

    resolved_username = username or user_id
    if user_store.check_username_exists(resolved_username, db_url):
        raise ValueError(f"Username '{resolved_username}' already exists")

    user_store.create_user(
        user_id=user_id,
        username=resolved_username,
        database_url=db_url,
        wallet_balance=float(starting_wallet),
        module_name=module_name,
    )
    created = user_store.get_user_by_id(user_id, db_url, module_name=module_name)
    if created is None:
        raise ValueError(f"Failed to create user '{user_id}'")
    return created


def init_user(user_id: str, username: Optional[str] = None) -> Dict[str, object]:
    """Initialize or get a user."""
    return _ensure_user(user_id, username)


def start_game(user_id: str, username: Optional[str] = None) -> Dict[str, object]:
    """Return minimal gameplay state for an existing player.

    User creation/registration must go through /users/register.
    """
    db_url = _require_database_url()
    module_name = _module_name()
    user = user_store.get_user_by_id(user_id, db_url, module_name=module_name)
    if user is None:
        raise ValueError("User not found. Please register first via /users/register.")
    owned_agents = user.get("owned_agents", []) if isinstance(user, dict) else []
    workers = [
                  str(item.get("level", "junior"))
                  for item in owned_agents
                  if isinstance(item, dict)
              ] or ["junior"]
    task_history = user.get("task_history", []) if isinstance(user, dict) else []
    tasks_completed_count = len(task_history) if isinstance(task_history, list) else 0
    return {
        "user_id": str(user.get("user_id", user_id)),
        "wallet_balance": float(user.get("wallet_balance", DEFAULT_GAME_START_WALLET)),
        "workers": workers,
        "tutorial_completed": bool(user.get("tutorial_completed", False)),
        "tasks_completed_count": int(tasks_completed_count),
    }


def get_user(user_id: str) -> Dict[str, object]:
    """Get user by ID."""
    return _ensure_user(user_id)


def check_username_exists(username: str) -> bool:
    """Check if a username already exists."""
    return user_store.check_username_exists(username, _require_database_url())


def get_user_by_username(username: str) -> Optional[Dict[str, object]]:
    """Get user data by username."""
    return user_store.get_user_by_username(username, _require_database_url(), module_name=_module_name())


def score_prompt_clarity(instructions: str, task_config: Dict[str, object]) -> float:
    text = (instructions or "").strip().lower()
    if not text:
        return 0.0

    words = text.split()
    points = 0
    max_points = 5

    if len(words) >= 12:
        points += 1
    if any(token in text for token in ("target", "budget", "timeline", "constraint", "must", "deliverable")):
        points += 1
    if any(ch.isdigit() for ch in text):
        points += 1
    if ("\n" in instructions) or (";" in text) or ("." in text):
        points += 1

    constraints = task_config.get("constraints", []) or []
    if constraints:
        hits = 0
        for item in constraints:
            key = str(item).lower().strip()
            if key and key in text:
                hits += 1
        if hits / max(1, len(constraints)) >= 0.5:
            points += 1
    else:
        points += 1

    return round(points / max_points, 2)


def list_task_board(user_id: str, task_definitions: Dict[str, Dict[str, object]]) -> Dict[str, object]:
    user = get_user(user_id)
    if not isinstance(user, dict):
        user = {
            "tutorial_progress": {"completed_tasks": []},
            "tutorial_completed": False,
        }

    tutorial_progress = user.get("tutorial_progress")
    if not isinstance(tutorial_progress, dict):
        tutorial_progress = {}

    completed_raw = tutorial_progress.get("completed_tasks", [])
    completed = set(completed_raw if isinstance(completed_raw, list) else [])
    task_history = user.get("task_history", []) if isinstance(user.get("task_history"), list) else []
    tasks_completed_count = int(user.get("tasks_completed_count", len(task_history)) or 0)
    wallet_balance = float(user.get("wallet_balance", 0.0) or 0.0)

    tutorial_tasks = [
        {**cfg, "task_id": name}
        for name, cfg in task_definitions.items()
        if bool(cfg.get("is_tutorial", False))
    ]
    tutorial_tasks.sort(key=lambda item: int(item.get("tutorial_order", 9999)))

    normal_tasks = [
        {**cfg, "task_id": name}
        for name, cfg in task_definitions.items()
        if not bool(cfg.get("is_tutorial", False))
    ]

    if not bool(user.get("tutorial_completed", False)):
        next_tutorial = [task for task in tutorial_tasks if task["task_id"] not in completed][:1]
        locked = [
            {**task, "unlock_condition": "Complete tutorial tasks"}
            for task in normal_tasks
        ]
        return {
            "locked": True,
            "tutorial_tasks": tutorial_tasks,
            "normal_tasks": normal_tasks,
            "available_tasks": next_tutorial,
            "locked_tasks": locked,
            "tasks": next_tutorial,
            "tasks_completed_count": tasks_completed_count,
            "wallet_balance": wallet_balance,
        }

    easy_tasks = [task for task in normal_tasks if str(task.get("difficulty", "easy")).lower() == "easy"]
    medium_tasks = [task for task in normal_tasks if str(task.get("difficulty", "easy")).lower() == "medium"]
    hard_tasks = [task for task in normal_tasks if str(task.get("difficulty", "easy")).lower() == "hard"]
    other_tasks = [
        task
        for task in normal_tasks
        if str(task.get("difficulty", "easy")).lower() not in {"easy", "medium", "hard"}
    ]
    medium_unlocked = tasks_completed_count >= 5 or wallet_balance >= 80.0
    hard_unlocked = tasks_completed_count >= 10 or wallet_balance >= 150.0
    available_tasks = list(easy_tasks) + list(other_tasks)
    locked_tasks: list[Dict[str, object]] = []
    if medium_unlocked:
        available_tasks.extend(medium_tasks)
    else:
        locked_tasks.extend(
            [{**task, "unlock_condition": "Complete 5 tasks or reach wallet 80"} for task in medium_tasks])
    if hard_unlocked:
        available_tasks.extend(hard_tasks)
    else:
        locked_tasks.extend(
            [{**task, "unlock_condition": "Complete 10 tasks or reach wallet 150"} for task in hard_tasks])

    stage_target_diff = "hard" if hard_unlocked else ("medium" if medium_unlocked else "easy")
    recommended_added = 0
    for item in available_tasks:
        is_target = str(item.get("difficulty", "")).lower() == stage_target_diff
        item["recommended"] = bool(is_target and recommended_added < 2)
        if item["recommended"]:
            recommended_added += 1
    if recommended_added == 0:
        for item in available_tasks[:2]:
            item["recommended"] = True

    return {
        "locked": False,
        "tutorial_tasks": tutorial_tasks,
        "normal_tasks": normal_tasks,
        "available_tasks": available_tasks,
        "locked_tasks": locked_tasks,
        "tasks": available_tasks,
        "tasks_completed_count": tasks_completed_count,
        "wallet_balance": wallet_balance,
    }


def estimate_task_cost(task_config: Dict[str, object]) -> float:
    return float(task_config.get("estimated_cost", task_config.get("cost_estimate", 0.0)) or 0.0)


def charge_task_cost(user_id: str, task_id: str, cost: float) -> Dict[str, object]:
    db_url = _require_database_url()
    module_name = _module_name()
    user = _ensure_user(user_id)
    wallet_before = float(user.get("wallet_balance", 0.0))
    if wallet_before < cost:
        raise ValueError(
            f"Insufficient wallet balance. required={round(cost, 2)}, available={round(wallet_before, 2)}"
        )

    wallet_after = round(wallet_before - cost, 2)
    event_payload = {
        "task_id": task_id,
        "cost_spent": round(cost, 2),
        "wallet_before": round(wallet_before, 2),
        "wallet_after_cost": wallet_after,
    }
    user_store.append_user_event(
        user_id=user_id,
        database_url=db_url,
        module_name=module_name,
        event_type="task_charged",
        payload=event_payload,
        task_id=task_id,
    )

    return event_payload


def _build_explanation(success: bool, clarity: float, final_score: float, missed_constraints: int) -> str:
    if not success:
        if clarity < 0.35:
            return "Task failed because instructions were too vague. Add clearer goals, constraints, and numbers."
        if missed_constraints > 0:
            return "Task failed because required constraints were missed."
        return "Task failed because output quality was below the requirement."
    if clarity < 0.45:
        return "Task succeeded, but clearer instructions would improve consistency and rewards."
    if missed_constraints > 0:
        return "Task succeeded with acceptable output, but some constraints were not fully addressed."
    if final_score >= 90:
        return "Task succeeded with clear instructions and strong execution."
    return "Task succeeded with good enough execution."


def _soft_failure_reasons(
        task_config: Dict[str, object],
        clarity_score: float,
        missed_constraints: int,
) -> list[str]:
    reasons: list[str] = []
    constraints = list(task_config.get("constraints", []) or [])
    total_constraints = len(constraints)
    hit_ratio = 1.0 if total_constraints <= 0 else max(0.0,
                                                       1.0 - (float(missed_constraints) / float(total_constraints)))
    min_hit_ratio = float(task_config.get("min_constraint_hit_ratio", 0.45) or 0.45)
    min_clarity = float(task_config.get("min_clarity_score", 0.12) or 0.12)
    min_fit = float(task_config.get("min_agent_task_fit_score", 0.35) or 0.35)
    fit_score = float(task_config.get("_agent_task_fit_score", 1.0) or 1.0)

    if hit_ratio < min_hit_ratio:
        reasons.append("too few required constraint hits")
    if clarity_score < min_clarity:
        reasons.append("very low clarity score")
    if fit_score < min_fit:
        reasons.append("poor agent-task fit")
    return reasons


def resolve_task_outcome(
    task_config: Dict[str, object],
    evaluation_score: float,
    clarity_score: float,
    missed_constraints: int,
) -> Dict[str, object]:
    is_tutorial = bool(task_config.get("tutorial_only", task_config.get("is_tutorial", False)))
    default_threshold = 55.0 if is_tutorial else 72.0
    threshold = float(task_config.get("success_threshold", default_threshold) or default_threshold)
    settings = get_settings()
    clarity_weight = max(0.0, min(1.0, float(settings.clarity_impact_weight)))
    base_weight = 1.0 - clarity_weight
    clarity_penalty = max(0.0, 0.45 - clarity_score) * 25.0
    effective_score = round((evaluation_score * (base_weight + (clarity_weight * clarity_score))) - clarity_penalty, 2)
    too_vague = clarity_score < (0.15 if is_tutorial else 0.28)
    soft_failures = _soft_failure_reasons(task_config, clarity_score, missed_constraints)
    success = (effective_score >= threshold) and not too_vague and (len(soft_failures) == 0)
    total_constraints = len(list(task_config.get("constraints", []) or []))
    near_miss = (
            (not success)
            and (not too_vague)
            and (missed_constraints in {1, 2})
            and (total_constraints <= 0 or (missed_constraints < total_constraints))
            and (effective_score >= max(0.0, threshold - 8.0))
    )
    reward_base = float(task_config.get("base_reward", task_config.get("reward", 0.0)) or 0.0)
    reward = round(reward_base * (0.50 + 0.90 * clarity_score), 2) if success else 0.0
    explanation = _build_explanation(success, clarity_score, effective_score, missed_constraints)
    if not success and soft_failures:
        explanation = f"Task failed due to {soft_failures[0]}."
    elif near_miss:
        explanation = "Almost success: most constraints were met, but a few key points are still missing."
    return {
        "success": success,
        "near_miss": near_miss,
        "effective_score": effective_score,
        "reward": reward,
        "explanation": explanation,
        "failure_reasons": soft_failures,
    }


def finalize_task_result(
    user_id: str,
    task_id: str,
    task_config: Dict[str, object],
    run_id: str,
    cost_spent: float,
    clarity_score: float,
    evaluation_score: float,
    missed_constraints: int,
        wallet_before: Optional[float] = None,
) -> Dict[str, object]:
    db_url = _require_database_url()
    module_name = _module_name()
    outcome = resolve_task_outcome(
        task_config=task_config,
        evaluation_score=evaluation_score,
        clarity_score=clarity_score,
        missed_constraints=missed_constraints,
    )

    user = _ensure_user(user_id)
    task_history = user.get("task_history", []) if isinstance(user, dict) else []
    previous_score = None
    previous_streak = 0
    if isinstance(task_history, list):
        for item in reversed(task_history):
            if not isinstance(item, dict):
                continue
            if str(item.get("task_id", "")) != str(task_id):
                continue
            value = item.get("effective_score")
            if isinstance(value, (int, float)):
                previous_score = float(value)
                break
        for item in reversed(task_history):
            if not isinstance(item, dict):
                continue
            if bool(item.get("success", False)):
                previous_streak += 1
                continue
            break

    wallet_before_reward = float(user.get("wallet_balance", 0.0))
    wallet_before_run = round(
        float(wallet_before) if wallet_before is not None else (wallet_before_reward + cost_spent), 2)
    streak_after = previous_streak + 1 if bool(outcome["success"]) else 0
    streak_bonus_rate = 0.10 if streak_after >= 3 else (0.05 if streak_after >= 2 else 0.0)
    reward_raw = float(outcome["reward"])
    reward_with_bonus = round(reward_raw * (1.0 + streak_bonus_rate), 2) if bool(outcome["success"]) else 0.0
    wallet_after = round(wallet_before_reward + reward_with_bonus, 2)
    score_delta = (
        round(float(outcome["effective_score"]) - float(previous_score), 2)
        if isinstance(previous_score, (int, float))
        else None
    )

    tutorial_progress = user.get("tutorial_progress")
    if not isinstance(tutorial_progress, dict):
        tutorial_progress = {"completed_tasks": []}

    completed = tutorial_progress.get("completed_tasks")
    if not isinstance(completed, list):
        completed = []

    if bool(outcome["success"]) and bool(task_config.get("is_tutorial", False)) and task_id not in completed:
        completed = [*completed, task_id]

    tutorial_completed = bool(user.get("tutorial_completed", False))
    if not tutorial_completed:
        tutorial_required = [
            name
            for name, cfg in task_config.get("_all_tasks", {}).items()
            if bool(cfg.get("is_tutorial", False))
        ]
        tutorial_completed = all(name in completed for name in tutorial_required)

    history_record = {
        "run_id": run_id,
        "task_id": task_id,
        "success": bool(outcome["success"]),
        "clarity_score": clarity_score,
        "effective_score": outcome["effective_score"],
        "previous_score": previous_score,
        "score_delta": score_delta,
        "near_miss": bool(outcome.get("near_miss", False)),
        "cost_spent": round(cost_spent, 2),
        "reward_gained": reward_with_bonus,
        "reward_before_bonus": reward_raw,
        "streak_bonus_rate": streak_bonus_rate,
        "streak_count": int(streak_after),
        "wallet_before": wallet_before_run,
        "net_result": round(float(reward_with_bonus) - cost_spent, 2),
        "wallet_after": wallet_after,
        "created_at": _utc_now_iso(),
    }

    event_payload = {
        **history_record,
        "tutorial_completed": tutorial_completed,
        "completed_tutorial_tasks": completed,
    }

    user_store.append_user_event(
        user_id=user_id,
        database_url=db_url,
        module_name=module_name,
        event_type="task_finished",
        payload=event_payload,
        run_id=run_id,
        task_id=task_id,
    )

    return {
        "success": bool(outcome["success"]),
        "near_miss": bool(outcome.get("near_miss", False)),
        "reward_gained": reward_with_bonus,
        "reward_before_bonus": reward_raw,
        "streak_bonus_rate": streak_bonus_rate,
        "streak_count": int(streak_after),
        "cost_spent": round(cost_spent, 2),
        "wallet_before": wallet_before_run,
        "wallet_after": wallet_after,
        "net_result": round(float(reward_with_bonus) - cost_spent, 2),
        "clarity_score": clarity_score,
        "effective_score": float(outcome["effective_score"]),
        "previous_score": previous_score,
        "score_delta": score_delta,
        "explanation": str(outcome["explanation"]),
        "failure_reasons": list(outcome.get("failure_reasons", []) or []),
        "tutorial_completed": tutorial_completed,
        "tasks_completed_count": len(task_history) + 1,
    }


def tutorial_allows_task(user_id: str, task_id: str, task_definitions: Dict[str, Dict[str, object]]) -> Tuple[bool, str]:
    user = get_user(user_id)
    is_tutorial_task = bool(task_definitions.get(task_id, {}).get("is_tutorial", False))
    if user.get("tutorial_completed", False):
        return True, ""
    if is_tutorial_task:
        board = list_task_board(user_id=user_id, task_definitions=task_definitions)
        available = [item["task_id"] for item in board.get("tasks", [])]
        if task_id in available:
            return True, ""
        return False, "Tutorial is guided. Complete the current tutorial task first."
    return False, "Complete tutorial tasks first to unlock the normal task board."
