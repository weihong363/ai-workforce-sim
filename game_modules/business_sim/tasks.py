"""Database-backed task catalog and lightweight task generation for business_sim."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Dict, List

from core_engine.agent_controller import AgentController
from core_engine.config import get_settings
from core_engine.task_store import get_task as db_get_task
from core_engine.task_store import init_task_db, list_tasks as db_list_tasks, seed_tasks, upsert_task

MODULE_NAME = "business_sim"
_MIN_NORMAL_TASKS = 3
_LAST_AUTO_GENERATE_TS = 0.0
_SEED_FILE_PATH = Path(__file__).with_name("task_seeds.json")


def _require_database_url() -> str:
    database_url = get_settings().database_url
    if not database_url:
        raise RuntimeError("DATABASE_URL is required for task catalog")
    return database_url


def _ensure_task_catalog() -> Dict[str, Dict[str, object]]:
    database_url = _require_database_url()
    init_task_db(database_url)
    seed_tasks(database_url, MODULE_NAME, _load_seed_tasks())
    return db_list_tasks(database_url, MODULE_NAME)


def _load_seed_tasks() -> List[Dict[str, object]]:
    raw = json.loads(_SEED_FILE_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"Invalid task seed file format: {_SEED_FILE_PATH}")
    return [dict(item) for item in raw if isinstance(item, dict)]


def _safe_slug(raw: str) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", raw.strip().lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:64] or f"generated_task_{int(time.time())}"


def _generate_task_via_ai() -> Dict[str, object]:
    settings = get_settings()
    controller = AgentController(settings=settings, purpose="task")
    prompt = (
        "Generate ONE new business simulation task as JSON only with keys: "
        "task_id,input,workflow,max_total_tokens,is_tutorial,reward,difficulty,cost_estimate,constraints. "
        "Rules: workflow must be [\"market_analyst\",\"strategy_writer\"], "
        "is_tutorial must be false, difficulty in [easy,medium,hard], constraints as short strings."
    )
    result = controller.run_step(
        step_index=0,
        agent_name="task_generator",
        prompt=prompt,
        task_input="Create one fresh startup strategy task.",
        agent_profile={"level": "senior", "obedience": 0.8, "initiative": 0.7, "effort": 0.9},
    )
    text = str(result.get("output", "")).strip()
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("Generated task payload must be a JSON object")

    task_id = _safe_slug(str(payload.get("task_id", "generated_task")))
    task = {
        "input": str(payload.get("input", "Assess a new business opportunity with clear trade-offs.")),
        "workflow": ["market_analyst", "strategy_writer"],
        "max_total_tokens": int(payload.get("max_total_tokens", 320) or 320),
        "is_tutorial": False,
        "reward": float(payload.get("reward", 40.0) or 40.0),
        "difficulty": str(payload.get("difficulty", "medium") or "medium"),
        "cost_estimate": float(payload.get("cost_estimate", 9.0) or 9.0),
        "constraints": [str(x) for x in (payload.get("constraints") or ["target customer", "pricing", "risk"])],
    }
    return {"task_id": task_id, "task_config": task, "source": "ai"}


def _maybe_generate_task(tasks: Dict[str, Dict[str, object]]) -> None:
    global _LAST_AUTO_GENERATE_TS
    auto_generate = str(__import__("os").getenv("BUSINESS_SIM_AUTO_GENERATE_TASKS", "true")).lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not auto_generate:
        return

    normal_task_count = sum(1 for cfg in tasks.values() if not bool(cfg.get("is_tutorial", False)))
    if normal_task_count >= _MIN_NORMAL_TASKS:
        return

    now = time.time()
    if now - _LAST_AUTO_GENERATE_TS < 60:
        return

    try:
        generated = _generate_task_via_ai()
        upsert_task(
            database_url=_require_database_url(),
            module_name=MODULE_NAME,
            task_id=str(generated["task_id"]),
            task_config=dict(generated["task_config"]),
            source=str(generated.get("source", "ai")),
        )
        _LAST_AUTO_GENERATE_TS = now
    except Exception:
        _LAST_AUTO_GENERATE_TS = now


def get_task(task_id: str) -> dict:
    tasks = _ensure_task_catalog()
    _maybe_generate_task(tasks)
    database_url = _require_database_url()
    item = db_get_task(database_url, MODULE_NAME, task_id)
    if item is None:
        raise ValueError(f"Unknown task: {task_id}")
    return item


def list_tasks() -> dict:
    tasks = _ensure_task_catalog()
    _maybe_generate_task(tasks)
    return db_list_tasks(_require_database_url(), MODULE_NAME)


def get_seed_tasks() -> Dict[str, Dict[str, object]]:
    """Return initial task seed map (used by tests and bootstrapping helpers)."""
    return {str(item["task_id"]): dict(item["task_config"]) for item in _load_seed_tasks()}
