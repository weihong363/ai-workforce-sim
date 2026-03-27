"""Minimal player progression loop for business_sim."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DEFAULT_STARTING_WALLET = 120.0
DEFAULT_USER_STATE_FILE = "data/business_sim_users.json"

_LOCK = threading.Lock()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state_path() -> Path:
    configured = os.getenv("BUSINESS_SIM_USER_STATE_PATH", DEFAULT_USER_STATE_FILE)
    return Path(configured)


def _load_state() -> Dict[str, object]:
    path = _state_path()
    if not path.exists():
        return {"users": {}}
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, dict):
        return {"users": {}}
    users = payload.get("users")
    if not isinstance(users, dict):
        return {"users": {}}
    return payload


def _save_state(state: Dict[str, object]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=True, indent=2)


def _new_user(user_id: str, username: Optional[str] = None) -> Dict[str, object]:
    safe_username = username or user_id
    return {
        "user_id": user_id,
        "username": safe_username,
        "wallet_balance": DEFAULT_STARTING_WALLET,
        "tutorial_completed": False,
        "owned_agents": [
            {"agent_id": "junior_001", "preset": "junior_worker", "level": "junior"},
        ],
        "tutorial_progress": {"completed_tasks": []},
        "task_history": [],
        "created_at": _utc_now_iso(),
        "updated_at": _utc_now_iso(),
    }


def init_user(user_id: str, username: Optional[str] = None) -> Dict[str, object]:
    """Initialize or get a user.
    
    Args:
        user_id: Unique user ID
        username: Optional username. If provided and user doesn't exist, creates new user.
                 If user exists, ignores the username parameter.
    
    Returns:
        User data dictionary
    """
    with _LOCK:
        state = _load_state()
        users = state["users"]
        if user_id not in users:
            username = username or user_id
            # Check username uniqueness
            for existing_user in users.values():
                if existing_user.get("username") == username:
                    raise ValueError(f"Username '{username}' already exists")
            users[user_id] = _new_user(user_id, username)
            _save_state(state)
        return dict(users[user_id])


def get_user(user_id: str) -> Dict[str, object]:
    """Get user by ID."""
    return init_user(user_id)


def check_username_exists(username: str) -> bool:
    """Check if a username already exists.
    
    Args:
        username: Username to check
    
    Returns:
        True if username exists, False otherwise
    """
    state = _load_state()
    users = state.get("users", {})
    for user_data in users.values():
        if user_data.get("username") == username:
            return True
    return False


def get_user_by_username(username: str) -> Optional[Dict[str, object]]:
    """Get user data by username.
    
    Args:
        username: Username to look up
    
    Returns:
        User data dictionary if found, None otherwise
    """
    state = _load_state()
    users = state.get("users", {})
    for user_data in users.values():
        if user_data.get("username") == username:
            return dict(user_data)
    return None


def _touch(user: Dict[str, object]) -> None:
    user["updated_at"] = _utc_now_iso()


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
    completed = set(user.get("tutorial_progress", {}).get("completed_tasks", []))
    tutorial_tasks = [
        {"task_name": name, **cfg}
        for name, cfg in task_definitions.items()
        if bool(cfg.get("is_tutorial", False))
    ]
    tutorial_tasks.sort(key=lambda item: int(item.get("tutorial_order", 9999)))

    if not bool(user.get("tutorial_completed", False)):
        next_tutorial = [task for task in tutorial_tasks if task["task_name"] not in completed][:1]
        return {"locked": True, "tasks": next_tutorial}

    normal_tasks = [
        {"task_name": name, **cfg}
        for name, cfg in task_definitions.items()
        if not bool(cfg.get("is_tutorial", False))
    ]
    return {"locked": False, "tasks": normal_tasks}


def estimate_task_cost(task_config: Dict[str, object]) -> float:
    return float(task_config.get("cost_estimate", 0.0) or 0.0)


def charge_task_cost(user_id: str, task_name: str, cost: float) -> Dict[str, object]:
    with _LOCK:
        state = _load_state()
        users = state["users"]
        if user_id not in users:
            users[user_id] = _new_user(user_id)
        user = users[user_id]
        wallet_before = float(user.get("wallet_balance", 0.0))
        if wallet_before < cost:
            raise ValueError(
                f"Insufficient wallet balance. required={round(cost, 2)}, available={round(wallet_before, 2)}"
            )
        wallet_after = round(wallet_before - cost, 2)
        user["wallet_balance"] = wallet_after
        _touch(user)
        _save_state(state)
    return {
        "task_name": task_name,
        "cost_spent": round(cost, 2),
        "wallet_before": round(wallet_before, 2),
        "wallet_after_cost": wallet_after,
    }


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


def resolve_task_outcome(
    task_config: Dict[str, object],
    evaluation_score: float,
    clarity_score: float,
    missed_constraints: int,
) -> Dict[str, object]:
    is_tutorial = bool(task_config.get("is_tutorial", False))
    threshold = 55.0 if is_tutorial else 72.0
    effective_score = round(evaluation_score * (0.65 + (0.35 * clarity_score)), 2)
    too_vague = clarity_score < (0.12 if is_tutorial else 0.20)
    success = (effective_score >= threshold) and not too_vague
    reward_base = float(task_config.get("reward", 0.0) or 0.0)
    reward = round(reward_base * (0.75 + 0.25 * clarity_score), 2) if success else 0.0
    return {
        "success": success,
        "effective_score": effective_score,
        "reward": reward,
        "explanation": _build_explanation(success, clarity_score, effective_score, missed_constraints),
    }


def finalize_task_result(
    user_id: str,
    task_name: str,
    task_config: Dict[str, object],
    run_id: str,
    cost_spent: float,
    clarity_score: float,
    evaluation_score: float,
    missed_constraints: int,
) -> Dict[str, object]:
    outcome = resolve_task_outcome(
        task_config=task_config,
        evaluation_score=evaluation_score,
        clarity_score=clarity_score,
        missed_constraints=missed_constraints,
    )
    with _LOCK:
        state = _load_state()
        users = state["users"]
        if user_id not in users:
            users[user_id] = _new_user(user_id)
        user = users[user_id]
        wallet_before_reward = float(user.get("wallet_balance", 0.0))
        wallet_after = round(wallet_before_reward + float(outcome["reward"]), 2)
        user["wallet_balance"] = wallet_after

        tutorial_progress = user.setdefault("tutorial_progress", {"completed_tasks": []})
        completed = tutorial_progress.setdefault("completed_tasks", [])
        if bool(outcome["success"]) and bool(task_config.get("is_tutorial", False)) and task_name not in completed:
            completed.append(task_name)

        if not bool(user.get("tutorial_completed", False)):
            tutorial_required = [
                name
                for name, cfg in task_config.get("_all_tasks", {}).items()
                if bool(cfg.get("is_tutorial", False))
            ]
            user["tutorial_completed"] = all(name in completed for name in tutorial_required)

        history = user.setdefault("task_history", [])
        history.append(
            {
                "run_id": run_id,
                "task_name": task_name,
                "success": bool(outcome["success"]),
                "clarity_score": clarity_score,
                "effective_score": outcome["effective_score"],
                "cost_spent": round(cost_spent, 2),
                "reward_gained": float(outcome["reward"]),
                "net_result": round(float(outcome["reward"]) - cost_spent, 2),
                "wallet_after": wallet_after,
                "created_at": _utc_now_iso(),
            }
        )
        _touch(user)
        _save_state(state)

    return {
        "success": bool(outcome["success"]),
        "reward_gained": float(outcome["reward"]),
        "cost_spent": round(cost_spent, 2),
        "wallet_after": wallet_after,
        "clarity_score": clarity_score,
        "effective_score": float(outcome["effective_score"]),
        "explanation": str(outcome["explanation"]),
        "tutorial_completed": bool(user.get("tutorial_completed", False)),
    }


def tutorial_allows_task(user_id: str, task_name: str, task_definitions: Dict[str, Dict[str, object]]) -> Tuple[bool, str]:
    user = get_user(user_id)
    is_tutorial_task = bool(task_definitions.get(task_name, {}).get("is_tutorial", False))
    if user.get("tutorial_completed", False):
        return True, ""
    if is_tutorial_task:
        board = list_task_board(user_id=user_id, task_definitions=task_definitions)
        available = [item["task_name"] for item in board.get("tasks", [])]
        if task_name in available:
            return True, ""
        return False, "Tutorial is guided. Complete the current tutorial task first."
    return False, "Complete tutorial tasks first to unlock the normal task board."
