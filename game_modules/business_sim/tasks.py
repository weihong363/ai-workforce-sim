"""Database-backed task catalog and lightweight task generation for business_sim.

This module standardizes task schema so gameplay, run_task, and debug flows
consume the same task definition shape.
"""

from __future__ import annotations

import json
import re
import time
import hashlib
from pathlib import Path
from typing import Dict, List

from core_engine.agent_controller import AgentController
from core_engine.config import get_settings
from core_engine.id_generator import generate_task_record_id
from core_engine.task_store import delete_task as db_delete_task
from core_engine.task_store import get_task as db_get_task
from core_engine.task_store import list_tasks as db_list_tasks, upsert_task as db_upsert_task
from game_modules.business_sim.agents import AGENTS

MODULE_NAME = "business_sim"
_MIN_NORMAL_TASKS = 3
_LAST_AUTO_GENERATE_TS = 0.0
_SEED_FILE_PATH = Path(__file__).with_name("task_seeds.json")
_DIFFICULTY_VALUES = {"easy", "medium", "hard"}


def _coerce_difficulty(raw: object) -> str:
    value = str(raw or "easy").strip().lower()
    return value if value in _DIFFICULTY_VALUES else "easy"


def _polish_description(raw_description: str, required_constraints: List[str]) -> str:
    description = str(raw_description or "").strip()
    if not description:
        description = "Complete this task with a clear and structured response."
    if required_constraints:
        preview = ", ".join(str(item).strip() for item in required_constraints[:3] if str(item).strip())
        if preview and "must include" not in description.lower():
            description = f"{description} Must include: {preview}."
    return description


def normalize_task(task_id: str, task_config: Dict[str, object]) -> Dict[str, object]:
    """Normalize one task into stable MVP schema with backward-compatible aliases."""
    cfg = dict(task_config or {})
    normalized_id = _safe_slug(str(task_id))
    title = str(cfg.get("title") or normalized_id.replace("_", " ").title()).strip()
    description = str(cfg.get("description") or cfg.get("input") or "").strip()
    difficulty = _coerce_difficulty(cfg.get("difficulty"))
    base_reward = float(cfg.get("base_reward", cfg.get("reward", 0.0)) or 0.0)
    estimated_cost = float(cfg.get("estimated_cost", cfg.get("cost_estimate", 0.0)) or 0.0)
    required_constraints = [
        str(item).strip()
        for item in (cfg.get("required_constraints", cfg.get("constraints", [])) or [])
        if str(item).strip()
    ]
    description = _polish_description(description, required_constraints)
    tutorial_only = bool(cfg.get("tutorial_only", cfg.get("is_tutorial", False)))
    default_threshold = 55.0 if tutorial_only else 72.0
    success_threshold = float(cfg.get("success_threshold", default_threshold) or default_threshold)

    normalized = {
        "task_id": normalized_id,
        "title": title,
        "description": description,
        "difficulty": difficulty,
        "base_reward": round(base_reward, 2),
        "estimated_cost": round(estimated_cost, 2),
        "required_constraints": required_constraints,
        "success_threshold": round(success_threshold, 2),
        "tutorial_only": tutorial_only,
        # Backward-compatible aliases used by existing run/eval/progression code.
        "input": description,
        "reward": round(base_reward, 2),
        "cost_estimate": round(estimated_cost, 2),
        "constraints": required_constraints,
        "is_tutorial": tutorial_only,
        "workflow": list(
            cfg.get("workflow", ["market_analyst", "strategy_writer"]) or ["market_analyst", "strategy_writer"]),
        "max_total_tokens": int(cfg.get("max_total_tokens", 320) or 320),
        "tutorial_order": int(cfg.get("tutorial_order", 9999) or 9999),
        "strict_constraints": bool(cfg.get("strict_constraints", False)),
    }
    return normalized


def generate_task_id(task_config: Dict[str, object], seed_hint: str | None = None) -> str:
    """Generate stable backend-owned task id from task content."""
    cfg = dict(task_config or {})
    title = str(cfg.get("title") or "").strip()
    description = str(cfg.get("description") or cfg.get("input") or "").strip()
    slug_source = title or description or str(seed_hint or "task")
    slug = _safe_slug(slug_source)[:24] or "task"
    fingerprint_payload = {
        "title": title,
        "description": description,
        "difficulty": str(cfg.get("difficulty", "easy")),
        "tutorial_only": bool(cfg.get("tutorial_only", cfg.get("is_tutorial", False))),
        "workflow": list(
            cfg.get("workflow", ["market_analyst", "strategy_writer"]) or ["market_analyst", "strategy_writer"]),
    }
    digest = hashlib.sha1(
        json.dumps(fingerprint_payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
    ).hexdigest()[:8]
    return f"tsk_{slug}_{digest}"


def _generate_ulid_task_id() -> str:
    """Generate backend-owned ULID-style task id for manual/admin task creation."""
    return f"tsk_{generate_task_record_id()}"


def validate_task_schema(task_id: str, task_config: Dict[str, object]) -> None:
    """Raise ValueError when normalized task schema is invalid."""
    cfg = normalize_task(task_id, task_config)
    if not cfg["task_id"]:
        raise ValueError("task_id is required")
    if not cfg["title"]:
        raise ValueError(f"Task '{task_id}' title is required")
    if not cfg["description"]:
        raise ValueError(f"Task '{task_id}' description is required")
    if cfg["difficulty"] not in _DIFFICULTY_VALUES:
        raise ValueError(f"Task '{task_id}' difficulty must be one of {_DIFFICULTY_VALUES}")
    if float(cfg["base_reward"]) < 0:
        raise ValueError(f"Task '{task_id}' base_reward must be >= 0")
    if float(cfg["estimated_cost"]) < 0:
        raise ValueError(f"Task '{task_id}' estimated_cost must be >= 0")
    if not isinstance(cfg["required_constraints"], list):
        raise ValueError(f"Task '{task_id}' required_constraints must be a list")
    workflow = cfg.get("workflow", [])
    if not isinstance(workflow, list) or not workflow:
        raise ValueError(f"Task '{task_id}' workflow must be a non-empty list")
    known_agents = set(str(name) for name in AGENTS.keys())
    unknown = [str(name) for name in workflow if str(name) not in known_agents]
    if unknown:
        raise ValueError(
            f"Task '{task_id}' workflow contains unknown agents: {unknown}. "
            f"Known agents: {sorted(known_agents)}"
        )


def to_public_task(task_id: str, task_config: Dict[str, object]) -> Dict[str, object]:
    """Frontend-friendly task payload."""
    cfg = normalize_task(task_id, task_config)
    return {
        "task_id": str(cfg["task_id"]),
        "title": str(cfg["title"]),
        "description": str(cfg["description"]),
        "difficulty": str(cfg["difficulty"]),
        "base_reward": float(cfg["base_reward"]),
        "estimated_cost": float(cfg["estimated_cost"]),
        "required_constraints": list(cfg["required_constraints"]),
        "success_threshold": float(cfg["success_threshold"]),
        "tutorial_only": bool(cfg["tutorial_only"]),
    }


def _require_database_url() -> str:
    database_url = get_settings().database_url
    if not database_url:
        raise RuntimeError("DATABASE_URL is required for task catalog")
    return database_url


def _ensure_task_catalog() -> Dict[str, Dict[str, object]]:
    database_url = _require_database_url()
    try:
        return db_list_tasks(database_url, MODULE_NAME)
    except Exception as exc:
        raise RuntimeError(
            "Task catalog is not initialized. Run bootstrap initialization first."
        ) from exc


def _load_seed_tasks() -> List[Dict[str, object]]:
    raw = json.loads(_SEED_FILE_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"Invalid task seed file format: {_SEED_FILE_PATH}")
    normalized_items: List[Dict[str, object]] = []
    seen_ids: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        seed_task_id = str(item.get("task_id", "")).strip()
        seed_task_config = item.get("task_config", {})
        if not isinstance(seed_task_config, dict):
            continue
        # Dynamic ID allocation:
        # - prefer provided id (when present)
        # - otherwise generate from task content
        # - if collision appears in one seed batch, allocate unique record id
        generated_task_id = str(seed_task_id or generate_task_id(seed_task_config, seed_hint="seed"))
        if generated_task_id in seen_ids:
            generated_task_id = _generate_ulid_task_id()
        seen_ids.add(generated_task_id)
        normalized_cfg = normalize_task(generated_task_id, seed_task_config)
        validate_task_schema(generated_task_id, normalized_cfg)
        normalized_items.append(
            {
                "task_id": normalized_cfg["task_id"],
                "task_config": normalized_cfg,
                "source": str(item.get("source", "seed") or "seed"),
            }
        )
    return normalized_items


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

    task_id = generate_task_id(raw_task := {
        "input": str(payload.get("input", "Assess a new business opportunity with clear trade-offs.")),
        "workflow": ["market_analyst", "strategy_writer"],
        "max_total_tokens": int(payload.get("max_total_tokens", 320) or 320),
        "is_tutorial": False,
        "reward": float(payload.get("reward", 40.0) or 40.0),
        "difficulty": str(payload.get("difficulty", "medium") or "medium"),
        "cost_estimate": float(payload.get("cost_estimate", 9.0) or 9.0),
        "constraints": [str(x) for x in (payload.get("constraints") or ["target customer", "pricing", "risk"])],
        "title": str(payload.get("title", "Generated Business Task") or "Generated Business Task"),
        "description": str(payload.get("description", payload.get("input", "")) or payload.get("input", "")),
    }, seed_hint=str(payload.get("task_id", "generated_task")))
    task = normalize_task(task_id, raw_task)
    validate_task_schema(task_id, task)
    return {"task_id": task["task_id"], "task_config": task, "source": "ai"}


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
        db_upsert_task(
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
    item = db_get_task(database_url, MODULE_NAME, str(task_id))
    if item is None:
        raise ValueError(f"Unknown task: {task_id}")
    normalized = normalize_task(str(task_id), item)
    validate_task_schema(task_id, normalized)
    return normalized


def list_tasks() -> dict:
    tasks = _ensure_task_catalog()
    _maybe_generate_task(tasks)
    raw = db_list_tasks(_require_database_url(), MODULE_NAME)
    normalized: Dict[str, Dict[str, object]] = {}
    for tid, cfg in raw.items():
        cfg_obj = dict(cfg or {})
        item = normalize_task(str(tid), cfg_obj)
        validate_task_schema(str(tid), item)
        normalized[str(item["task_id"])] = item
    return normalized


def get_seed_tasks() -> Dict[str, Dict[str, object]]:
    """Return initial task seed map (used by tests and bootstrapping helpers)."""
    loaded = _load_seed_tasks()
    return {str(item["task_id"]): dict(item["task_config"]) for item in loaded}


def list_task_catalog() -> List[Dict[str, object]]:
    """Return full task catalog in stable public schema (not user-filtered)."""
    catalog = list_tasks()
    items = [to_public_task(task_id, cfg) for task_id, cfg in catalog.items()]
    items.sort(
        key=lambda item: (
            0 if bool(item.get("tutorial_only", False)) else 1,
            str(item.get("difficulty", "")),
            str(item.get("task_id", "")),
        )
    )
    return items


def upsert_task_definition(
        task_config: Dict[str, object],
        task_id: str | None = None,
        source: str = "manual",
) -> Dict[str, object]:
    """Create or update one task definition in DB catalog."""
    assigned_task_id = str(task_id or _generate_ulid_task_id())
    normalized = normalize_task(assigned_task_id, task_config)
    validate_task_schema(assigned_task_id, normalized)
    db_upsert_task(
        database_url=_require_database_url(),
        module_name=MODULE_NAME,
        task_id=str(normalized["task_id"]),
        task_config=normalized,
        source=str(source or "manual"),
    )
    return dict(normalized)


def delete_task_definition(task_id: str) -> bool:
    """Delete one task definition from DB catalog."""
    return db_delete_task(
        database_url=_require_database_url(),
        module_name=MODULE_NAME,
        task_id=str(task_id),
    )
