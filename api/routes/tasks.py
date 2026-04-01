"""Gameplay task board endpoints."""

from fastapi import APIRouter, HTTPException, Path, Query

from api.schemas import TaskManageRequest, TaskUpdateRequest
from api.services.task_zh_temp import build_zh_overlay_by_origin
from core_engine.config import get_settings
from core_engine.module_facade import ModuleFacade
from core_engine.module_loader import ModuleLoadError

router = APIRouter(tags=["tasks"])


def _task_to_public(facade: ModuleFacade, task_id: str, task_config: dict) -> dict:
    tasks_component = getattr(facade, "tasks", None)
    converter = getattr(tasks_component, "to_public_task", None) if tasks_component is not None else None
    if callable(converter):
        return converter(task_id, task_config)
    return {
        "task_id": task_id,
        "title": str(task_config.get("title") or task_id),
        "description": str(task_config.get("description") or task_config.get("input") or ""),
        "difficulty": str(task_config.get("difficulty") or "easy"),
        "base_reward": float(task_config.get("base_reward", task_config.get("reward", 0.0)) or 0.0),
        "estimated_cost": float(task_config.get("estimated_cost", task_config.get("cost_estimate", 0.0)) or 0.0),
        "required_constraints": list(task_config.get("required_constraints", task_config.get("constraints", [])) or []),
        "success_threshold": float(task_config.get("success_threshold", 72.0) or 72.0),
        "tutorial_only": bool(task_config.get("tutorial_only", task_config.get("is_tutorial", False))),
    }


def _overlay_public_text(base_public: dict, zh_task_config: dict) -> dict:
    merged = dict(base_public or {})
    if not isinstance(zh_task_config, dict):
        return merged
    title = zh_task_config.get("title")
    description = zh_task_config.get("description", zh_task_config.get("input"))
    constraints = zh_task_config.get("required_constraints", zh_task_config.get("constraints"))
    if isinstance(title, str) and title.strip():
        merged["title"] = title
    if isinstance(description, str) and description.strip():
        merged["description"] = description
    if isinstance(constraints, list):
        merged["required_constraints"] = [str(item) for item in constraints if str(item).strip()]
    merged["lang"] = "zh-CN"
    merged["origin_task_id"] = str(base_public.get("task_id", ""))
    merged["zh_task_id"] = str(zh_task_config.get("task_id", ""))
    return merged


def _temp_zh_unlock_condition(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return value
    lowered = value.lower()
    if "complete tutorial tasks" in lowered:
        return "先完成教程任务"
    if "complete 5 tasks" in lowered:
        return "完成 5 个任务或钱包达到 80"
    if "complete 10 tasks" in lowered:
        return "完成 10 个任务或钱包达到 150"
    return value


@router.get(
    "/tasks",
    summary="Get Task Board",
    description="Return user-visible tasks based on tutorial/progression state (available + locked).",
)
def get_tasks_route(user_id: str = Query(..., min_length=1, description="Player id for task visibility")) -> dict:
    settings = get_settings()
    try:
        facade = ModuleFacade.from_name(settings.active_game_module)
        task_definitions = facade.list_tasks() or {}
        progression = getattr(facade, "progression", None)
        if progression is None or not callable(getattr(progression, "list_task_board", None)):
            raise RuntimeError("Progression component is unavailable.")
        board_raw = progression.list_task_board(user_id=user_id, task_definitions=task_definitions)
        board = board_raw if isinstance(board_raw, dict) else {}
        available_raw = board.get("available_tasks", board.get("tasks", [])) if isinstance(board, dict) else []
        locked_raw = board.get("locked_tasks", []) if isinstance(board, dict) else []
        available_public: list[dict] = []
        for item in available_raw:
            if not isinstance(item, dict):
                continue
            task_id = str(item.get("task_id", "")).strip()
            if not task_id:
                continue
            payload = _task_to_public(facade, task_id, item)
            if "recommended" in item:
                payload["recommended"] = bool(item.get("recommended", False))
            available_public.append(payload)
        locked_public: list[dict] = []
        for item in locked_raw:
            if not isinstance(item, dict):
                continue
            task_id = str(item.get("task_id", "")).strip()
            if not task_id:
                continue
            payload = _task_to_public(facade, task_id, item)
            payload["unlock_condition"] = _temp_zh_unlock_condition(str(item.get("unlock_condition", "")))
            locked_public.append(payload)
        tutorial_completed = not bool(board.get("locked", False))
        return {
            "user_id": user_id,
            "module_name": settings.active_game_module,
            "tutorial_completed": tutorial_completed,
            "tasks_completed_count": int(board.get("tasks_completed_count", 0) or 0),
            "wallet_balance": float(board.get("wallet_balance", 0.0) or 0.0),
            "available": available_public,
            "locked": locked_public,
            # backward-compatible alias
            "tasks": available_public,
        }
    except ModuleLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/tasks-temp-zh",
    summary="Get Task Board (Temporary Chinese Copy)",
    description="Temporary endpoint: return task board using Chinese DB copies (for MVP frontend toggle).",
)
def get_tasks_temp_zh_route(
        user_id: str = Query(..., min_length=1, description="Player id for task visibility"),
) -> dict:
    settings = get_settings()
    try:
        facade = ModuleFacade.from_name(settings.active_game_module)
        task_definitions = facade.list_tasks() or {}
        progression = getattr(facade, "progression", None)
        if progression is None or not callable(getattr(progression, "list_task_board", None)):
            raise RuntimeError("Progression component is unavailable.")
        zh_overlay = build_zh_overlay_by_origin(
            database_url=settings.database_url,
            module_name=settings.active_game_module,
        )
        board_raw = progression.list_task_board(user_id=user_id, task_definitions=task_definitions)
        board = board_raw if isinstance(board_raw, dict) else {}
        available_raw = board.get("available_tasks", board.get("tasks", [])) if isinstance(board, dict) else []
        locked_raw = board.get("locked_tasks", []) if isinstance(board, dict) else []

        available_public: list[dict] = []
        for item in available_raw:
            if not isinstance(item, dict):
                continue
            task_id = str(item.get("task_id", "")).strip()
            if not task_id:
                continue
            payload = _task_to_public(facade, task_id, item)
            payload = _overlay_public_text(payload, zh_overlay.get(task_id, {}))
            if "recommended" in item:
                payload["recommended"] = bool(item.get("recommended", False))
            available_public.append(payload)

        locked_public: list[dict] = []
        for item in locked_raw:
            if not isinstance(item, dict):
                continue
            task_id = str(item.get("task_id", "")).strip()
            if not task_id:
                continue
            payload = _task_to_public(facade, task_id, item)
            payload = _overlay_public_text(payload, zh_overlay.get(task_id, {}))
            payload["unlock_condition"] = str(item.get("unlock_condition", ""))
            locked_public.append(payload)

        tutorial_completed = not bool(board.get("locked", False))
        return {
            "user_id": user_id,
            "module_name": settings.active_game_module,
            "lang": "zh-CN",
            "tutorial_completed": tutorial_completed,
            "tasks_completed_count": int(board.get("tasks_completed_count", 0) or 0),
            "wallet_balance": float(board.get("wallet_balance", 0.0) or 0.0),
            "available": available_public,
            "locked": locked_public,
            "tasks": available_public,
        }
    except ModuleLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/tasks/{task_id}",
    summary="Get Task Detail",
    description="Return one task detail if the task is currently visible/unlocked for the user.",
)
def get_task_route(
        task_id: str = Path(..., min_length=1, description="Task ID"),
        user_id: str = Query(..., min_length=1, description="Player id for task visibility"),
) -> dict:
    settings = get_settings()
    try:
        facade = ModuleFacade.from_name(settings.active_game_module)
        task_definitions = facade.list_tasks() or {}
        progression = getattr(facade, "progression", None)
        if progression is None or not callable(getattr(progression, "list_task_board", None)):
            raise RuntimeError("Progression component is unavailable.")
        board_raw = progression.list_task_board(user_id=user_id, task_definitions=task_definitions)
        board = board_raw if isinstance(board_raw, dict) else {}
        visible_tasks = board.get("available_tasks", board.get("tasks", [])) if isinstance(board, dict) else []
        visible_ids = {str(item.get("task_id", "")) for item in visible_tasks if isinstance(item, dict)}
        if task_id not in visible_ids:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not available for this user.")
        task_cfg = task_definitions.get(task_id)
        if not isinstance(task_cfg, dict):
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
        return _task_to_public(facade, task_id, task_cfg)
    except HTTPException:
        raise
    except ModuleLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/tasks-catalog",
    summary="Get Task Catalog",
    description="Return all module tasks without user progression filtering (admin/debug overview).",
)
def get_tasks_catalog_route() -> dict:
    """Global task overview (not filtered by player progression)."""
    settings = get_settings()
    try:
        facade = ModuleFacade.from_name(settings.active_game_module)
        task_definitions = facade.list_tasks() or {}
        items = [_task_to_public(facade, task_id, cfg) for task_id, cfg in task_definitions.items() if
                 isinstance(cfg, dict)]
        items.sort(
            key=lambda item: (
                0 if bool(item.get("tutorial_only", False)) else 1,
                str(item.get("difficulty", "")),
                str(item.get("task_id", "")),
            )
        )
        return {
            "module_name": settings.active_game_module,
            "total_tasks": len(items),
            "tutorial_tasks": sum(1 for item in items if bool(item.get("tutorial_only", False))),
            "normal_tasks": sum(1 for item in items if not bool(item.get("tutorial_only", False))),
            "tasks": items,
        }
    except ModuleLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/task/admin",
    summary="Admin List Tasks",
    description="List all task definitions with raw config and public projection.",
)
def admin_list_tasks_route() -> dict:
    settings = get_settings()
    try:
        facade = ModuleFacade.from_name(settings.active_game_module)
        task_definitions = facade.list_tasks() or {}
        return {
            "module_name": settings.active_game_module,
            "total_tasks": len(task_definitions),
            "tasks": [
                {
                    "task_id": task_id,
                    "public": _task_to_public(facade, task_id, cfg),
                    "task_config": cfg,
                }
                for task_id, cfg in sorted(task_definitions.items(), key=lambda pair: str(pair[0]))
                if isinstance(cfg, dict)
            ],
        }
    except ModuleLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/task/admin/{task_id}",
    summary="Admin Get Task",
    description="Fetch one task definition by task ID.",
)
def admin_get_task_route(task_id: str = Path(..., min_length=1, description="Task ID")) -> dict:
    settings = get_settings()
    try:
        facade = ModuleFacade.from_name(settings.active_game_module)
        cfg = facade.get_task(task_id)
        if not isinstance(cfg, dict):
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
        return {
            "module_name": settings.active_game_module,
            "task_id": task_id,
            "public": _task_to_public(facade, task_id, cfg),
            "task_config": cfg,
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ModuleLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/task/admin",
    summary="Admin Create Task",
    description="Create a new task definition. Task ID is generated by backend ULID generator.",
)
def admin_create_task_route(request: TaskManageRequest) -> dict:
    settings = get_settings()
    try:
        facade = ModuleFacade.from_name(settings.active_game_module)
        upsert_fn = getattr(facade.tasks, "upsert_task_definition", None)
        if not callable(upsert_fn):
            raise RuntimeError("Task management is not supported by active module.")
        saved = upsert_fn(
            task_config=request.task_config.model_dump(exclude_none=True),
            source=request.source,
        )
        saved_task_id = str(saved.get("task_id", ""))
        return {
            "module_name": settings.active_game_module,
            "task_id": saved_task_id,
            "public": _task_to_public(facade, saved_task_id, saved),
            "task_config": saved,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ModuleLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put(
    "/task/admin/{task_id}",
    summary="Admin Update Task",
    description="Update one existing task definition by task ID.",
)
def admin_update_task_route(
        request: TaskUpdateRequest,
        task_id: str = Path(..., min_length=1, description="Task ID"),
) -> dict:
    settings = get_settings()
    try:
        facade = ModuleFacade.from_name(settings.active_game_module)
        upsert_fn = getattr(facade.tasks, "upsert_task_definition", None)
        if not callable(upsert_fn):
            raise RuntimeError("Task management is not supported by active module.")
        saved = upsert_fn(
            task_id=task_id,
            task_config=request.task_config.model_dump(exclude_none=True),
            source=request.source,
        )
        return {
            "module_name": settings.active_game_module,
            "task_id": str(saved.get("task_id", task_id)),
            "public": _task_to_public(facade, task_id, saved),
            "task_config": saved,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ModuleLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete(
    "/task/admin/{task_id}",
    summary="Admin Delete Task",
    description="Delete one task definition by task ID.",
)
def admin_delete_task_route(task_id: str = Path(..., min_length=1, description="Task ID")) -> dict:
    settings = get_settings()
    try:
        facade = ModuleFacade.from_name(settings.active_game_module)
        delete_fn = getattr(facade.tasks, "delete_task_definition", None)
        if not callable(delete_fn):
            raise RuntimeError("Task management is not supported by active module.")
        deleted = bool(delete_fn(task_id))
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
        return {
            "module_name": settings.active_game_module,
            "task_id": task_id,
            "deleted": True,
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ModuleLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
